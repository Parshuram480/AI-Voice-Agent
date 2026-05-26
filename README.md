# Voice Agent 🎙️

An AI-powered voice agent that handles phone calls via **Twilio**, transcribes speech with **Groq Whisper STT**, processes queries through an **LLM (Llama 3.1)** and **PostgreSQL** database, and responds with **Groq TTS** — all with sub-second latency.

## Architecture

```
📞 Caller → Twilio → /voice (TwiML) → WebSocket /audio-stream
                                             ↓
                                     Audio Buffer (μ-law → PCM)
                                             ↓
                                     Groq STT (Whisper)
                                             ↓
                                     Intent Detection
                                        ↓         ↓
                                   PostgreSQL    Groq LLM
                                        ↓         ↓
                                     Reply Builder
                                             ↓
                                     Groq TTS (PlayAI)
                                             ↓
                                     Twilio <Play> → 📞 Caller
```

## Prerequisites

- **Python 3.11+**
- **PostgreSQL** (optional — the system falls back to in-memory data for testing)
- **ngrok** (optional — for testing with real phone calls)

## Quick Start

### 1. Clone & Setup

```bash
cd Voice-Agent
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
```

### 2. Configure Environment

```bash
copy .env.example .env
# Edit .env with your actual API keys
```

**Required keys:**
| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Your Groq API key (get one at [console.groq.com](https://console.groq.com)) |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID (optional for local testing) |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token (optional for local testing) |
| `DB_PASSWORD` | PostgreSQL password (optional — falls back to in-memory) |

### 3. Database Setup (Optional)

If you have PostgreSQL installed:

```bash
createdb voice_agent
psql -U postgres -d voice_agent -f sql/init.sql
```

If not, the system automatically uses an in-memory store with sample data.

### 4. Run the Server

```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Open the Testing UI

Visit **http://localhost:8000** in your browser.

The console lets you:
- **Simulate a call**: Enter a name, DOB, and query to test the full pipeline
- **Use your microphone**: Click the mic button to record live audio

### Sample Test Data

| Name | DOB | Latest Order |
|---|---|---|
| John Smith | 1990-05-15 | ORD-20260510-002 — Processing |
| Jane Doe | 1985-11-20 | ORD-20260505-003 — Delivered |
| Alice Johnson | 1992-03-08 | ORD-20260512-004 — In Transit |

## Twilio Setup (Real Calls)

1. Start ngrok:
   ```bash
   ngrok http 8000
   ```

2. Copy the HTTPS URL (e.g., `https://abc123.ngrok-free.app`)

3. Update `.env`:
   ```
   SERVER_HOST=https://abc123.ngrok-free.app
   ```

4. In the [Twilio Console](https://console.twilio.com):
   - Go to your phone number's configuration
   - Set the **Voice webhook** to `https://abc123.ngrok-free.app/voice`
   - Method: POST

5. Call your Twilio number!

## Project Structure

```
Voice-Agent/
├── app/
│   ├── __init__.py          # Package init
│   ├── main.py              # FastAPI app, routes, WebSocket
│   ├── config.py            # Settings from .env (python-dotenv)
│   ├── groq_client.py       # GroqClient: STT, LLM, TTS
│   ├── database.py          # DatabaseClient: asyncpg + fallback
│   ├── twilio_handler.py    # TwiML generation, call updates
│   ├── pipeline.py          # VoicePipeline orchestrator
│   └── audio_utils.py       # μ-law decode, resample, WAV build
├── static/
│   ├── index.html           # Testing UI
│   ├── style.css            # Premium dark theme
│   └── app.js               # UI logic + mic recording
├── sql/
│   └── init.sql             # Database schema + sample data
├── audio_cache/             # Generated TTS files (runtime)
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## API Endpoints

| Route | Method | Description |
|---|---|---|
| `/` | GET | Local testing UI |
| `/voice` | POST | Twilio voice webhook (returns TwiML) |
| `/audio-stream` | WebSocket | Twilio media stream receiver |
| `/audio/{filename}` | GET | Serve cached TTS audio files |
| `/api/simulate` | POST | Test: text query → pipeline → audio |
| `/api/mic` | POST | Test: mic audio → pipeline → audio |

## Key Design Decisions

- **Async everywhere**: All I/O is non-blocking (`async`/`await`) for maximum concurrency
- **Streaming LLM**: Chat completions use `stream=True` to begin generating before the full response is ready
- **In-memory fallback**: Works without PostgreSQL for quick local testing
- **Silence detection**: RMS-based end-of-speech detection on μ-law audio chunks
- **HTTP keep-alive**: Groq SDK and httpx sessions are reused across requests

## License

MIT
