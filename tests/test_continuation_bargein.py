import asyncio
import logging
import os
import time

from app.streaming_pipeline import StreamingVoicePipeline, _DONE
from app.groq_client import GroqClient
from app.database import DatabaseClient
from app.services.agent_service import AgentService
from app.llm.rephrase import LLMRephraser
from app.twilio_handler import TwilioHandler

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("TestContinuation")

class MockTwilioHandler:
    async def clear_stream(self, websocket, stream_sid):
        logger.info(f"MockTwilioHandler: clear_stream called for {stream_sid}")
        return True

class MockAgentService:
    async def handle_user_text(self, session_id, transcript, on_llm_token=None):
        logger.info(f"MockAgentService received merged text: '{transcript}'")
        from app.models.response import ConversationResult
        # Simulate processing time
        await asyncio.sleep(1.0)
        return ConversationResult(
            session_id=session_id,
            verified=False,
            customer=None,
            orders=[],
            timings={},
            turn_metrics={},
            intent="test",
            reply_text=f"Processed: {transcript}",
            state="test_state",
            should_end=True
        )

class MockPipeline(StreamingVoicePipeline):
    """Override VAD to inject mock utterances directly without real audio processing."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mock_script = []
        self.script_idx = 0
        self.stt_provider = "mock"
        self.deepgram = None
        self.rephraser = None
        
    async def _vad_collect_utterance(self, audio_queue, *, session_id, utterance_id, interruption_event=None, **kwargs):
        if self.script_idx >= len(self.mock_script):
            return None, "stream_ended", 0.0, 0.0
            
        action = self.mock_script[self.script_idx]
        self.script_idx += 1
        
        delay = action.get("delay", 0.0)
        if delay > 0:
            logger.info(f"MockVAD: waiting {delay}s before triggering...")
            await asyncio.sleep(delay)
            
        if interruption_event and action.get("interrupt"):
            logger.info(f"MockVAD: firing interruption event!")
            interruption_event.set()
            
        text = action.get("text", "silence")
        logger.info(f"MockVAD returning utterance: {text}")
        
        # Must be large enough to pass length check (3200)
        return b"0" * 4000 + text.encode('utf-8'), "silence", 200.0, 300.0
        
    async def _process_single_utterance(self, utterance_pcm, **kwargs):
        text = utterance_pcm[4000:].decode('utf-8')
        logger.info(f"MockSTT decoding: {text}")
        
        original_stt = self.groq.speech_to_text
        async def mock_stt(*args, **kwargs):
            return text
        self.groq.speech_to_text = mock_stt
        
        try:
            return await super()._process_single_utterance(utterance_pcm, **kwargs)
        finally:
            self.groq.speech_to_text = original_stt

async def run_test():
    logger.info("Starting Continuation & Barge-in Test")
    
    groq = GroqClient()
    db = DatabaseClient()
    twilio = MockTwilioHandler()
    agent = MockAgentService()
    rephraser = None
    
    pipeline = MockPipeline(groq, db, twilio, agent, rephraser)
    
    # We are setting up:
    # 0s: T0 begins processing. STT gets "My name is Rohit Sharma". Debounce (300ms) starts.
    # 0.1s: VAD detects speech! Triggers interrupt. T0 debounce is cancelled.
    #       VAD returns T1 ("No wait, John Smith").
    #       T0 and T1 transcripts are merged.
    #       T1 debounce starts.
    # 1.0s: T1 processing finishes (should end session).
    
    pipeline.mock_script = [
        {"text": "My name is Rohit Sharma", "delay": 0.0, "interrupt": False},
        {"text": "No wait, John Smith", "delay": 0.1, "interrupt": True},
    ]
    
    queue = asyncio.Queue()
    
    def on_stage(stage, status, detail=""):
        logger.info(f"STAGE: {stage} [{status}] - {detail}")
        
    def on_tts(audio):
        logger.info(f"TTS audio chunk generated ({len(audio)} bytes)")
        
    try:
        # Provide a twilio_ws mock
        class MockWS:
            pass
            
        result = await asyncio.wait_for(
            pipeline.process_continuous(
                queue,
                on_stage=on_stage,
                on_tts_audio=on_tts,
                session_id="test-session",
                twilio_ws=MockWS(),
                stream_sid="test-stream"
            ),
            timeout=10.0
        )
        logger.info(f"Test completed. Result: {result}")
    except asyncio.TimeoutError:
        logger.error("Test timed out!")
    except Exception as e:
        logger.exception("Test failed!")

if __name__ == "__main__":
    asyncio.run(run_test())
