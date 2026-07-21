"""
Standalone test: Connect to Gemini Live API v2.12+ and verify audio round-trip.
This test sends a short spoken greeting and checks if Gemini responds with audio.
"""
import asyncio
import os
import sys
import time

# Load .env
from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types
from google.genai.types import AudioTranscriptionConfig

API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.0-flash-live-001")
VOICE = os.getenv("GEMINI_VOICE", "Achernar")

print(f"API Key present: {bool(API_KEY)}")
print(f"Model: {MODEL}")
print(f"Voice: {VOICE}")
print(f"SDK version: {genai.__version__ if hasattr(genai, '__version__') else 'unknown'}")

async def test_gemini_live_basic():
    """Test 1: Basic connection with NO tools, just text system prompt."""
    print("\n=== TEST 1: Basic Gemini Live connection (no tools) ===")
    client = genai.Client(api_key=API_KEY)
    
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription=AudioTranscriptionConfig(),
        output_audio_transcription=AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE)
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part(text="You are a helpful assistant. Greet the user warmly.")]
        ),
    )
    
    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("✓ Connected to Gemini Live!")
            
            # Send a text message to trigger a response
            print("  Sending text: 'Hello, can you hear me?'")
            await session.send(input="Hello, can you hear me?", end_of_turn=True)
            
            # Listen for responses with a timeout
            got_audio = False
            got_text = False
            got_turn_complete = False
            start = time.time()
            
            async for response in session.receive():
                elapsed = time.time() - start
                
                if response.server_content is not None:
                    sc = response.server_content
                    
                    if sc.model_turn:
                        for part in sc.model_turn.parts:
                            if part.inline_data:
                                if not got_audio:
                                    print(f"  ✓ Got first audio chunk at {elapsed:.2f}s ({len(part.inline_data.data)} bytes)")
                                got_audio = True
                            if part.text:
                                print(f"  ✓ Got text: {part.text[:100]}")
                                got_text = True
                    
                    if getattr(sc, "output_transcription", None):
                        t = sc.output_transcription.text
                        if t:
                            print(f"  ✓ Output transcription: {t[:100]}")
                    
                    if sc.turn_complete:
                        print(f"  ✓ Turn complete at {elapsed:.2f}s")
                        got_turn_complete = True
                        break
                
                if response.usage_metadata:
                    um = response.usage_metadata
                    print(f"  ✓ Usage: in={getattr(um, 'prompt_token_count', 0)}, out={getattr(um, 'response_token_count', 0)}")
                
                if elapsed > 15:
                    print("  ✗ TIMEOUT: No turn_complete after 15s")
                    break
            
            print(f"\n  Results: audio={got_audio}, text={got_text}, turn_complete={got_turn_complete}")
            if got_audio and got_turn_complete:
                print("  ✓✓✓ TEST 1 PASSED ✓✓✓")
                return True
            else:
                print("  ✗✗✗ TEST 1 FAILED ✗✗✗")
                return False
                
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_gemini_live_with_tools():
    """Test 2: Connection WITH dynamic tool declarations (like our pipeline uses)."""
    print("\n=== TEST 2: Gemini Live connection WITH tools ===")
    client = genai.Client(api_key=API_KEY)
    
    tool_declarations = [
        {
            "name": "verify_patients",
            "description": "Verify a patient's identity",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "full_name": {"type": "STRING", "description": "Patient's full name"},
                    "date_of_birth": {"type": "STRING", "description": "Patient DOB in YYYY-MM-DD"}
                },
                "required": ["full_name", "date_of_birth"]
            }
        }
    ]
    
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription=AudioTranscriptionConfig(),
        output_audio_transcription=AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE)
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part(text="You are a healthcare assistant. Greet the user and ask them to verify their identity.")]
        ),
        tools=[{"function_declarations": tool_declarations}]
    )
    
    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("✓ Connected to Gemini Live with tools!")
            
            # Send text to trigger greeting
            print("  Sending text: 'Hello'")
            await session.send(input="Hello", end_of_turn=True)
            
            got_audio = False
            got_turn_complete = False
            start = time.time()
            
            async for response in session.receive():
                elapsed = time.time() - start
                
                if response.server_content is not None:
                    sc = response.server_content
                    
                    if sc.model_turn:
                        for part in sc.model_turn.parts:
                            if part.inline_data:
                                if not got_audio:
                                    print(f"  ✓ Got first audio chunk at {elapsed:.2f}s ({len(part.inline_data.data)} bytes)")
                                got_audio = True
                            if part.text:
                                print(f"  ✓ Got text: {part.text[:100]}")
                    
                    if getattr(sc, "output_transcription", None):
                        t = sc.output_transcription.text
                        if t:
                            print(f"  ✓ Transcription: {t[:100]}")
                    
                    if sc.turn_complete:
                        print(f"  ✓ Turn complete at {elapsed:.2f}s")
                        got_turn_complete = True
                        break
                
                if elapsed > 15:
                    print("  ✗ TIMEOUT: No turn_complete after 15s")
                    break
            
            if got_audio and got_turn_complete:
                print("  ✓✓✓ TEST 2 PASSED ✓✓✓")
                return True
            else:
                print("  ✗✗✗ TEST 2 FAILED ✗✗✗")
                return False
                
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_gemini_live_audio_send():
    """Test 3: Send audio data (silence) and verify the send format works."""
    print("\n=== TEST 3: Audio send format test ===")
    client = genai.Client(api_key=API_KEY)
    
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE)
            )
        ),
        system_instruction="You are a helpful assistant.",
    )
    
    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("✓ Connected!")
            
            # Send silence (16kHz, 16-bit, mono — 1 second = 32000 bytes)
            silence = b'\x00' * 32000
            
            # Test the new audio send format
            try:
                await session.send(
                    input=types.LiveClientRealtimeInput(
                        audio=types.Blob(data=silence, mimeType="audio/pcm;rate=16000")
                    )
                )
                print("  ✓ Audio send (LiveClientRealtimeInput + Blob) succeeded!")
            except Exception as e:
                print(f"  ✗ Audio send failed: {e}")
                return False
            
            # Also send a text message so Gemini has something to respond to
            await session.send(input="Say hello", end_of_turn=True)
            
            got_response = False
            start = time.time()
            async for response in session.receive():
                elapsed = time.time() - start
                if response.server_content and response.server_content.turn_complete:
                    print(f"  ✓ Got turn_complete at {elapsed:.2f}s")
                    got_response = True
                    break
                if response.server_content and response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.inline_data and not got_response:
                            print(f"  ✓ Got audio response at {elapsed:.2f}s")
                            got_response = True
                if elapsed > 15:
                    break
            
            if got_response:
                print("  ✓✓✓ TEST 3 PASSED ✓✓✓")
                return True
            else:
                print("  ✗✗✗ TEST 3 FAILED ✗✗✗")
                return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    print("=" * 60)
    print("Gemini Live API v2.12+ Compatibility Test Suite")
    print("=" * 60)
    
    results = {}
    
    results["basic"] = await test_gemini_live_basic()
    results["with_tools"] = await test_gemini_live_with_tools()
    results["audio_send"] = await test_gemini_live_audio_send()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name}: {status}")
    
    all_passed = all(results.values())
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
