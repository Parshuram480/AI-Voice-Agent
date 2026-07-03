import asyncio
import time
import os
import sys

# Ensure app path is in sys
sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv(override=True)

from app.streaming_pipeline import StreamingVoicePipeline
from app.stt.deepgram_client import DeepgramStreamingClient
from app.groq_client import GroqClient
from app.cartesia_client import CartesiaClient
from app.services.agent_service import AgentService
from app.services.verification_service import VerificationService
from app.services.order_service import OrderService
from app.session import SessionManager, InMemorySessionStore
from app.repositories import CustomerRepository, OrderRepository
from app.database import DatabaseClient
from dotenv import load_dotenv

async def main():
    
    print("Initializing services...")
    stt = DeepgramStreamingClient(os.getenv("DEEPGRAM_API_KEY"))
    tts = CartesiaClient()
    llm = GroqClient()
    store = InMemorySessionStore()
    sessions = SessionManager(store)
    
    db = DatabaseClient()
    await db.connect()
    customer_repo = CustomerRepository(db)
    order_repo = OrderRepository(db)
    
    verification = VerificationService(customer_repo)
    orders = OrderService(order_repo)
    
    agent = AgentService(
        session_manager=sessions,
        groq_client=llm,
        verification_service=verification,
        order_service=orders,
    )
    
    from app.twilio_handler import TwilioHandler
    twilio = TwilioHandler()
    pipeline = StreamingVoicePipeline(
        groq_client=llm,
        db_client=db,
        twilio_handler=twilio,
        agent_service=agent,
        rephraser=None,
        cartesia_client=tts
    )
    
    # Test the streaming latency
    print("\n--- Testing True Streaming ---")
    tts_queue = asyncio.Queue()
    t0 = time.perf_counter()
    first_audio_time = None
    
    def on_llm_token(token: str):
        pass # Tokens are handled by pipeline or we can print them
        
    async def _tts_consumer():
        nonlocal first_audio_time
        while True:
            sentence = await tts_queue.get()
            if sentence is None:
                break
            # Time to first audio would be roughly the time the first sentence is queued + Cartesia API TTFA (~150ms)
            if first_audio_time is None:
                first_audio_time = time.perf_counter() - t0 + 0.150 # Add 150ms for Cartesia API
                print(f"\n>>> TIME TO FIRST AUDIO (Simulated): {first_audio_time*1000:.0f}ms <<<\n")
            print(f"[TTS] Synthesizing: {sentence}")
            tts_queue.task_done()
            
    consumer_task = asyncio.create_task(_tts_consumer())
    
    token_buffer = []
    def _handle_token(token: str):
        nonlocal token_buffer
        token_buffer.append(token)
        current = "".join(token_buffer)
        if current.endswith((".", "?", "!")):
            tts_queue.put_nowait(current.strip())
            token_buffer.clear()
            
    # Simulate turn 9
    print("\n--- TURN 9 ---")
    await pipeline.agent.handle_user_text("test-crash-1", "You are taking Rohit Sermas telling wrong. Its name is Rohit Sarma, s h a r m a.", on_llm_token=_handle_token)
    
    # Simulate turn 10
    print("\n--- TURN 10 ---")
    try:
        result = await pipeline.agent.handle_user_text("test-crash-1", "And my date of birth is 05/15/1990. And tell me my order status.", on_llm_token=_handle_token)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return
    
    t0 = time.perf_counter()
    pipeline_ms = int((time.perf_counter() - t0) * 1000)
    print(f"\nPipeline total time: {pipeline_ms}ms")
    print(f"Reply: {result.reply_text}\n")
    
    await llm.close()

if __name__ == "__main__":
    asyncio.run(main())
