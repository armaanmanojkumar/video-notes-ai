from __future__ import annotations

import logging
import os
import subprocess
import uuid
from pathlib import Path
from typing import Dict, Optional

from backend.config import settings

logger = logging.getLogger(__name__)


def download_youtube(url: str, output_dir: Optional[Path] = None) -> Dict:
    from pytubefix import YouTube

    output_dir = output_dir or settings.UPLOAD_DIR
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    uid = str(uuid.uuid4())

    yt = YouTube(
        url,
        use_oauth=False,
        allow_oauth_cache=False,
    )

    stream = (
        yt.streams
        .filter(only_audio=True)
        .order_by("abr")
        .last()
    )

    if not stream:
        stream = yt.streams.filter(progressive=True).order_by("resolution").last()

    if not stream:
        raise RuntimeError("No downloadable stream found for this video. It may be age-restricted or private.")

    raw_path = stream.download(output_path=str(output_dir), filename=uid)

    output_path = str(output_dir / f"{uid}.mp3")

    cmd = [
        "ffmpeg", "-i", raw_path,
        "-vn", "-ar", "16000", "-ac", "1", "-b:a", "128k",
        "-y", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if os.path.exists(raw_path) and raw_path != output_path:
        try:
            os.remove(raw_path)
        except OSError:
            pass

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr[:300]}")

    return {
        "file_path": output_path,
        "title": yt.title or "Untitled",
        "duration": yt.length,
        "thumbnail": yt.thumbnail_url,
        "channel": yt.author,
        "language": None,
    }


def extract_audio_from_file(input_path: str, output_dir: Optional[Path] = None) -> str:
    output_dir = output_dir or settings.UPLOAD_DIR
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    uid = str(uuid.uuid4())
    output_path = output_dir / f"{uid}.mp3"

    cmd = [
        "ffmpeg", "-i", input_path,
        "-vn", "-ar", "16000", "-ac", "1", "-b:a", "128k",
        "-y", str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[:500]}")

    return str(output_path)


def get_audio_duration(file_path: str) -> Optional[float]:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0", file_path,
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return float(out)
    except Exception:
        return None


def split_audio_for_whisper(
    file_path: str,
    max_chunk_minutes: int = 25,
    output_dir: Optional[Path] = None,
) -> list[str]:
    output_dir = output_dir or settings.UPLOAD_DIR
    output_dir = Path(output_dir)

    duration = get_audio_duration(file_path)
    if duration is None:
        return [file_path]

    chunk_seconds = max_chunk_minutes * 60
    if duration <= chunk_seconds:
        return [file_path]

    chunks = []
    start = 0
    idx = 0
    uid = str(uuid.uuid4())[:8]

    while start < duration:
        end = min(start + chunk_seconds, duration)
        chunk_path = str(output_dir / f"{uid}_chunk_{idx:03d}.mp3")
        cmd = [
            "ffmpeg", "-i", file_path,
            "-ss", str(start), "-to", str(end),
            "-c", "copy", "-y", chunk_path,
        ]
        subprocess.run(cmd, capture_output=True)
        chunks.append(chunk_path)
        start = end
        idx += 1

    return chunks


def cleanup_files(*file_paths: str):
    for p in file_paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass
