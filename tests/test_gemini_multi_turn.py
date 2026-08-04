"""Test: Multi-turn conversation to verify session.receive() behavior across turns."""
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
VOICE = os.getenv("GEMINI_VOICE", "Achernar")


async def test_multi_turn():
    """Test if session.receive() continues across multiple turns or ends after each turn."""
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
        system_instruction="You are a helpful assistant. Keep responses very short (1 sentence).",
    )
    
    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("[OK] Connected")
        
        # === TURN 1 ===
        print("\n--- TURN 1: Sending 'Hello' ---")
        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text="Hello")]),
            turn_complete=True
        )
        
        turn1_complete = False
        start = time.time()
        async for response in session.receive():
            if response.server_content:
                if getattr(response.server_content, "output_transcription", None):
                    t = response.server_content.output_transcription.text
                    if t:
                        print(f"  Agent: {t}", end="", flush=True)
                if response.server_content.turn_complete:
                    print(f"\n  [Turn 1 complete at {time.time()-start:.2f}s]")
                    turn1_complete = True
                    break
            if time.time() - start > 15:
                print("\n  [TIMEOUT]")
                break
        
        if not turn1_complete:
            print("[FAIL] Turn 1 did not complete")
            return False
        
        # Check if receive() continues or ends
        print("\n--- Checking if receive() continues after turn_complete ---")
        
        # === TURN 2: Send another message ===
        print("--- TURN 2: Sending 'What is 2+2?' ---")
        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text="What is 2 plus 2?")]),
            turn_complete=True
        )
        
        # METHOD A: Try continuing the SAME receive() iterator
        turn2_complete = False
        start = time.time()
        try:
            async for response in session.receive():
                if response.server_content:
                    if getattr(response.server_content, "output_transcription", None):
                        t = response.server_content.output_transcription.text
                        if t:
                            print(f"  Agent: {t}", end="", flush=True)
                    if response.server_content.turn_complete:
                        print(f"\n  [Turn 2 complete at {time.time()-start:.2f}s]")
                        turn2_complete = True
                        break
                if time.time() - start > 15:
                    print("\n  [TIMEOUT on turn 2]")
                    break
        except Exception as e:
            print(f"\n  [ERROR on turn 2 receive]: {e}")
        
        if turn2_complete:
            print("\n[RESULT] session.receive() works across turns with separate calls")
            return True
        else:
            print("\n[RESULT] session.receive() did NOT work for turn 2")
            print("  -> Need while True wrapper to restart receive() after each turn")
            return False


async def test_multi_turn_with_while_loop():
    """Test with while True wrapper around session.receive() — the original pattern."""
    print(f"\n\n=== Testing with while True wrapper ===")
    
    client = genai.Client(api_key=API_KEY)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        output_audio_transcription=AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE)
            )
        ),
        system_instruction="You are a helpful assistant. Keep responses very short (1 sentence).",
    )
    
    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("[OK] Connected")
        
        turns_completed = 0
        messages = ["Hello", "What is 2 plus 2?", "Thank you, goodbye"]
        
        # Send first message
        msg = messages[0]
        print(f"\n--- Sending: '{msg}' ---")
        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=msg)]),
            turn_complete=True
        )
        
        start = time.time()
        
        # Use while True + receive() pattern
        while turns_completed < len(messages):
            try:
                async for response in session.receive():
                    if response.server_content:
                        if getattr(response.server_content, "output_transcription", None):
                            t = response.server_content.output_transcription.text
                            if t:
                                print(f"  Agent: {t}", end="", flush=True)
                        
                        if response.server_content.turn_complete:
                            turns_completed += 1
                            elapsed = time.time() - start
                            print(f"\n  [Turn {turns_completed} complete at {elapsed:.2f}s]")
                            
                            # Send next message if available
                            if turns_completed < len(messages):
                                msg = messages[turns_completed]
                                print(f"\n--- Sending: '{msg}' ---")
                                await session.send_client_content(
                                    turns=types.Content(role="user", parts=[types.Part(text=msg)]),
                                    turn_complete=True
                                )
                            break  # break inner for loop, continue outer while
                    
                    if time.time() - start > 30:
                        print("\n  [TIMEOUT]")
                        return False
                        
            except Exception as e:
                print(f"\n  [ERROR]: {e}")
                return False
        
        print(f"\n[RESULT] Completed {turns_completed}/{len(messages)} turns with while+receive pattern")
        return turns_completed == len(messages)


async def main():
    print("=" * 60)
    print("Multi-Turn Gemini Live Conversation Test")
    print("=" * 60)
    
    r1 = await test_multi_turn()
    r2 = await test_multi_turn_with_while_loop()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Separate receive() calls:  {'PASS' if r1 else 'FAIL'}")
    print(f"  While+receive() pattern:   {'PASS' if r2 else 'FAIL'}")


if __name__ == "__main__":
    asyncio.run(main())
