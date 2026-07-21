import asyncio
import os
import sys
import time

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types
from google.genai.types import AudioTranscriptionConfig

API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.0-flash-live-001")
VOICE = os.getenv("GEMINI_VOICE", "Aoede")

async def test_healthcare_multimodal():
    print(f"Model: {MODEL}")
    
    client = genai.Client(api_key=API_KEY)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        output_audio_transcription=AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE)
            )
        ),
        system_instruction="You are a helpful healthcare assistant. Answer medical and health related queries. Keep responses concise.",
    )
    
    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("[OK] Connected to Gemini Live Healthcare Pipeline")
        
        turns_completed = 0
        messages = [
            "The phone call has just connected. Please greet the user appropriately for the 'healthcare' domain and ask how you can help them.",
            "I need to book an appointment for tomorrow.",
            "My name is John Doe, and my date of birth is 1990-01-01.",
            "Thank you, that's all I needed."
        ]
        
        # Send first message (simulating the initial connection prompt)
        msg = messages[0]
        print(f"\n--- Sending (Initial Greeting): '{msg}' ---")
        await session.send(input=msg, end_of_turn=True)
        
        start = time.time()
        
        # Use while True + receive() pattern (same as our fixed pipeline)
        while turns_completed < len(messages):
            try:
                async for response in session.receive():
                    if response.server_content:
                        if getattr(response.server_content, "output_transcription", None):
                            t = response.server_content.output_transcription.text
                            if t:
                                print(f"  Agent Transcript: {t}", end="", flush=True)
                        
                        if getattr(response.server_content, "turn_complete", False):
                            turns_completed += 1
                            elapsed = time.time() - start
                            print(f"\n  [Turn {turns_completed} complete at {elapsed:.2f}s]")
                            
                            # Send next user message if available
                            if turns_completed < len(messages):
                                msg = messages[turns_completed]
                                print(f"\n--- User Speaks: '{msg}' ---")
                                await session.send(input=msg, end_of_turn=True)
                            break  # break inner for loop, continue outer while True
                    
                    if time.time() - start > 45:
                        print("\n  [TIMEOUT] Agent took too long to respond.")
                        return False
                        
            except Exception as e:
                print(f"\n  [ERROR]: {e}")
                return False
        
        print(f"\n[RESULT] Successfully completed {turns_completed}/{len(messages)} multi-turn conversational turns with Gemini!")
        return turns_completed == len(messages)

if __name__ == "__main__":
    success = asyncio.run(test_healthcare_multimodal())
    sys.exit(0 if success else 1)
