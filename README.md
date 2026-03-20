
<img width="1908" height="911" alt="Screenshot 2026-03-20 155037" src="https://github.com/user-attachments/assets/33edfbbb-2264-43c6-bf83-dcfcfee3326b" />
<img width="1908" height="911" alt="Screenshot 2026-03-20 155037" src="https://github.com/user-attachments/assets/aeb13603-e91f-4804-b63f-5e1c0fa04f35" />
<img width="525" height="670" alt="Screenshot 2026-03-20 155027" src="https://github.com/user-attachments/assets/4c1cceaa-4ec7-4f9e-8982-ffd393c39909" />
<img width="1681" height="559" alt="Screenshot 2026-03-20 155009" src="https://github.com/user-attachments/assets/2ede0d50-f8d2-4f84-932d-a252502e00c4" />
<img width="1751" height="297" alt="Screenshot 2026-03-20 155004" src="https://github.com/user-attachments/assets/a9e6524e-e908-4cd9-990b-b4005f04ec2b" />
<img width="1658" height="773" alt="Screenshot 2026-03-20 154954" src="https://github.com/user-attachments/assets/0bdf43ba-ddb7-41e0-8554-a9095c90caa4" />
<img width="1871" height="600" alt="Screenshot 2026-03-20 154947" src="https://github.com/user-attachments/assets/ad4311ff-6b09-416b-a92c-59f6903dadb9" />
<img width="1907" height="924" alt="Screenshot 2026-03-20 154937" src="https://github.com/user-attachments/assets/5b8288c5-5c2e-41d5-aaf6-c12cf708a652" />

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
