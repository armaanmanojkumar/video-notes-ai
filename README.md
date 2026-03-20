# VideoNotes AI

Turn any YouTube video, lecture, or meeting recording into organized notes, timestamped chapters, action items, and an AI-powered Q&A assistant.

## Features

- Speech-to-Text via Groq Whisper large-v3
- AI Summarization via LLaMA 3.3 70B
- Chapter Detection
- Key Timestamp Extraction
- Action Item Extraction with priorities
- RAG Q&A Chat using ChromaDB and sentence-transformers
- Export to Markdown, PDF, or JSON
- Persistent storage with SQLite or PostgreSQL
- Real-time progress via WebSocket
- YouTube and file upload support

## Quick Start

### Requirements

- Python 3.10+
- ffmpeg installed on your system
- A free Groq API key from https://console.groq.com

### Setup

git clone https://github.com/armaanmanojkumar/video-notes-ai.git
cd video-notes-ai

python -m venv .venv
.venv\Scripts\activate      

pip install -r requirements.txt

copy .env.example .env      

mkdir backend\uploads backend\chroma_db

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload


Open http://localhost:8000

## Project Structure


video-notes-ai/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── models/
│   │   ├── database.py
│   │   └── schemas.py
│   ├── services/
│   │   ├── video_processor.py
│   │   ├── transcriber.py
│   │   ├── analyzer.py
│   │   ├── rag_engine.py
│   │   └── exporter.py
│   └── utils/
│       └── static_helper.py
├── frontend/
│   └── index.html
├── tests/
│   └── test_api.py
├── .env.example
├── requirements.txt
└── vercel.json


## Deploy to Vercel


npm install -g vercel
vercel login
vercel


Then add GROQ_API_KEY in your Vercel project settings under Environment Variables.

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/process/url | Process a YouTube or video URL |
| POST | /api/process/upload | Process an uploaded file |
| GET | /api/status/{id} | Poll processing status |
| GET | /api/notes/{id} | Get completed notes |
| POST | /api/chat | RAG Q&A over a session |
| GET | /api/export/{id} | Export notes as markdown, pdf, or json |
| GET | /api/history | List past sessions |
| DELETE | /api/notes/{id} | Delete a session |
| WS | /ws/{id} | Real-time progress WebSocket |

## Tech Stack

- FastAPI
- Groq (Whisper + LLaMA 3.3 70B)
- ChromaDB
- sentence-transformers
- SQLAlchemy
- yt-dlp
- ReportLab
