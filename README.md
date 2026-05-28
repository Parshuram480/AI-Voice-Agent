# Voice Agent 🎙️

An AI-powered voice agent that handles phone calls via **Twilio**, transcribes speech with **Groq Whisper STT**, routes intent with a deterministic **state machine + session memory**, queries **PostgreSQL** safely, and responds with **Groq TTS** — all with sub-second latency.

## Architecture

```
📞 Caller → Twilio → /voice (TwiML) → WebSocket /audio-stream
       (or Web UI → WebSocket /ws/mic-stream)
                                             ↓
                                     Continuous VAD
                               (Speech detection & Endpointing)
                                             ↓
                                     Audio Buffer (PCM)
                                             ↓
                                     Groq STT (Whisper)
                                             ↓
                           Conversation Service (state machine)
                         intent router + slot filling + session
                                             ↓
                           Verification + Repositories (SQL-safe)
                                             ↓
                         Response Builder (deterministic)
                               (optional LLM rephrase)
                                             ↓
                                     Groq TTS (PlayAI)
                                             ↓
                                     Twilio <Play> → 📞 Caller
                                     (or Web UI Player)
```

**Key Capabilities:**
- **Continuous Turn-Taking:** The user only starts the microphone once. The system handles continuous listening and automatic turn progression.
- **Voice Activity Detection (VAD):** Energy-based VAD automatically detects speech start and endpoints based on silence duration.
- **Barge-in / Interruption:** Users can interrupt the agent while it is speaking, immediately stopping TTS playback and resuming listening.

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
│   ├── api/                 # FastAPI route modules
│   ├── intents/             # Intent router + slot filler
│   ├── llm/                 # Controlled rephrase helper
│   ├── logging/             # Structured logging helpers
│   ├── models/              # Session + response models
│   ├── observability/       # Latency metrics
│   ├── repositories/        # SQL-safe repositories
│   ├── schemas/             # Request schemas
│   ├── services/            # Conversation + verification + order services
│   ├── session/             # Session store + manager
│   ├── state_machine/       # Conversation state machine
│   ├── main.py              # FastAPI app, routes, WebSocket
│   ├── config.py            # Settings from .env (python-dotenv)
│   ├── groq_client.py       # GroqClient: STT, LLM, TTS
│   ├── database.py          # DatabaseClient: asyncpg + fallback
│   ├── pipeline.py          # VoicePipeline orchestrator
│   ├── streaming_pipeline.py# Low-latency streaming pipeline
│   ├── twilio_handler.py    # TwiML generation, call updates
│   └── audio_utils.py       # μ-law decode, resample, WAV build
├── static/
│   ├── index.html           # Testing UI
│   ├── style.css            # Premium dark theme
│   └── app.js               # UI logic + mic recording
├── Docs/
│   ├── architecture.md      # Architecture explanation
│   ├── diagrams.md          # Sequence + flow diagrams
│   ├── latency-notes.md     # Latency optimization notes
│   └── setup.md             # Developer setup guide
├── sql/
│   └── init.sql             # Database schema + sample data
├── tests/                   # Pytest coverage
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

- **Continuous Conversational Turn-Taking**: Persistent WebSocket loop allows natural multi-turn conversations without manual interaction.
- **Voice Activity Detection (VAD)**: Energy-based silence detection for automatic endpointing and turn-taking.
- **Barge-in Support**: Users can interrupt the agent at any point during playback.
- **Async everywhere**: All I/O is non-blocking (`async`/`await`) for maximum concurrency.
- **Deterministic control**: State machine, rule-based intents, and slot filling drive logic.
- **Controlled LLM usage**: LLM is optional and only rephrases deterministic responses.
- **In-memory fallback**: Works without PostgreSQL for quick local testing.
- **Structured logging**: Session-aware logging with latency metrics and turn-by-turn tracing.
- **HTTP keep-alive**: Groq SDK and httpx sessions are reused across requests.

## Testing

```bash
pytest
```

## Docs

- [Docs/architecture.md](Docs/architecture.md)
- [Docs/diagrams.md](Docs/diagrams.md)
- [Docs/setup.md](Docs/setup.md)
- [Docs/latency-notes.md](Docs/latency-notes.md)

## License

MIT
