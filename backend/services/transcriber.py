from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from groq import Groq

from backend.config import settings
from backend.services.video_processor import split_audio_for_whisper

logger = logging.getLogger(__name__)

_client: Optional[Groq] = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        if not settings.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set.")
        _client = Groq(api_key=settings.GROQ_API_KEY)
    return _client


def transcribe_file(audio_path: str, language: str = "auto") -> Dict:
    client = _get_client()
    lang = None if language in ("auto", None) else language

    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            file=(Path(audio_path).name, f),
            model=settings.STT_MODEL,
            language=lang,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    segments = []
    if hasattr(response, "segments") and response.segments:
        for seg in response.segments:
            if isinstance(seg, dict):
                segments.append({
                    "id": seg.get("id", ""),
                    "start": round(seg.get("start", 0), 2),
                    "end": round(seg.get("end", 0), 2),
                    "text": seg.get("text", "").strip(),
                })
            else:
                segments.append({
                    "id": getattr(seg, "id", ""),
                    "start": round(getattr(seg, "start", 0), 2),
                    "end": round(getattr(seg, "end", 0), 2),
                    "text": getattr(seg, "text", "").strip(),
                })

    return {
        "text": response.text.strip(),
        "segments": segments,
        "language": getattr(response, "language", language),
        "duration": getattr(response, "duration", None),
    }


def transcribe_long_audio(audio_path: str, language: str = "auto", progress_callback=None) -> Dict:
    chunks = split_audio_for_whisper(audio_path, max_chunk_minutes=25)

    full_text_parts: List[str] = []
    all_segments: List[Dict] = []
    detected_language = language
    time_offset = 0.0

    for idx, chunk_path in enumerate(chunks):
        if progress_callback:
            pct = (idx / len(chunks)) * 100
            progress_callback(f"Transcribing part {idx + 1} of {len(chunks)}", pct)

        result = transcribe_file(chunk_path, language=language)

        for seg in result["segments"]:
            seg["start"] += time_offset
            seg["end"] += time_offset
            all_segments.append(seg)

        full_text_parts.append(result["text"])
        time_offset += result.get("duration") or _estimate_duration(chunk_path)

        if detected_language == "auto" and result.get("language"):
            detected_language = result["language"]

        if chunk_path != audio_path and os.path.exists(chunk_path):
            try:
                os.remove(chunk_path)
            except OSError:
                pass

    return {
        "text": " ".join(full_text_parts),
        "segments": all_segments,
        "language": detected_language,
        "duration": time_offset,
    }


def _estimate_duration(path: str) -> float:
    try:
        size_bytes = os.path.getsize(path)
        return size_bytes / (128 * 1024 / 8)
    except OSError:
        return 0.0


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"