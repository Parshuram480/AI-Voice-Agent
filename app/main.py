"""
FastAPI application — main entry point for the Voice-Agent server.

Endpoints:
    GET  /              — Local testing UI
    POST /voice         — Twilio voice webhook (returns TwiML)
    WS   /audio-stream  — Twilio Media Stream WebSocket (streaming pipeline)
    WS   /ws/mic-stream — Browser microphone WebSocket (streaming pipeline)
    GET  /audio/{name}  — Serve cached TTS audio files
    POST /api/simulate  — Local test: text query → audio response
    POST /api/mic       — Local test: microphone audio → audio response (compat)
"""

import asyncio
from typing import Optional
import base64
import json
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)
import audioop
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from app.api import create_api_router
from app.groq_client import GroqClient
from app.database import DatabaseClient
from app.twilio_handler import TwilioHandler
from app.channels.twilio_adapter import TwilioChannelAdapter
from app.pipeline import VoicePipeline
from app.streaming_pipeline import StreamingVoicePipeline, _DONE
from app.intents import IntentRouter, SlotFiller
from app.session import SessionManager, InMemorySessionStore
from app.state_machine import ConversationStateMachine
from app.repositories import CustomerRepository, OrderRepository
from app.services import AgentService, VerificationService, OrderService
from app.llm import LLMRephraser
from app.audio_utils import (
    mulaw_to_pcm,
    resample_to_16khz,
    wav_bytes_to_pcm,
    to_mono,
    resample_pcm,
)

# =============================================================================
# Logging
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
SERVER_HOST = os.getenv("SERVER_HOST", "http://localhost:8000")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
TWILIO_STREAM_AUDIO_OUT = os.getenv("TWILIO_STREAM_AUDIO_OUT", "true").lower() in ("1", "true", "yes", "on")


# =============================================================================
# Application
# =============================================================================
app = FastAPI(
    title="Voice Agent",
    description="AI-powered voice agent with Twilio + Groq — streaming low-latency pipeline",
    version="2.0.0",
)


def _get_pipeline() -> VoicePipeline:
    return pipeline


def _get_streaming_pipeline() -> StreamingVoicePipeline:
    return streaming_pipeline


app.include_router(create_api_router(_get_pipeline, _get_streaming_pipeline))

# Shared service instances (initialized on startup)
groq_client_1: GroqClient = None  # type: ignore
groq_client_2: GroqClient = None  # type: ignore
cartesia_client = None
db_client: DatabaseClient = None  # type: ignore
twilio_handler: TwilioHandler = None  # type: ignore
pipeline: VoicePipeline = None  # type: ignore
streaming_pipeline: StreamingVoicePipeline = None  # type: ignore
session_manager: SessionManager = None  # type: ignore
agent_service: AgentService = None  # type: ignore
rephraser: LLMRephraser = None  # type: ignore

# =============================================================================
# Startup / Shutdown
# =============================================================================
@app.on_event("startup")
async def startup():
    """Initialize all services on server startup."""
    global groq_client_1, groq_client_2, cartesia_client, db_client, twilio_handler, pipeline, streaming_pipeline
    global session_manager, agent_service, rephraser

    logger.info("=" * 60)
    logger.info("  Voice Agent v2 — Streaming Pipeline — Starting up")
    logger.info("=" * 60)

    # Initialize Groq clients
    groq_client_1 = GroqClient(
        api_key=os.getenv("GROQ_LLM1_API_KEY") or os.getenv("GROQ_API_KEY"),
        default_model=os.getenv("LLM1_MODEL")
    )
    groq_client_2 = GroqClient(
        api_key=os.getenv("GROQ_LLM2_API_KEY") or os.getenv("GROQ_API_KEY"),
        default_model=os.getenv("LLM2_MODEL")
    )
    logger.info("✓ Groq clients initialized")

    # Warm up Groq connections (pre-establish TLS)
    await groq_client_1.warmup()
    await groq_client_2.warmup()
    logger.info("✓ Groq connections warmed up")

    # Initialize Cartesia client if configured
    tts_provider = os.getenv("TTS_PROVIDER", "groq").lower()
    if tts_provider == "cartesia":
        from app.cartesia_client import CartesiaClient
        cartesia_client = CartesiaClient()
        logger.info("✓ Cartesia client initialized")

    # Initialize database
    db_client = DatabaseClient()
    await db_client.connect()
    logger.info("✓ Database client initialized")

    # Initialize Twilio handler
    twilio_handler = TwilioHandler()
    logger.info("✓ Twilio handler initialized")

    # Initialize conversation orchestration
    session_store = InMemorySessionStore()
    session_manager = SessionManager(session_store)
    intent_router = IntentRouter()
    slot_filler = SlotFiller()
    state_machine = ConversationStateMachine()
    customer_repo = CustomerRepository(db_client)
    order_repo = OrderRepository(db_client)
    verification_service = VerificationService(customer_repo)
    order_service = OrderService(order_repo)
    agent_service = AgentService(
        session_manager=session_manager,
        groq_client_1=groq_client_1,
        groq_client_2=groq_client_2,
        verification_service=verification_service,
        order_service=order_service,
    )
    rephraser = LLMRephraser(groq_client_1)
    logger.info("✓ Conversation orchestration initialized")

    # Initialize legacy pipeline (for text simulation)
    pipeline = VoicePipeline(groq_client_1, db_client, twilio_handler, agent_service, rephraser)
    logger.info("✓ Legacy voice pipeline initialized")

    pipeline_mode = os.getenv("PIPELINE_MODE", "cascade").lower()
    
    if pipeline_mode == "multimodal":
        from app.gemini_live_client import GeminiLiveClient
        from app.multimodal_pipeline import GeminiLivePipeline
        gemini_client = GeminiLiveClient(verification_service, order_service)
        streaming_pipeline = GeminiLivePipeline(gemini_client)
        logger.info("✓ Multimodal (Gemini Live) pipeline initialized")
    else:
        # Initialize streaming pipeline
        streaming_pipeline = StreamingVoicePipeline(
            groq_client_1,
            db_client,
            twilio_handler,
            agent_service,
            rephraser,
            cartesia_client=cartesia_client,
        )
        logger.info("✓ Streaming voice pipeline initialized")

    logger.info(f"  Pipeline Mode: {pipeline_mode}")
    logger.info(f"  Server host: {SERVER_HOST}")
    logger.info(f"  Listening on port: {SERVER_PORT}")
    logger.info("=" * 60)

    # Start LiveKit worker in background if credentials are set
    if os.getenv("LIVEKIT_URL") and os.getenv("LIVEKIT_API_KEY") and os.getenv("LIVEKIT_API_SECRET"):
        from app.livekit_agent import start_livekit_worker
        asyncio.create_task(start_livekit_worker())
        logger.info("✓ LiveKit agent worker started in background")


@app.on_event("shutdown")
async def shutdown():
    """Clean up resources on server shutdown."""
    logger.info("Shutting down...")
    if groq_client_1:
        await groq_client_1.close()
    if groq_client_2:
        await groq_client_2.close()
    if db_client:
        await db_client.close()
    logger.info("Shutdown complete.")


# =============================================================================
# Static Files
# =============================================================================
# Mount the static directory for the testing UI
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# =============================================================================
# Routes
# =============================================================================

# ---- LiveKit Token Endpoint ----
@app.get("/api/livekit/token")
async def livekit_token(session_id: Optional[str] = None):
    """
    Generate an access token for a LiveKit WebRTC room session.
    """
    from livekit import api
    
    room_name = session_id or f"room-{uuid.uuid4().hex[:8]}"
    identity = f"user-{uuid.uuid4().hex[:6]}"
    
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    livekit_url = os.getenv("LIVEKIT_URL")
    
    if not all([api_key, api_secret, livekit_url]):
        return Response(
            content=json.dumps({"error": "LiveKit credentials not configured"}),
            status_code=500,
            media_type="application/json"
        )
        
    try:
        token = api.AccessToken(api_key, api_secret) \
            .with_identity(identity) \
            .with_name(identity) \
            .with_grants(api.VideoGrants(
                room_join=True,
                room=room_name,
            ))
        
        jwt_token = token.to_jwt()
        return {
            "token": jwt_token,
            "url": livekit_url,
            "room": room_name,
            "identity": identity
        }
    except Exception as e:
        logger.exception("Failed to generate LiveKit token")
        return Response(
            content=json.dumps({"error": str(e)}),
            status_code=500,
            media_type="application/json"
        )


# ---- Local Testing UI ----
@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the local testing UI."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>Voice Agent</h1><p>Static files not found. Place index.html in /static/</p>"
    )


# ---- Twilio Voice Webhook ----
@app.post("/voice")
async def voice_webhook(request: Request):
    """
    Twilio voice webhook — called when a phone call comes in.

    Returns TwiML that starts a media stream and greets the caller.
    """
    # Build the WebSocket URL dynamically based on the incoming request host
    # If the request comes through ngrok (https), we use wss://
    scheme = "wss" if request.url.scheme == "https" or "ngrok" in request.url.hostname else "ws"
    ws_url = f"{scheme}://{request.url.hostname}/audio-stream"
    if request.url.port and request.url.port not in (80, 443):
        ws_url = f"{scheme}://{request.url.hostname}:{request.url.port}/audio-stream"

    twiml = twilio_handler.generate_stream_twiml(ws_url)
    logger.info(f"Voice webhook called — streaming to {ws_url}")

    return Response(content=twiml, media_type="application/xml")


# ---- Twilio Media Stream WebSocket (STREAMING PIPELINE) ----
@app.websocket("/audio-stream")
async def audio_stream(websocket: WebSocket):
    """
    WebSocket endpoint for Twilio Media Streams.

    Receives real-time μ-law audio from Twilio, feeds chunks into the
    streaming pipeline (STT → LLM → TTS running concurrently).
    """
    await websocket.accept()
    logger.info("Twilio audio stream WebSocket connected")

    stream_sid = None
    call_sid = None
    audio_queue: asyncio.Queue = asyncio.Queue()
    pipeline_task = None
    use_stream_audio_out = TWILIO_STREAM_AUDIO_OUT
    stream_audio_sent = False
    twilio_adapter = None

    def on_tts_audio(audio_bytes: bytes):
        nonlocal stream_audio_sent
        if not use_stream_audio_out or not twilio_adapter:
            return
        asyncio.create_task(twilio_adapter.send_audio(audio_bytes))
        stream_audio_sent = True

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            event = data.get("event")

            if event == "connected":
                logger.info(f"Twilio stream connected: {data.get('protocol', 'unknown')}")

            elif event == "start":
                stream_sid = data.get("start", {}).get("streamSid")
                call_sid = data.get("start", {}).get("callSid")
                logger.info(f"Stream started — streamSid={stream_sid}, callSid={call_sid}")

                # Instantiate adapter
                twilio_adapter = TwilioChannelAdapter(
                    twilio_handler=twilio_handler,
                    websocket=websocket,
                    stream_sid=stream_sid,
                    call_sid=call_sid
                )

                # Launch the streaming pipeline in the background
                pipeline_task = asyncio.create_task(
                    streaming_pipeline.process_stream(
                        audio_queue=audio_queue,
                        call_sid=call_sid,
                        on_tts_audio=on_tts_audio if use_stream_audio_out else None,
                        update_call_with_audio=not use_stream_audio_out,
                        session_id=call_sid,
                        channel_adapter=twilio_adapter,
                    )
                )

            elif event == "media":
                # Decode base64 μ-law audio → PCM → 16kHz
                payload = data.get("media", {}).get("payload", "")
                if payload:
                    chunk_bytes = base64.b64decode(payload)
                    pcm_chunk = mulaw_to_pcm(chunk_bytes)
                    pcm_16k = resample_to_16khz(pcm_chunk)
                    await audio_queue.put(pcm_16k)

            elif event == "stop":
                logger.info("Twilio stream stopped")
                # Signal end-of-audio to the pipeline
                await audio_queue.put(_DONE)
                break

    except WebSocketDisconnect:
        logger.info("Twilio audio stream WebSocket disconnected")
        await audio_queue.put(_DONE)
    except Exception as e:
        logger.exception(f"Twilio audio stream error: {e}")
        await audio_queue.put(_DONE)
    finally:
        # Wait for the pipeline to complete
        if pipeline_task:
            try:
                result = await asyncio.wait_for(pipeline_task, timeout=30.0)
                if use_stream_audio_out and call_sid and result.get("audio_url") and not stream_audio_sent:
                    await twilio_handler.update_call_with_audio(call_sid, result["audio_url"])
                logger.info(f"Twilio pipeline result: {result.get('reply_text', '')[:80]}")
            except asyncio.TimeoutError:
                logger.error("Twilio pipeline timed out")
                pipeline_task.cancel()
            except Exception as e:
                logger.error(f"Twilio pipeline error: {e}")
        logger.info("Twilio audio stream WebSocket closed")


# ---- Browser Microphone WebSocket (CONTINUOUS CONVERSATION) ----
@app.websocket("/ws/mic-stream")
async def mic_stream(websocket: WebSocket):
    """
    WebSocket endpoint for browser microphone streaming.

    Upgraded to continuous conversation mode:
      - User clicks mic ONCE to start a session
      - Audio streams continuously
      - VAD detects utterance boundaries automatically
      - Each utterance is processed through STT → LLM → TTS
      - Listening resumes automatically after TTS playback
      - Session ends when user clicks "End Conversation" or disconnects

    Messages sent to client:
      - {"type": "phase", "phase": "LISTENING|SPEECH_DETECTED|..."}
      - {"type": "stage", "stage": "...", "status": "...", "detail": "..."}
      - {"type": "stt", "text": "..."}
      - {"type": "llm_token", "token": "..."}
      - {"type": "tts_audio", "data": "<base64>", "index": N}
      - {"type": "timing", "timings": {...}}
      - {"type": "turn_done", "result": {...}}
      - {"type": "session_end", "total_turns": N}
    """
    await websocket.accept()
    logger.info("Browser mic-stream WebSocket connected (continuous mode)")

    audio_queue: asyncio.Queue = asyncio.Queue()
    ws_open = True
    barge_in_event = asyncio.Event()

    ws_send_queue: asyncio.Queue = asyncio.Queue()

    async def ws_sender():
        nonlocal ws_open
        while ws_open:
            msg = await ws_send_queue.get()
            if msg is None:
                break
            try:
                if ws_open:
                    await websocket.send_json(msg)
            except Exception:
                ws_open = False
            finally:
                ws_send_queue.task_done()

    sender_task = asyncio.create_task(ws_sender())

    def safe_send_sync(msg: dict):
        if ws_open:
            ws_send_queue.put_nowait(msg)

    async def safe_send(msg: dict):
        safe_send_sync(msg)

    # Callbacks for the streaming pipeline
    audio_chunk_index = 0

    def on_stt_text(text: str):
        safe_send_sync({"type": "stt", "text": text})

    def on_llm_token(token: str):
        safe_send_sync({"type": "llm_token", "token": token})

    def on_tts_audio(audio_bytes: bytes):
        nonlocal audio_chunk_index
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        sample_rate = 24000
        
        audio_format = "pcm"
        if audio_bytes.startswith(b"RIFF"):
            audio_format = "wav"
        elif audio_bytes.startswith(b"ID3") or audio_bytes.startswith(b"\xff\xfb"):
            audio_format = "mp3"

        safe_send_sync({
            "type": "tts_audio",
            "data": b64,
            "index": audio_chunk_index,
            "sampleRate": sample_rate,
            "format": audio_format,
        })
        audio_chunk_index += 1

    def on_stage(stage: str, status: str, detail: str = ""):
        safe_send_sync({
            "type": "stage",
            "stage": stage,
            "status": status,
            "detail": detail,
        })

    def on_phase_change(phase: str):
        safe_send_sync({"type": "phase", "phase": phase})

    def on_turn_done(result: dict):
        nonlocal audio_chunk_index
        # Reset audio chunk index for next turn
        audio_chunk_index = 0
        # Send turn result (strip non-serializable fields)
        send_result = {
            k: v for k, v in result.items()
            if k != "audio_bytes"
        }
        safe_send_sync({
            "type": "timing",
            "timings": result.get("timings", {}),
        })
        safe_send_sync({
            "type": "turn_done",
            "result": send_result,
        })

    # Session ID management
    session_id = websocket.query_params.get("session_id")
    if not session_id:
        session_id = f"mic-{uuid.uuid4().hex[:8]}"
    await safe_send({"type": "session", "session_id": session_id})

    # Launch the continuous conversation pipeline in background
    pipeline_task = asyncio.create_task(
        streaming_pipeline.process_continuous(
            audio_queue=audio_queue,
            on_stt_text=on_stt_text,
            on_llm_token=on_llm_token,
            on_tts_audio=on_tts_audio,
            on_stage=on_stage,
            on_phase_change=on_phase_change,
            on_turn_done=on_turn_done,
            session_id=session_id,
            barge_in_event=barge_in_event,
            langsmith_extra={"metadata": {"session_id": session_id, "thread_id": session_id}},
        )
    )

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            # Binary frames = raw PCM audio
            if "bytes" in message and message["bytes"]:
                await audio_queue.put(message["bytes"])

            # Text frames = control messages
            elif "text" in message and message["text"]:
                try:
                    ctrl = json.loads(message["text"])
                    action = ctrl.get("action")

                    if action == "stop" or action == "end_session":
                        logger.info(f"Browser mic-stream: {action} received")
                        await audio_queue.put(_DONE)
                        break

                    elif action == "barge_in":
                        # Only interrupt if the agent is actively speaking
                        if getattr(streaming_pipeline, "_current_phase", None) == "SPEAKING":
                            logger.info("Browser mic-stream: barge-in signal received")
                            barge_in_event.set()
                            # Reset after a short delay
                            asyncio.get_event_loop().call_later(
                                0.1, barge_in_event.clear
                            )

                except json.JSONDecodeError:
                    pass

    except WebSocketDisconnect:
        logger.info("Browser mic-stream WebSocket disconnected")
    except Exception as e:
        logger.exception(f"Browser mic-stream error: {e}")
    finally:
        # Ensure the pipeline knows audio is done
        try:
            audio_queue.put_nowait(_DONE)
        except Exception:
            pass

        # Wait for pipeline completion
        try:
            result = await asyncio.wait_for(pipeline_task, timeout=30.0)
            if ws_open:
                await safe_send({
                    "type": "session_end",
                    "total_turns": result.get("total_turns", 0),
                })
        except asyncio.TimeoutError:
            logger.error("Browser mic-stream pipeline timed out")
            pipeline_task.cancel()
        except Exception as e:
            logger.error(f"Browser mic-stream pipeline error: {e}")

        logger.info("Browser mic-stream WebSocket closed")
        if session_id:
            await session_manager.delete(session_id)


# =============================================================================
# Run with: uvicorn app.main:app --reload --port 8000
# =============================================================================
