import asyncio
import base64
import json
import wave
import time

def test_chunking():
    # Simulate gemini audio buffer
    gemini_audio_buffer = bytearray()
    
    # 1. Simulate receiving some chunks from gemini
    print("Testing audio buffering...")
    test_chunks = [b'a' * 1000, b'b' * 4000, b'c' * 200]
    
    for audio_chunk in test_chunks:
        gemini_audio_buffer.extend(audio_chunk)
        print(f"Buffer size: {len(gemini_audio_buffer)}")
        
        while len(gemini_audio_buffer) >= 4800:
            chunk_bytes = bytes(gemini_audio_buffer[:4800])
            del gemini_audio_buffer[:4800]
            print(f"Emitted chunk of size {len(chunk_bytes)}. Remaining: {len(gemini_audio_buffer)}")

    print("Testing turn complete...")
    if gemini_audio_buffer:
        remainder = bytes(gemini_audio_buffer)
        if len(remainder) % 2 != 0:
            remainder += b'\x00'
        print(f"Emitted final remainder of size {len(remainder)}")
        gemini_audio_buffer.clear()

if __name__ == "__main__":
    test_chunking()
