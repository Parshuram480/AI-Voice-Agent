import asyncio
import logging
from livekit import agents, rtc
from livekit.agents import JobContext, WorkerOptions, worker
from app.channels.livekit_adapter import LiveKitChannelAdapter
from app.audio_utils import resample_pcm
from app.streaming_pipeline import _DONE

logger = logging.getLogger(__name__)

# Sample rates used
AGENT_PLAYBACK_RATE = 24000  # Cartesia default rate
PIPELINE_INBOUND_RATE = 16000  # Groq Whisper default rate

async def entrypoint(ctx: JobContext):
    """
    LiveKit Agent Job entry point.
    Fires when a job is assigned to this worker.
    """
    logger.info(f"LiveKit agent worker started for room: {ctx.room.name}")
    
    # 1. Connect to the LiveKit Room
    await ctx.connect()
    logger.info("LiveKit connected to room. Preparing agent audio track...")

    # 2. Setup the agent outbound audio source and publish it to the room
    audio_source = rtc.AudioSource(sample_rate=AGENT_PLAYBACK_RATE, num_channels=1)
    audio_track = rtc.LocalAudioTrack.create_audio_track("agent-voice", audio_source)
    publish_options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    
    await ctx.room.local_participant.publish_track(audio_track, publish_options)
    logger.info("Agent voice track published successfully.")

    # 3. Instantiate our adapter
    livekit_adapter = LiveKitChannelAdapter(audio_source, sample_rate=AGENT_PLAYBACK_RATE)

    # 4. Shared audio queue for pipeline input
    audio_queue: asyncio.Queue = asyncio.Queue()
    pipeline_task = None

    # Helper to start pipeline
    def start_pipeline_task(session_id: str):
        nonlocal pipeline_task
        from app.main import streaming_pipeline
        
        logger.info(f"Starting pipeline task for session: {session_id}")
        pipeline_task = asyncio.create_task(
            streaming_pipeline.process_continuous(
                audio_queue=audio_queue,
                on_tts_audio=None,  # Handled by channel_adapter.send_audio inside pipeline
                session_id=session_id,
                channel_adapter=livekit_adapter,
            )
        )

    # Automatically start pipeline with room name as session ID
    start_pipeline_task(ctx.room.name)

    # 5. Handle incoming audio tracks from participants
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info(f"Subscribed to audio track {track.sid} from participant {participant.identity}")
            
            # Read WebRTC frames from track
            async def read_audio_frames():
                audio_stream = rtc.AudioStream(track)
                try:
                    async for frame_event in audio_stream:
                        frame = frame_event.frame
                        # Normalise frame to 16kHz PCM mono
                        pcm_data = frame.data
                        
                        # Resample to 16kHz if not already
                        if frame.sample_rate != PIPELINE_INBOUND_RATE:
                            # Convert 16-bit to float/lin if needed (rtc.AudioFrame gives raw bytes)
                            # E.g., WebRTC often delivers 48kHz
                            pcm_data = resample_pcm(
                                pcm_data,
                                in_rate=frame.sample_rate,
                                out_rate=PIPELINE_INBOUND_RATE,
                                sample_width=2,
                                channels=frame.num_channels
                            )
                        
                        await audio_queue.put(pcm_data)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Error reading frames from track {track.sid}: {e}")
                finally:
                    await audio_stream.aclose()
                    logger.info(f"Closed audio stream for track {track.sid}")

            asyncio.create_task(read_audio_frames())

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logger.info(f"Participant {participant.identity} disconnected. Ending session.")
        # End pipeline
        audio_queue.put_nowait(_DONE)

    # Wait for the room session to finish
    try:
        while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        logger.info("LiveKit Job context cancelled.")
    finally:
        audio_queue.put_nowait(_DONE)
        if pipeline_task:
            try:
                await pipeline_task
            except Exception as e:
                logger.error(f"Error awaiting pipeline completion: {e}")
        logger.info(f"LiveKit Agent session completed for room: {ctx.room.name}")


async def start_livekit_worker():
    """
    Launch LiveKit agent worker in the background.
    """
    logger.info("Initializing LiveKit Agent Worker...")
    
    # Read environment variables
    import os
    livekit_url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    
    if not all([livekit_url, api_key, api_secret]):
        logger.warning("LiveKit environment variables missing. Worker will not start.")
        return

    opts = WorkerOptions(
        entrypoint_fnc=entrypoint,
        api_key=api_key,
        api_secret=api_secret,
        ws_url=livekit_url,
    )
    
    try:
        from livekit.agents.worker import AgentServer
        server = AgentServer.from_server_options(opts)
        await server.run()
    except Exception as e:
        logger.error(f"Failed to start LiveKit worker: {e}")
