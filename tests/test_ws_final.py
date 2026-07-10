import asyncio
import os
import time
from pathlib import Path
from cartesia import AsyncCartesia
from dotenv import load_dotenv

# Import the audio utility used in your pipeline
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.audio_utils import build_wav

load_dotenv()

async def test_ws_tts():
    print("Initializing Cartesia WebSocket...")
    client = AsyncCartesia(api_key=os.getenv('CARTESIA_API_KEY'))
    ws = await client.tts.websocket()
    await ws.connect()
    
    print("WebSocket connected successfully!")
    
    sentence = "Your orders are ORD-20260501-001 and ORD-20260510-002."
    print(f"\nSending text: '{sentence}'")
    
    t0 = time.time()
    
    # 1. Send the request via the open websocket (exactly how streaming_pipeline.py does it)
    voice = os.getenv("CARTESIA_VOICE_ID", "5ee9feff-1265-424a-9d7f-8e4d431a12c7")
    ws_stream = await ws.send(
        model_id="sonic-3.5",
        transcript=sentence,
        voice={"mode": "id", "id": voice},
        output_format={
            "container": "raw", 
            "encoding": "pcm_s16le", 
            "sample_rate": 24000
        },
        stream=True,
    )
    
    # 2. Measure TTFA and collect chunks (using the exact same hasattr logic)
    audio_chunks = []
    first = True
    ttfa_ms = 0
    
    async for output in ws_stream:
        # Compatibility check (same as pipeline)
        audio_chunk = None
        if hasattr(output, "audio") and output.audio:
            audio_chunk = output.audio
        elif isinstance(output, dict) and "audio" in output:
            audio_chunk = output["audio"]
            
        if audio_chunk:
            if first:
                ttfa_ms = (time.time() - t0) * 1000
                print(f"TTFA (Time To First Audio): {ttfa_ms:.0f}ms")
                first = False
            audio_chunks.append(audio_chunk)
            
    print(f"Received {len(audio_chunks)} total audio chunks.")
    
    # Simple sentence test
    print("\n--- Testing simple sentence ---")
    sentence2 = "Your orders are ORD-20260501-001 and ORD-20260510-002."
    print(f"Sending text: '{sentence2}'")
    
    t1 = time.time()
    ws_stream2 = await ws.send(
        model_id="sonic-3.5",
        transcript=sentence2,
        voice={"mode": "id", "id": voice},
        output_format={
            "container": "raw", 
            "encoding": "pcm_s16le", 
            "sample_rate": 24000
        },
        stream=True,
    )
    
    first = True
    async for output in ws_stream2:
        audio_chunk = None
        if hasattr(output, "audio") and output.audio:
            audio_chunk = output.audio
        elif isinstance(output, dict) and "audio" in output:
            audio_chunk = output["audio"]
            
        if audio_chunk and first:
            ttfa_ms2 = (time.time() - t1) * 1000
            print(f"TTFA for simple sentence: {ttfa_ms2:.0f}ms")
            first = False
    
    # 3. Combine and save to cached_audio
    raw_pcm = b"".join(audio_chunks)
    wav_bytes = build_wav(raw_pcm, sample_rate=24000)
    
    output_dir = Path("audio_cache")
    output_dir.mkdir(exist_ok=True)
    out_file = output_dir / "test_audio.wav"
    
    out_file.write_bytes(wav_bytes)
    print(f"Saved audio to: {out_file.absolute()}")
    
    await ws.close()

if __name__ == "__main__":
    asyncio.run(test_ws_tts())
