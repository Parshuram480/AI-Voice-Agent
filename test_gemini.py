import asyncio
import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

async def run_test():
    api_key = os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
    
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
            )
        )
    )

    print(f"Connecting to {model}...")
    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            print("Connected!")
            
            # Send a text message (so we don't have to generate fake audio for the test)
            print("Sending text: 'Hello, what is your name?'")
            await session.send(input="Hello, what is your name?", end_of_turn=True)
            
            # Read responses
            async for response in session.receive():
                print("\n--- Received Response Chunk ---")
                
                # Check for usage metadata
                if getattr(response, "usage_metadata", None):
                    um = response.usage_metadata
                    print(f"[USAGE] Prompt: {um.prompt_token_count}, Response: {um.response_token_count}")
                    
                # Check for server content (transcripts, audio, text)
                if response.server_content is not None:
                    
                    if getattr(response.server_content, "input_transcription", None):
                        t_text = response.server_content.input_transcription.text
                        if t_text:
                            print(f"[INPUT TRANSCRIPT] {t_text}")
                            
                    if getattr(response.server_content, "output_transcription", None):
                        t_text = response.server_content.output_transcription.text
                        if t_text:
                            print(f"[OUTPUT TRANSCRIPT] {t_text}")
                            
                    model_turn = response.server_content.model_turn
                    if model_turn:
                        for part in model_turn.parts:
                            if part.text:
                                print(f"[LLM TEXT] {part.text}")
                            if part.inline_data:
                                print(f"[AUDIO] Received {len(part.inline_data.data)} bytes")
                                
                    if response.server_content.turn_complete:
                        print("[TURN COMPLETE]")
                        break # End test on turn complete
                        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_test())
