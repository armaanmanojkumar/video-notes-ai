from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, field_validator


class ProcessURLRequest(BaseModel):
    url: str
    language: str = "auto"
    generate_chapters: bool = True
    generate_action_items: bool = True
    generate_timestamps: bool = True

    @field_validator("url")
    @classmethod
    def url_must_be_valid(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: List[Dict[str, str]] = []


class ProcessResponse(BaseModel):
    session_id: str
    status: str
    message: str


class StatusResponse(BaseModel):
    session_id: str
    status: str
    progress: float
    stage: Optional[str]
    error: Optional[str]


class NotesResponse(BaseModel):
    session_id: str
    title: Optional[str]
    source_url: Optional[str]
    source_type: str
    duration: Optional[float]
    language: str
    thumbnail: Optional[str]
    channel: Optional[str]
    status: str
    created_at: Optional[str]
    transcript: Optional[str]
    transcript_segments: Optional[List[Dict[str, Any]]]
    summary: Optional[str]
    executive_summary: Optional[str]
    chapters: Optional[List[Dict[str, Any]]]
    key_timestamps: Optional[List[Dict[str, Any]]]
    action_items: Optional[List[Dict[str, Any]]]
    key_points: Optional[List[str]]
    topics: Optional[List[str]]
    sentiment: Optional[str]
    difficulty_level: Optional[str]
    word_count: Optional[Dict[str, int]]
    questions_answered: Optional[List[str]]

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]] = []
    session_id: str


class HistoryItem(BaseModel):
    id: str
    title: Optional[str]
    source_type: str
    source_url: Optional[str]
    duration: Optional[float]
    status: str
    created_at: Optional[str]
    thumbnail: Optional[str]


class HistoryResponse(BaseModel):
    items: List[HistoryItem]
    total: int
