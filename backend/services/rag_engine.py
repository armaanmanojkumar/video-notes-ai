from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer

from backend.config import settings
from backend.services.transcriber import format_timestamp

logger = logging.getLogger(__name__)

_chroma_client: Optional[chromadb.PersistentClient] = None
_embedder: Optional[SentenceTransformer] = None


def _get_chroma():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(
            path=str(settings.CHROMA_DIR),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _chroma_client


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _embedder


def _chunk_transcript(segments: List[Dict], transcript: str) -> List[Dict]:
    chunk_tokens = settings.CHUNK_SIZE_TOKENS
    overlap_tokens = settings.CHUNK_OVERLAP_TOKENS

    if not segments:
        words = transcript.split()
        chunks = []
        step = max(1, chunk_tokens - overlap_tokens)
        for i in range(0, len(words), step):
            chunks.append({
                "text": " ".join(words[i: i + chunk_tokens]),
                "start_time": None,
                "end_time": None,
                "chunk_id": str(uuid.uuid4()),
            })
        return chunks

    chunks = []
    current_segs: List[Dict] = []
    current_tokens = 0

    def flush():
        if not current_segs:
            return
        chunks.append({
            "text": " ".join(s["text"] for s in current_segs),
            "start_time": current_segs[0]["start"],
            "end_time": current_segs[-1]["end"],
            "chunk_id": str(uuid.uuid4()),
        })

    for seg in segments:
        seg_tokens = len(seg["text"].split())
        if current_tokens + seg_tokens > chunk_tokens and current_segs:
            flush()
            overlap_segs = []
            overlap_count = 0
            for prev_seg in reversed(current_segs):
                t = len(prev_seg["text"].split())
                if overlap_count + t > overlap_tokens:
                    break
                overlap_segs.insert(0, prev_seg)
                overlap_count += t
            current_segs = overlap_segs[:]
            current_tokens = sum(len(s["text"].split()) for s in current_segs)
        current_segs.append(seg)
        current_tokens += seg_tokens

    flush()
    return chunks


def index_transcript(session_id: str, transcript: str, segments: List[Dict], title: str = "") -> int:
    client = _get_chroma()
    embedder = _get_embedder()

    try:
        client.delete_collection(session_id)
    except Exception:
        pass

    collection = client.create_collection(name=session_id, metadata={"hnsw:space": "cosine"})
    chunks = _chunk_transcript(segments, transcript)
    if not chunks:
        return 0

    texts = [c["text"] for c in chunks]
    embeddings = embedder.encode(texts, show_progress_bar=False).tolist()

    batch_size = 500
    for i in range(0, len(chunks), batch_size):
        collection.add(
            ids=[c["chunk_id"] for c in chunks[i: i + batch_size]],
            embeddings=embeddings[i: i + batch_size],
            documents=texts[i: i + batch_size],
            metadatas=[
                {"start_time": str(c.get("start_time") or ""), "end_time": str(c.get("end_time") or ""), "title": title}
                for c in chunks[i: i + batch_size]
            ],
        )

    return len(chunks)


def retrieve_relevant_chunks(session_id: str, query: str, top_k: int = None) -> List[Dict]:
    top_k = top_k or settings.TOP_K_RESULTS
    client = _get_chroma()
    embedder = _get_embedder()

    try:
        collection = client.get_collection(session_id)
    except Exception:
        return []

    query_embedding = embedder.encode([query]).tolist()
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
        start = meta.get("start_time")
        chunks.append({
            "text": doc,
            "start_time": float(start) if start else None,
            "timestamp_label": format_timestamp(float(start)) if start else None,
            "relevance_score": round(1 - dist, 3),
        })
    return chunks


def answer_question(session_id: str, question: str, chat_history: List[Dict] = None, title: str = "") -> Dict[str, Any]:
    from backend.services.analyzer import _llm

    sources = retrieve_relevant_chunks(session_id, question)
    if not sources:
        return {"answer": "I don't have enough context from the transcript to answer that.", "sources": []}

    context = "\n\n".join(
        f"[Excerpt {i + 1}{' at ' + s['timestamp_label'] if s.get('timestamp_label') else ''}]\n{s['text']}"
        for i, s in enumerate(sources)
    )

    history_str = ""
    if chat_history:
        lines = [f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in chat_history[-6:]]
        history_str = "\nPrevious conversation:\n" + "\n".join(lines) + "\n"

    system = (
        f'You are a helpful assistant answering questions about the video "{title}". '
        "Use ONLY the provided transcript excerpts. If the answer is not there, say so. "
        "Mention timestamps when relevant. Be concise."
    )

    answer = _llm(
        f"{history_str}\nTranscript excerpts:\n---\n{context}\n---\n\nQuestion: {question}\n\nAnswer:",
        system, temperature=0.2, max_tokens=1024
    )

    return {"answer": answer, "sources": sources}


def delete_session_index(session_id: str):
    try:
        _get_chroma().delete_collection(session_id)
    except Exception:
        pass
