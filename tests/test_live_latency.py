import asyncio
import json
import time
import os
import sys
from pathlib import Path
import websockets
from dotenv import load_dotenv
load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.audio_utils import build_wav, wav_bytes_to_pcm, resample_pcm
from app.cartesia_client import CartesiaClient

async def generate_test_audio(text: str) -> bytes:
    print(f"Generating realistic human voice for: '{text}'...")
    client = CartesiaClient()
    pcm_bytes = await client.text_to_speech(text)
    # Convert Cartesia 24kHz output to 16kHz for the mic stream
    pcm_16k = resample_pcm(pcm_bytes, in_rate=24000, out_rate=16000)
    return pcm_16k

async def test_live_latency():
    uri = "ws://127.0.0.1:8001/ws/mic-stream"
    
    query = "Hi, I am calling to check my order status."
    try:
        audio_bytes = await generate_test_audio(query)
    except Exception as e:
        print(f"Failed to generate test audio: {e}")
        return

    # 16-bit mono 16kHz
    framerate = 16000
    audio_duration = len(audio_bytes) / (framerate * 2)
    print(f"Generated {audio_duration:.2f}s of audio.")
    
    print(f"Connecting to live server at {uri}...")
    try:
        async with websockets.connect(uri) as ws:
            print("Connected! Streaming human speech...")
            
            chunk_duration_ms = 30
            bytes_per_ms = framerate * 2 / 1000
            chunk_size = int(chunk_duration_ms * bytes_per_ms)
            
            t0 = time.time()
            receive_queue = asyncio.Queue()
            
            async def receiver():
                try:
                    while True:
                        msg = await ws.recv()
                        await receive_queue.put(msg)
                except Exception:
                    pass

            recv_task = asyncio.create_task(receiver())
            
            # Stream audio like a real mic
            for i in range(0, len(audio_bytes), chunk_size):
                chunk = audio_bytes[i:i+chunk_size]
                await ws.send(chunk)
                await asyncio.sleep(chunk_duration_ms / 1000.0)
                
            audio_end_time = time.time()
            print(f"User finished speaking at {audio_end_time - t0:.2f}s mark.")
            print("Waiting for agent to process VAD -> STT -> LLM -> TTS...")
            
            stt_received = False
            first_audio_received = False
            
            while True:
                try:
                    msg = await asyncio.wait_for(receive_queue.get(), timeout=15.0)
                    if isinstance(msg, str):
                        data = json.loads(msg)
                        msg_type = data.get("type")
                        
                        if msg_type == "stt" and not stt_received:
                            stt_time = time.time()
                            latency = (stt_time - audio_end_time) * 1000
                            print(f"[STT] Final Transcript: '{data.get('text')}' (Latency from end of speech: {latency:.0f}ms)")
                            stt_received = True
                            
                        elif msg_type == "tts_audio" and not first_audio_received:
                            audio_time = time.time()
                            latency = (audio_time - audio_end_time) * 1000
                            print(f"[TTS] Received FIRST agent audio chunk! *** END-TO-END LATENCY: {latency:.0f}ms ***")
                            first_audio_received = True
                            
                        elif msg_type == "session_end":
                            print("Session ended.")
                            break
                            
                        elif msg_type == "turn_done":
                            print("Turn completed.")
                            break
                            
                except asyncio.TimeoutError:
                    print("Timeout waiting for server response!")
                    break
                    
            recv_task.cancel()
            await ws.send(json.dumps({"action": "stop"}))
            
    except ConnectionRefusedError:
        print("Connection refused. Make sure server is running on port 8001.")
    except Exception as e:
        print(f"WebSocket error: {e}")

if __name__ == "__main__":
    asyncio.run(test_live_latency())
