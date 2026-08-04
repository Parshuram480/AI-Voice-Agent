import asyncio
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types

API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.0-flash-live-001")
VOICE = os.getenv("GEMINI_VOICE", "Achernar")

async def main():
    client = genai.Client(api_key=API_KEY)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
    )
    
    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("Connected.")
        
        async def sender():
            print("Sending hello...")
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text="Hello")]),
                turn_complete=True
            )
            await asyncio.sleep(5)
            print("Sending 2+2...")
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text="What is 2+2?")]),
                turn_complete=True
            )
            await asyncio.sleep(5)
            print("Sender done.")

        async def receiver():
            print("Receiver started.")
            # ONE SINGLE ITERATOR
            async for response in session.receive():
                sc = response.server_content
                if sc and sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.text:
                            print(f"Agent: {part.text}")
                        elif part.inline_data:
                            print(f"Agent Audio: {len(part.inline_data.data)} bytes")
                if sc and getattr(sc, "output_transcription", None) and sc.output_transcription.text:
                    print(f"Agent Trans: {sc.output_transcription.text}")
                
                if sc and sc.turn_complete:
                    print("Turn complete!")
            print("Receiver exited the loop!!!")
            
        await asyncio.gather(sender(), receiver())

if __name__ == "__main__":
    asyncio.run(main())
