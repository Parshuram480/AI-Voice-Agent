import asyncio
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

async def test():
    client = genai.Client(api_key=os.environ.get('GOOGLE_API_KEY'))
    print("Connecting...")
    async with client.aio.live.connect(model='gemini-3.1-flash-live-preview', config={'response_modalities': ['AUDIO']}) as session:
        print("Connected! Waiting 45 seconds to see if it drops...")
        try:
            for _ in range(45):
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Exception during sleep: {e}")
            raise
    print("Done")

if __name__ == "__main__":
    asyncio.run(test())
