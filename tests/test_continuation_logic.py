import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from app.streaming_pipeline import StreamingVoicePipeline

class MockDeepgramClient:
    def __init__(self):
        self.buffer = ""
        self.flushed = False

    def clear_buffer(self):
        self.buffer = ""

    async def flush_and_read(self, timeout=0.3):
        self.flushed = True
        t = self.buffer
        self.buffer = ""
        return t

@pytest.mark.asyncio
async def test_continuation_stt_finished_before_cancellation():
    """
    Test scenario: STT finishes successfully before the barge-in.
    The cancelled task should return a dict containing the transcript.
    The continuation logic should grab this transcript instead of calling flush_and_read.
    """
    pipeline = StreamingVoicePipeline(
        groq_client=MagicMock(),
        db_client=MagicMock(),
        twilio_handler=MagicMock(),
        agent_service=MagicMock(),
        rephraser=MagicMock()
    )
    pipeline.deepgram = MockDeepgramClient()
    pipeline.deepgram.buffer = "Leftover text"

    # Mock the VAD to return data once, then simulate a barge-in by returning a second utterance
    # We will raise an exception or just break the loop to end the test after one turn.
    turn_count = 0
    barge_in_event = asyncio.Event()

    async def mock_vad(*args, **kwargs):
        nonlocal turn_count
        if turn_count == 0:
            turn_count += 1
            return b"audio1", "speech", 100, 250
        elif turn_count == 1:
            turn_count += 1
            # Simulate barge-in by setting the event
            if "interruption_event" in kwargs and kwargs["interruption_event"]:
                kwargs["interruption_event"].set()
            return b"audio2", "speech", 100, 250
        return None, "stream_ended", 0, 0

    # Mock process_single_utterance to return a result immediately (simulating fast STT)
    async def mock_process(*args, **kwargs):
        try:
            # Simulate some processing time
            await asyncio.sleep(0.1)
            # This represents STT finishing and returning the transcript
            return {"transcript": "Name is.", "timings": {}}
        except asyncio.CancelledError:
            # The actual code catches CancelledError and returns the result anyway
            return {"transcript": "Name is.", "timings": {}}

    with patch.object(pipeline, "_vad_collect_utterance", side_effect=mock_vad), \
         patch.object(pipeline, "_process_single_utterance", side_effect=mock_process):
         
        # We need to run _process_continuous_internal
        audio_queue = asyncio.Queue()
        
        pipeline_task = asyncio.create_task(
            pipeline._process_continuous_internal(
                audio_queue, 
                session_id="session_123", 
                on_turn_done=None, 
                on_stage=None, 
                barge_in_event=barge_in_event
            )
        )
        
        await pipeline_task
        
        # In this scenario, since STT finished, it should NOT have flushed the buffer
        assert pipeline.deepgram.flushed == False, "It should not have called flush_and_read because STT was done"



