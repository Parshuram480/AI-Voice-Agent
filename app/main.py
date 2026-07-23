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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from app.api import create_api_router
from app.groq_client import GroqClient
from app.database import DatabaseClient
from app.twilio_handler import TwilioHandler
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
app.state.last_active_client_id = None

# Add CORS Middleware to support decoupled React-TS frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Globally track websocket listener connections for session synchronization
active_listeners: dict[str, list[WebSocket]] = {}

async def broadcast_to_listeners(session_id: str, message: dict):
    if session_id in active_listeners:
        disconnected = []
        for ws in active_listeners[session_id]:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            try:
                active_listeners[session_id].remove(ws)
            except Exception:
                pass


def _get_pipeline() -> VoicePipeline:
    return pipeline


def _get_streaming_pipeline() -> StreamingVoicePipeline:
    return streaming_pipeline


def _get_twilio_handler() -> TwilioHandler:
    return twilio_handler


app.include_router(create_api_router(_get_pipeline, _get_streaming_pipeline, _get_twilio_handler))

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
        from app.multimodal_pipeline import GeminiLivePipeline

        # Instantiate pipeline
        streaming_pipeline = GeminiLivePipeline(
            verification_service,
            order_service,
            db_client
        )
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

# ---- API Root Status ----
@app.get("/")
async def root():
    """Returns the API service status."""
    return {"status": "ok", "service": "AI Voice Agent SaaS API Server"}


# ---- Twilio Voice Webhook ----
@app.post("/voice")
async def voice_webhook(request: Request):
    """
    Twilio voice webhook — called when a phone call comes in.

    Returns TwiML that starts a media stream and greets the caller.
    """
    # Extract client_id from query parameter if present
    client_id = request.query_params.get("client_id")
    if not client_id or client_id == "None":
        client_id = getattr(request.app.state, "last_active_client_id", None)
        if client_id:
            client_id = str(client_id)
    logger.info(f"[VOICE WEBHOOK] Resolved client_id: {client_id}")
    
    # Build the WebSocket URL dynamically based on the incoming request host
    # If the request comes through ngrok (https), we use wss://
    scheme = "wss" if request.url.scheme == "https" or "ngrok" in request.url.hostname else "ws"
    ws_url = f"{scheme}://{request.url.hostname}/audio-stream"
    if request.url.port and request.url.port not in (80, 443):
        ws_url = f"{scheme}://{request.url.hostname}:{request.url.port}/audio-stream"

    if client_id:
        ws_url += f"?client_id={client_id}"

    twiml = twilio_handler.generate_stream_twiml(ws_url)
    logger.info(f"Voice webhook called — streaming to {ws_url}")

    return Response(content=twiml, media_type="application/xml")


@app.websocket("/audio-stream")
async def audio_stream(websocket: WebSocket):
    """
    WebSocket endpoint for Twilio Media Streams.

    Receives real-time μ-law audio from Twilio, feeds chunks into the
    streaming pipeline (STT → LLM → TTS running concurrently).
    """
    await websocket.accept()
    logger.info("Twilio audio stream WebSocket connected")

    client_id_str = websocket.query_params.get("client_id")
    logger.info(f"[AUDIO STREAM WS] Raw client_id_str from ws query params: {client_id_str}")
    client_id = None
    if client_id_str and client_id_str != "None":
        try:
            client_id = int(client_id_str)
        except ValueError:
            logger.error(f"[AUDIO STREAM WS] ValueError converting client_id_str to int: {client_id_str}")
            pass
            
    if client_id is None:
        client_id = getattr(websocket.app.state, "last_active_client_id", None)
        logger.info(f"[AUDIO STREAM WS] Fallback resolved client_id: {client_id}")

    logger.info(f"[AUDIO STREAM WS] Resolved client_id: {client_id}")

    stream_sid = None
    call_sid = None
    audio_queue: asyncio.Queue = asyncio.Queue()
    outbound_audio_queue: asyncio.Queue = asyncio.Queue()
    pipeline_task = None
    use_stream_audio_out = TWILIO_STREAM_AUDIO_OUT
    stream_audio_sent = False
    outbound_task = None

    async def _outbound_audio_loop():
        nonlocal stream_audio_sent, stream_sid, call_sid
        resample_state = None
        logger.info("[OUTBOUND LOOP] Started outbound audio stream task")
        while True:
            audio_item = await outbound_audio_queue.get()
            if audio_item is None:
                logger.info("[OUTBOUND LOOP] Received Sentinel None, stopping outbound task")
                break
                
            if audio_item == "CLEAR":
                logger.info("[OUTBOUND LOOP] Clear signal received. Flushing pending audio.")
                while not outbound_audio_queue.empty():
                    try:
                        outbound_audio_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                # Reset resample state so the new audio stream doesn't click
                resample_state = None
                continue
                
            if not stream_sid:
                logger.warning("[OUTBOUND LOOP] stream_sid is not yet set, discarding chunk")
                continue

            try:
                if isinstance(audio_item, tuple):
                    # Direct PCM tuple: (pcm_bytes, sample_rate)
                    pcm_bytes, sample_rate = audio_item
                    sample_width = 2
                    channels = 1
                else:
                    # Legacy WAV bytes (from Cartesia etc)
                    wav_bytes = audio_item
                    pcm_bytes, sample_rate, sample_width, channels = wav_bytes_to_pcm(wav_bytes)
                    if not pcm_bytes:
                        continue
                        
                # Ensure pcm_bytes is a whole number of frames to prevent audioop crash
                if len(pcm_bytes) % sample_width != 0:
                    pcm_bytes += b'\x00' * (sample_width - (len(pcm_bytes) % sample_width))

                if sample_width != 2:
                    pcm_bytes = audioop.lin2lin(pcm_bytes, sample_width, 2)
                    sample_width = 2

                pcm_bytes = to_mono(pcm_bytes, sample_width=sample_width, channels=channels)
                if sample_rate != 8000:
                    # Maintain state across chunks to prevent static/clicks
                    pcm_bytes, resample_state = audioop.ratecv(
                        pcm_bytes,
                        sample_width,
                        1,
                        sample_rate,
                        8000,
                        resample_state,
                    )

                ok = await twilio_handler.send_audio_to_stream(websocket, pcm_bytes, stream_sid)
                if ok:
                    stream_audio_sent = True
                    logger.info(f"[OUTBOUND LOOP] Successfully sent {len(pcm_bytes)} bytes to Twilio.")
            except Exception as e:
                logger.error(f"CRITICAL ERROR in _outbound_audio_loop: {e}")
                import traceback
                traceback.print_exc()

    def on_tts_audio(audio_data):
        if not use_stream_audio_out:
            return
        outbound_audio_queue.put_nowait(audio_data)

    def on_stt_text(text: str):
        logger.info(f"Twilio Call STT: {text}")
        if call_sid:
            asyncio.create_task(broadcast_to_listeners(call_sid, {"type": "stt", "text": text}))

    def on_llm_token(token: str):
        if call_sid:
            asyncio.create_task(broadcast_to_listeners(call_sid, {"type": "llm_token", "token": token}))

    def on_stage(stage: str, status: str, detail: str = ""):
        if call_sid:
            asyncio.create_task(broadcast_to_listeners(call_sid, {
                "type": "stage",
                "stage": stage,
                "status": status,
                "detail": detail
            }))

    def on_phase_change(phase: str):
        if call_sid:
            val = phase.value if hasattr(phase, 'value') else phase
            asyncio.create_task(broadcast_to_listeners(call_sid, {"type": "phase", "phase": val}))

    def on_turn_done(result: dict):
        if call_sid:
            send_result = {k: v for k, v in result.items() if k != "audio_bytes"}
            asyncio.create_task(broadcast_to_listeners(call_sid, {"type": "timing", "timings": result.get("timings", {})}))
            asyncio.create_task(broadcast_to_listeners(call_sid, {"type": "turn_done", "result": send_result}))

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

                # Seeding the session state with client_id
                await session_manager.get_or_create(call_sid, client_id=client_id)

                if use_stream_audio_out and not outbound_task:
                    outbound_task = asyncio.create_task(_outbound_audio_loop())

                dynamic_kwargs = {}
                if client_id:
                    try:
                        from app.system_database import SystemDatabase
                        sys_db = SystemDatabase()
                        client_mapping = await sys_db.get_client_domain_mapping(client_id)
                        if client_mapping and client_mapping.get("dynamic_config"):
                            dyn_cfg = json.loads(client_mapping["dynamic_config"])
                            db_config = await sys_db.get_client_db_config(client_id)
                            if db_config:
                                dyn_cfg["database"] = db_config
                                dyn_cfg["domain"] = client_mapping.get("domain_name", "default")
                                
                                from app.services.schema_service import SchemaService
                                from app.services.dynamic_tool_factory import DynamicToolFactory
                                from app.services.dynamic_tool_executor import DynamicToolExecutor
                                from app.services.dynamic_prompt_assembler import DynamicPromptAssembler
                                
                                schema_service = SchemaService(db_config)
                                schema_metadata = await schema_service.get_schema_metadata()
                                
                                tool_factory = DynamicToolFactory(dyn_cfg, schema_metadata)
                                tools, exec_map = tool_factory.generate_tools()
                                
                                from app.dynamic_db_client import DynamicDbClient
                                dyn_db_client = DynamicDbClient(db_config)
                                
                                executor = DynamicToolExecutor(
                                    dyn_db_client, 
                                    exec_map, 
                                    dyn_cfg["identity"]["table"],
                                    dyn_cfg["identity"]["name_column"],
                                    dyn_cfg["identity"]["verification_column"]
                                )
                                prompt = DynamicPromptAssembler.assemble(dyn_cfg, schema_metadata, tools)
                                dynamic_kwargs = {
                                    "dynamic_tools": tools,
                                    "dynamic_executor": executor,
                                    "system_prompt": prompt,
                                    "domain": dyn_cfg["domain"]
                                }
                                logger.info(f"[{call_sid}] Configured dynamic tools for client {client_id}")
                    except Exception as e:
                        logger.error(f"[{call_sid}] Error loading dynamic config for client {client_id}: {e}")

                # Launch the streaming pipeline in the background
                pipeline_task = asyncio.create_task(
                    streaming_pipeline.process_stream(
                        audio_queue=audio_queue,
                        call_sid=call_sid,
                        on_stt_text=on_stt_text,
                        on_llm_token=on_llm_token,
                        on_tts_audio=on_tts_audio if use_stream_audio_out else None,
                        on_stage=on_stage,
                        on_phase_change=on_phase_change,
                        on_turn_done=on_turn_done,
                        update_call_with_audio=not use_stream_audio_out,
                        session_id=call_sid,
                        twilio_ws=websocket,
                        stream_sid=stream_sid,
                        **dynamic_kwargs
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
                outbound_audio_queue.put_nowait(None)
                break

    except WebSocketDisconnect:
        logger.info("Twilio audio stream WebSocket disconnected")
        await audio_queue.put(_DONE)
        outbound_audio_queue.put_nowait(None)
    except Exception as e:
        logger.exception(f"Twilio audio stream error: {e}")
        await audio_queue.put(_DONE)
        outbound_audio_queue.put_nowait(None)
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
        
    client_id_str = websocket.query_params.get("client_id")
    client_id = None
    if client_id_str and client_id_str != "null" and client_id_str != "undefined":
        try:
            client_id = int(client_id_str)
        except ValueError:
            pass

    # Pre-seed session state with client_id
    await session_manager.get_or_create(session_id, client_id=client_id)

    await safe_send({"type": "session", "session_id": session_id})

    listener_str = websocket.query_params.get("listener", "false")
    is_listener = listener_str.lower() == "true"
    if is_listener:
        if session_id not in active_listeners:
            active_listeners[session_id] = []
        active_listeners[session_id].append(websocket)
        logger.info(f"Websocket listener registered for session {session_id}")
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if "text" in message and message["text"]:
                    ctrl = json.loads(message["text"])
                    if ctrl.get("action") == "end_session":
                        break
        except Exception:
            pass
        finally:
            if session_id in active_listeners and websocket in active_listeners[session_id]:
                active_listeners[session_id].remove(websocket)
            logger.info(f"Websocket listener disconnected for session {session_id}")
            return

    dynamic_kwargs = {}
    if client_id:
        try:
            from app.system_database import SystemDatabase
            sys_db = SystemDatabase()
            client_mapping = await sys_db.get_client_domain_mapping(client_id)
            if client_mapping and client_mapping.get("dynamic_config"):
                import json
                dyn_cfg = json.loads(client_mapping["dynamic_config"])
                db_config = await sys_db.get_client_db_config(client_id)
                if db_config:
                    dyn_cfg["database"] = db_config
                    dyn_cfg["domain"] = client_mapping.get("domain_name", "default")
                    from app.services.schema_service import SchemaService
                    from app.services.dynamic_tool_factory import DynamicToolFactory
                    from app.services.dynamic_tool_executor import DynamicToolExecutor
                    from app.services.dynamic_prompt_assembler import DynamicPromptAssembler
                    
                    schema_service = SchemaService(db_config)
                    schema_metadata = await schema_service.get_schema_metadata()
                    tool_factory = DynamicToolFactory(dyn_cfg, schema_metadata)
                    tools, exec_map = tool_factory.generate_tools()
                    
                    from app.dynamic_db_client import DynamicDbClient
                    dyn_db_client = DynamicDbClient(db_config)
                    executor = DynamicToolExecutor(
                        dyn_db_client, exec_map, dyn_cfg["identity"]["table"],
                        dyn_cfg["identity"]["name_column"], dyn_cfg["identity"]["verification_column"]
                    )
                    prompt = DynamicPromptAssembler.assemble(dyn_cfg, schema_metadata, tools)
                    dynamic_kwargs = {
                        "dynamic_tools": tools,
                        "dynamic_executor": executor,
                        "system_prompt": prompt,
                        "domain": dyn_cfg["domain"]
                    }
                    logger.info(f"[{session_id}] Configured dynamic tools for client {client_id}")
        except Exception as e:
            logger.error(f"[{session_id}] Error loading dynamic config for client {client_id}: {e}")

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
            **dynamic_kwargs
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
