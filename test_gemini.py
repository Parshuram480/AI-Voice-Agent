import asyncio
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from app.gemini_live_client import GeminiLiveClient

async def main():
    class DummyService:
        pass
    
    client = GeminiLiveClient(
        verification_service=DummyService(),
        order_service=DummyService(),
        system_prompt="You are a helpful assistant. Keep your answer brief."
    )
    
    try:
        async with client.connect() as session:
            start_t = time.time()
            await session.send(input="Hello, are you there? Please say yes.", end_of_turn=True)
            print(f"[{time.time() - start_t:.2f}s] Sent initial prompt.")
            
            first_byte_time = None
            async for response in session.receive():
                if response.server_content is not None:
                    if response.server_content.model_turn is not None:
                        for part in response.server_content.model_turn.parts:
                            if part.inline_data:
                                if not first_byte_time:
                                    first_byte_time = time.time()
                                    print(f"[{first_byte_time - start_t:.2f}s] FIRST AUDIO BYTE RECEIVED!")
                                
                    if response.server_content.turn_complete:
                        print(f"[{time.time() - start_t:.2f}s] Turn complete!")
                        break
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
