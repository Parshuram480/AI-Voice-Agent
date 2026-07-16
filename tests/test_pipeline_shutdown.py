import os
import sys
import asyncio
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

from app.database import DatabaseClient
from app.session import SessionManager, InMemorySessionStore
from app.services import AgentService
from app.streaming_pipeline import StreamingVoicePipeline, _DONE

class MockGroq:
    def __init__(self, *args, **kwargs): pass
    async def warmup(self): pass
    async def close(self): pass

class MockTwilio:
    pass

class MockRephraser:
    pass

async def main():
    print("Initializing test environment...")
    db = DatabaseClient()
    await db.connect()

    session_store = InMemorySessionStore()
    session_manager = SessionManager(session_store)
    
    agent = AgentService(
        session_manager=session_manager,
        groq_client_1=MockGroq(),
        groq_client_2=MockGroq(),
        verification_service=None,
        order_service=None
    )

    pipeline = StreamingVoicePipeline(
        groq_client=MockGroq(),
        db_client=db,
        twilio_handler=MockTwilio(),
        agent_service=agent,
        rephraser=MockRephraser()
    )

    # Mock audio queue that immediately returns _DONE
    audio_queue = asyncio.Queue()
    audio_queue.put_nowait(_DONE)

    session_id = "test-shutdown-1"

    print("Running process_continuous with immediate _DONE...")
    try:
        result = await pipeline.process_continuous(
            audio_queue=audio_queue,
            session_id=session_id
        )
        print("Pipeline process_continuous returned successfully!")
        print(f"Result: {result}")
        print("\nShutdown logic did not throw any exceptions. get_or_create works!")
    except Exception as e:
        print(f"Pipeline threw an exception: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
