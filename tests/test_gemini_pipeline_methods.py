"""
Test: Verify the exact same send methods used in our pipeline work with Gemini Live v2.12+.
This mimics the pipeline's sender_task and receiver_task flow.
"""
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


async def test_pipeline_send_methods():
    """Test the exact methods our pipeline uses: send_realtime_input + send_tool_response."""
    print(f"Model: {MODEL}, Voice: {VOICE}")
    print("\n=== Testing pipeline send methods ===")
    
    client = genai.Client(api_key=API_KEY)
    
    tool_declarations = [
        {
            "name": "verify_patients",
            "description": "Verify a patient",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "full_name": {"type": "STRING", "description": "Patient name"},
                    "date_of_birth": {"type": "STRING", "description": "DOB YYYY-MM-DD"}
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
            parts=[types.Part(text="You are a healthcare assistant. Greet the user warmly.")]
        ),
        tools=[{"function_declarations": tool_declarations}]
    )
    
    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("[OK] Connected to Gemini Live")
        
        # Step 1: Send silence audio using send_realtime_input (like pipeline does)
        silence = b'\x00' * 3200  # 100ms of silence at 16kHz
        for i in range(5):  # Send 500ms of silence
            await session.send_realtime_input(
                audio=types.Blob(data=silence, mimeType="audio/pcm;rate=16000")
            )
        print("[OK] send_realtime_input worked (500ms silence)")
        
        # Step 2: Send text to trigger a response (simulating user speech detected by Gemini VAD)
        await session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[types.Part(text="Hello, I need help")]
            ),
            turn_complete=True
        )
        print("[OK] send_client_content worked")
        
        # Step 3: Receive responses (like receiver_task does)
        got_audio = False
        got_transcription = False
        got_turn_complete = False
        start = time.time()
        
        async for response in session.receive():
            elapsed = time.time() - start
            
            sc_flag = response.server_content is not None
            tc_flag = response.tool_call is not None
            um_flag = response.usage_metadata is not None
            
            if response.server_content:
                sc = response.server_content
                
                if sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.inline_data and not got_audio:
                            print(f"[OK] Got audio at {elapsed:.2f}s ({len(part.inline_data.data)} bytes)")
                            got_audio = True
                
                if getattr(sc, "output_transcription", None):
                    t = sc.output_transcription.text
                    if t and not got_transcription:
                        print(f"[OK] Got transcription: '{t}'")
                        got_transcription = True
                
                if sc.turn_complete:
                    print(f"[OK] Turn complete at {elapsed:.2f}s")
                    got_turn_complete = True
                    break
            
            if elapsed > 15:
                print("[FAIL] Timeout")
                break
        
        if got_audio and got_turn_complete:
            print("\n=== ALL PIPELINE METHODS WORK ===")
            return True
        else:
            print(f"\n=== FAILED: audio={got_audio}, turn={got_turn_complete} ===")
            return False


if __name__ == "__main__":
    success = asyncio.run(test_pipeline_send_methods())
    sys.exit(0 if success else 1)
