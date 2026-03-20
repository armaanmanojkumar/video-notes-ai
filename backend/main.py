from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.database import ChatMessage, VideoSession, get_db, init_db
from backend.models.schemas import ChatRequest, ChatResponse, HistoryItem, HistoryResponse, NotesResponse, ProcessResponse, ProcessURLRequest, StatusResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, session_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(session_id, []).append(ws)

    def disconnect(self, session_id: str, ws: WebSocket):
        if session_id in self._connections:
            try:
                self._connections[session_id].remove(ws)
            except ValueError:
                pass

    async def broadcast(self, session_id: str, message: dict):
        dead = []
        for ws in self._connections.get(session_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(session_id, ws)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        from backend.utils.static_helper import ensure_frontend_served
        ensure_frontend_served()
    except Exception as e:
        logger.warning(f"Could not copy frontend: {e}")
    logger.info("VideoNotes AI started")
    yield


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if (FRONTEND_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")


def _sync_emit(session_id: str, stage: str, progress: float, db: Session):
    session = db.query(VideoSession).filter(VideoSession.id == session_id).first()
    if session:
        session.stage = stage
        session.progress = progress
        session.updated_at = datetime.utcnow()
        db.commit()
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(
                manager.broadcast(session_id, {"event": "progress", "stage": stage, "progress": progress})
            )
    except RuntimeError:
        pass


async def _run_pipeline(session_id: str, audio_path: str):
    from backend.models.database import SessionLocal
    from backend.services.transcriber import transcribe_long_audio
    from backend.services.analyzer import run_full_analysis
    from backend.services.rag_engine import index_transcript

    db = SessionLocal()
    try:
        session = db.query(VideoSession).filter(VideoSession.id == session_id).first()
        if not session:
            return

        session.status = "processing"
        db.commit()

        _sync_emit(session_id, "Transcribing audio", 5, db)
        transcript_result = transcribe_long_audio(
            audio_path,
            language=session.language,
            progress_callback=lambda s, p: _sync_emit(session_id, s, 5 + p * 0.40, db),
        )

        transcript = transcript_result["text"]
        segments = transcript_result["segments"]

        session.transcript = transcript
        session.transcript_segments = segments
        session.language = transcript_result.get("language") or session.language
        if not session.duration:
            session.duration = transcript_result.get("duration")
        db.commit()

        _sync_emit(session_id, "Running AI analysis", 50, db)
        analysis = run_full_analysis(
            transcript=transcript,
            segments=segments,
            title=session.title or "",
            generate_chapters=True,
            generate_action_items=True,
            generate_timestamps=True,
            progress_callback=lambda s, p: _sync_emit(session_id, s, 50 + p * 0.35, db),
        )

        session.summary = analysis.get("summary")
        session.executive_summary = analysis.get("executive_summary")
        session.chapters = analysis.get("chapters")
        session.key_timestamps = analysis.get("key_timestamps")
        session.action_items = analysis.get("action_items")
        session.key_points = analysis.get("key_points")
        session.topics = analysis.get("topics")
        session.sentiment = analysis.get("sentiment")
        session.difficulty_level = analysis.get("difficulty_level")
        session.word_count = analysis.get("word_count")
        session.questions_answered = analysis.get("questions_answered")
        db.commit()

        _sync_emit(session_id, "Building Q&A index", 88, db)
        index_transcript(session_id=session_id, transcript=transcript, segments=segments, title=session.title or "")

        session.status = "completed"
        session.progress = 100
        session.stage = "Done"
        session.updated_at = datetime.utcnow()
        db.commit()

        await manager.broadcast(session_id, {"event": "completed", "session_id": session_id, "progress": 100})

    except Exception as exc:
        logger.error(f"Pipeline failed for {session_id}: {exc}\n{traceback.format_exc()}")
        session = db.query(VideoSession).filter(VideoSession.id == session_id).first()
        if session:
            session.status = "failed"
            session.error = str(exc)[:500]
            session.updated_at = datetime.utcnow()
            db.commit()
        await manager.broadcast(session_id, {"event": "error", "session_id": session_id, "error": str(exc)})
    finally:
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except OSError:
            pass
        db.close()


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.post("/api/process/url", response_model=ProcessResponse)
async def process_url(body: ProcessURLRequest, db: Session = Depends(get_db)):
    from backend.services.video_processor import download_youtube

    source_type = "youtube" if any(h in body.url for h in ("youtube.com", "youtu.be")) else "url"

    session = VideoSession(
        source_url=body.url,
        source_type=source_type,
        language=body.language if body.language != "auto" else "auto",
        status="pending",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    session_id = session.id

    async def _download_and_run():
        from backend.models.database import SessionLocal
        db2 = SessionLocal()
        try:
            await manager.broadcast(session_id, {"event": "progress", "stage": "Downloading video", "progress": 2})
            meta = download_youtube(body.url)
            s = db2.query(VideoSession).filter(VideoSession.id == session_id).first()
            if s:
                s.title = meta.get("title")
                s.duration = meta.get("duration")
                s.thumbnail = meta.get("thumbnail")
                s.channel = meta.get("channel")
                db2.commit()
            await _run_pipeline(session_id, meta["file_path"])
        except Exception as exc:
            s = db2.query(VideoSession).filter(VideoSession.id == session_id).first()
            if s:
                s.status = "failed"
                s.error = str(exc)[:500]
                db2.commit()
            await manager.broadcast(session_id, {"event": "error", "error": str(exc)})
        finally:
            db2.close()

    asyncio.create_task(_download_and_run())

    return ProcessResponse(session_id=session_id, status="pending", message="Processing started.")


@app.post("/api/process/upload", response_model=ProcessResponse)
async def process_upload(file: UploadFile = File(...), language: str = Form("auto"), db: Session = Depends(get_db)):
    from backend.services.video_processor import extract_audio_from_file, get_audio_duration

    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    suffix = Path(file.filename or "upload").suffix or ".mp4"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        total = 0
        while chunk := await file.read(8192):
            total += len(chunk)
            if total > max_bytes:
                os.remove(tmp.name)
                raise HTTPException(413, f"File exceeds {settings.MAX_FILE_SIZE_MB} MB limit")
            tmp.write(chunk)
        raw_path = tmp.name

    session = VideoSession(
        title=Path(file.filename or "Uploaded video").stem,
        source_type="upload",
        language=language if language != "auto" else "auto",
        status="pending",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    session_id = session.id

    async def _extract_and_run():
        from backend.models.database import SessionLocal
        db2 = SessionLocal()
        try:
            audio_path = extract_audio_from_file(raw_path)
            if os.path.exists(raw_path):
                os.remove(raw_path)
            duration = get_audio_duration(audio_path)
            s = db2.query(VideoSession).filter(VideoSession.id == session_id).first()
            if s and duration:
                s.duration = duration
                db2.commit()
            await _run_pipeline(session_id, audio_path)
        except Exception as exc:
            s = db2.query(VideoSession).filter(VideoSession.id == session_id).first()
            if s:
                s.status = "failed"
                s.error = str(exc)[:500]
                db2.commit()
            await manager.broadcast(session_id, {"event": "error", "error": str(exc)})
        finally:
            db2.close()
            if os.path.exists(raw_path):
                try:
                    os.remove(raw_path)
                except OSError:
                    pass

    asyncio.create_task(_extract_and_run())

    return ProcessResponse(session_id=session_id, status="pending", message="Upload received. Processing started.")


@app.get("/api/status/{session_id}", response_model=StatusResponse)
async def get_status(session_id: str, db: Session = Depends(get_db)):
    session = db.query(VideoSession).filter(VideoSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    return StatusResponse(session_id=session.id, status=session.status, progress=session.progress or 0, stage=session.stage, error=session.error)


@app.get("/api/notes/{session_id}", response_model=NotesResponse)
async def get_notes(session_id: str, db: Session = Depends(get_db)):
    session = db.query(VideoSession).filter(VideoSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    return NotesResponse(**session.to_dict())


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, db: Session = Depends(get_db)):
    from backend.services.rag_engine import answer_question
    session = db.query(VideoSession).filter(VideoSession.id == body.session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if session.status != "completed":
        raise HTTPException(400, "Session is not yet completed")
    result = answer_question(session_id=body.session_id, question=body.message, chat_history=body.history, title=session.title or "")
    db.add(ChatMessage(session_id=body.session_id, role="user", content=body.message))
    db.add(ChatMessage(session_id=body.session_id, role="assistant", content=result["answer"], sources=result.get("sources")))
    db.commit()
    return ChatResponse(answer=result["answer"], sources=result.get("sources", []), session_id=body.session_id)


@app.get("/api/export/{session_id}")
async def export_notes(session_id: str, format: str = Query("markdown", regex="^(markdown|pdf|json)$"), db: Session = Depends(get_db)):
    from backend.services.exporter import export_session
    session = db.query(VideoSession).filter(VideoSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    content, content_type, filename = export_session(session.to_dict(), format)
    return Response(content=content, media_type=content_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/history", response_model=HistoryResponse)
async def get_history(limit: int = Query(20, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    total = db.query(VideoSession).count()
    sessions = db.query(VideoSession).order_by(VideoSession.created_at.desc()).offset(offset).limit(limit).all()
    items = [
        HistoryItem(id=s.id, title=s.title, source_type=s.source_type, source_url=s.source_url, duration=s.duration, status=s.status, created_at=s.created_at.isoformat() if s.created_at else None, thumbnail=s.thumbnail)
        for s in sessions
    ]
    return HistoryResponse(items=items, total=total)


@app.delete("/api/notes/{session_id}")
async def delete_session(session_id: str, db: Session = Depends(get_db)):
    from backend.services.rag_engine import delete_session_index
    session = db.query(VideoSession).filter(VideoSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.delete(session)
    db.commit()
    delete_session_index(session_id)
    return {"message": "Session deleted"}


@app.get("/api/chat/history/{session_id}")
async def get_chat_history(session_id: str, db: Session = Depends(get_db)):
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
    return [{"id": m.id, "role": m.role, "content": m.content, "sources": m.sources, "created_at": m.created_at.isoformat()} for m in messages]


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(ws: WebSocket, session_id: str):
    await manager.connect(session_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(session_id, ws)


FRONTEND_INDEX = FRONTEND_DIR / "index.html"


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if FRONTEND_INDEX.exists():
        return FileResponse(str(FRONTEND_INDEX))
    return {"message": f"{settings.APP_NAME} is running. Visit /docs for the API."}


try:
    from mangum import Mangum
    handler = Mangum(app, lifespan="off")
except ImportError:
    handler = None

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
