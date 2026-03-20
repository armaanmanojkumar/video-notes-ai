from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from groq import Groq

from backend.config import settings
from backend.services.transcriber import format_timestamp

logger = logging.getLogger(__name__)

_client: Optional[Groq] = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        if not settings.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set.")
        _client = Groq(api_key=settings.GROQ_API_KEY)
    return _client


def _llm(prompt: str, system: str, temperature: float = 0.3, max_tokens: int = 4096) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def _parse_json_block(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    for pat in (r"\{[\s\S]+\}", r"\[[\s\S]+\]"):
        match = re.search(pat, text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    return None


SYSTEM_ANALYST = (
    "You are an expert content analyst AI. Your job is to analyze video/lecture/meeting "
    "transcripts and extract structured, actionable intelligence. Always be precise, concrete, "
    "and helpful. When outputting JSON, output ONLY valid JSON with no additional text."
)


def generate_summaries(transcript: str, title: str = "") -> Dict[str, str]:
    context = f'Title: "{title}"\n\n' if title else ""
    prompt = f"""{context}Transcript:
\"\"\"
{transcript[:12000]}
\"\"\"

Produce a JSON object with exactly two keys:
1. "executive_summary": a 3-sentence TL;DR.
2. "detailed_summary": a thorough 4-6 paragraph summary."""

    raw = _llm(prompt, SYSTEM_ANALYST, max_tokens=2048)
    parsed = _parse_json_block(raw)
    if parsed and isinstance(parsed, dict):
        return {
            "executive_summary": parsed.get("executive_summary", ""),
            "summary": parsed.get("detailed_summary", ""),
        }
    return {"executive_summary": raw[:300], "summary": raw}


def extract_chapters(segments: List[Dict], transcript: str, title: str = "") -> List[Dict]:
    if not segments:
        return []
    simplified = [
        f"[{format_timestamp(s['start'])}] {s['text']}"
        for s in segments[:: max(1, len(segments) // 80)]
    ]
    prompt = f"""Video title: "{title}"

Transcript sample:
{chr(10).join(simplified[:120])}

Identify 4-10 meaningful chapters.
Return a JSON array. Each element:
  - "title": short chapter title (max 8 words)
  - "start_time": start time in seconds (number)
  - "end_time": end time in seconds (number)
  - "summary": 1-2 sentence description

Sort by start_time ascending."""

    raw = _llm(prompt, SYSTEM_ANALYST, max_tokens=2048)
    parsed = _parse_json_block(raw)
    if isinstance(parsed, list):
        return [
            {
                "title": str(ch["title"]),
                "start_time": float(ch.get("start_time", 0)),
                "end_time": float(ch.get("end_time", 0)),
                "summary": str(ch.get("summary", "")),
            }
            for ch in parsed if isinstance(ch, dict) and "title" in ch
        ]
    return []


def extract_key_timestamps(segments: List[Dict], title: str = "") -> List[Dict]:
    if not segments:
        return []
    simplified = [
        f"[{format_timestamp(s['start'])} / {s['start']}s] {s['text']}"
        for s in segments[:: max(1, len(segments) // 60)]
    ]
    prompt = f"""Video: "{title}"

Segments:
{chr(10).join(simplified[:100])}

Identify the 5-15 most important moments.
Return a JSON array. Each element:
  - "time": exact time in seconds (number)
  - "label": concise label (max 10 words)
  - "importance": integer 1-5"""

    raw = _llm(prompt, SYSTEM_ANALYST, max_tokens=1024)
    parsed = _parse_json_block(raw)
    if isinstance(parsed, list):
        valid = [
            {
                "time": float(ts["time"]),
                "label": str(ts.get("label", "")),
                "importance": int(ts.get("importance", 3)),
            }
            for ts in parsed if isinstance(ts, dict) and "time" in ts
        ]
        return sorted(valid, key=lambda x: x["importance"], reverse=True)[:15]
    return []


def extract_action_items(transcript: str) -> List[Dict]:
    prompt = f"""Transcript:
\"\"\"
{transcript[:10000]}
\"\"\"

Extract every concrete action item or to-do.
Return a JSON array. Each element:
  - "task": actionable task starting with a verb
  - "priority": "high" | "medium" | "low"
  - "context": 1-sentence explanation
  - "owner": person responsible or null

If none, return []."""

    raw = _llm(prompt, SYSTEM_ANALYST, max_tokens=2048)
    parsed = _parse_json_block(raw)
    if isinstance(parsed, list):
        return [
            {
                "task": str(item["task"]),
                "priority": str(item.get("priority", "medium")).lower(),
                "context": str(item.get("context", "")),
                "owner": item.get("owner"),
            }
            for item in parsed if isinstance(item, dict) and "task" in item
        ]
    return []


def extract_key_points(transcript: str, n: int = 10) -> List[str]:
    prompt = f"""Transcript:
\"\"\"
{transcript[:10000]}
\"\"\"

Extract the {n} most important insights.
Return a JSON array of strings. No bullet symbols."""

    raw = _llm(prompt, SYSTEM_ANALYST, max_tokens=1024)
    parsed = _parse_json_block(raw)
    if isinstance(parsed, list):
        return [str(p) for p in parsed if p][:n]
    return []


def classify_content(transcript: str, title: str = "") -> Dict[str, Any]:
    prompt = f"""Title: "{title}"

Transcript:
\"\"\"
{transcript[:6000]}
\"\"\"

Return a JSON object with:
  - "topics": array of 3-8 topic strings
  - "sentiment": one of informative / motivational / analytical / conversational / technical / critical / educational
  - "difficulty_level": "beginner" | "intermediate" | "advanced"
  - "questions_answered": array of up to 8 questions this video answers"""

    raw = _llm(prompt, SYSTEM_ANALYST, max_tokens=1024)
    parsed = _parse_json_block(raw)
    if isinstance(parsed, dict):
        return {
            "topics": parsed.get("topics", []),
            "sentiment": parsed.get("sentiment", "informative"),
            "difficulty_level": parsed.get("difficulty_level", "intermediate"),
            "questions_answered": parsed.get("questions_answered", []),
        }
    return {"topics": [], "sentiment": "informative", "difficulty_level": "intermediate", "questions_answered": []}


def count_words(transcript: str) -> Dict[str, int]:
    words = transcript.lower().split()
    return {"total": len(words), "unique": len(set(words))}


def run_full_analysis(
    transcript: str,
    segments: List[Dict],
    title: str = "",
    generate_chapters: bool = True,
    generate_action_items: bool = True,
    generate_timestamps: bool = True,
    progress_callback=None,
) -> Dict[str, Any]:
    def _progress(stage, pct):
        if progress_callback:
            progress_callback(stage, pct)

    results: Dict[str, Any] = {}
    results["word_count"] = count_words(transcript)

    tasks = {
        "summaries": lambda: generate_summaries(transcript, title),
        "key_points": lambda: extract_key_points(transcript),
        "classification": lambda: classify_content(transcript, title),
    }
    if generate_chapters:
        tasks["chapters"] = lambda: extract_chapters(segments, transcript, title)
    if generate_timestamps:
        tasks["timestamps"] = lambda: extract_key_timestamps(segments, title)
    if generate_action_items:
        tasks["actions"] = lambda: extract_action_items(transcript)

    _progress("Sending all requests to Groq simultaneously", 10)

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        completed = 0
        total = len(futures)

        for future in as_completed(futures):
            name = futures[future]
            completed += 1
            pct = 10 + int((completed / total) * 85)
            try:
                result = future.result()
                if name == "summaries":
                    results.update(result)
                elif name == "key_points":
                    results["key_points"] = result
                elif name == "classification":
                    results.update(result)
                elif name == "chapters":
                    results["chapters"] = result
                elif name == "timestamps":
                    results["key_timestamps"] = result
                elif name == "actions":
                    results["action_items"] = result
                _progress(f"{name.title()} ready", pct)
            except Exception as e:
                logger.error(f"Task {name} failed: {e}")
                if name == "summaries":
                    results["summary"] = ""
                    results["executive_summary"] = ""
                elif name == "key_points":
                    results["key_points"] = []
                elif name == "classification":
                    results.update({"topics": [], "sentiment": "informative", "difficulty_level": "intermediate", "questions_answered": []})
                elif name == "chapters":
                    results["chapters"] = []
                elif name == "timestamps":
                    results["key_timestamps"] = []
                elif name == "actions":
                    results["action_items"] = []

    _progress("Analysis complete", 100)
    return results
