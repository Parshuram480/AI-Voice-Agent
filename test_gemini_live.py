import asyncio
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

async def main():
    client = genai.Client(api_key=os.environ.get('GOOGLE_API_KEY'))
    
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            parts=[types.Part(text="Hello")]
        )
    )
    try:
        async with client.aio.live.connect(model='gemini-3.1-flash-live-preview', config=config) as session:
            chunk = b'\x00' * 160
            print("Sending realtime input...")
            await session.send_realtime_input(
                audio=types.Blob(data=chunk, mimeType="audio/pcm;rate=16000")
            )
            print("Sent! Waiting for response...")
            async for response in session.receive():
                print("Received:", response)
                break
    except Exception as e:
        print(f"Exception: {type(e).__name__} - {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
