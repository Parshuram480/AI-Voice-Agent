import asyncio
import websockets
import json
import base64
import audioop
import time

async def test_websocket():
    uri = "ws://localhost:8000/audio-stream?client_id=1"
    
    print(f"Connecting to {uri}")
    try:
        async with websockets.connect(uri) as ws:
            print("Connected! Sending start event...")
            start_event = {
                "event": "start",
                "start": {
                    "streamSid": "test_stream_sid",
                    "callSid": "test_call_sid"
                }
            }
            await ws.send(json.dumps(start_event))
            
            # Send 1 second of silent audio to trigger Gemini pipeline VAD
            print("Sending audio frames...")
            silent_pcm_8k = b'\x00' * 16000 # 1 second at 8000hz 16-bit
            silent_ulaw = audioop.lin2ulaw(silent_pcm_8k, 2)
            
            # Send in 20ms chunks
            chunk_size = 160
            for i in range(0, len(silent_ulaw), chunk_size):
                chunk = silent_ulaw[i:i+chunk_size]
                payload = base64.b64encode(chunk).decode("ascii")
                await ws.send(json.dumps({
                    "event": "media",
                    "streamSid": "test_stream_sid",
                    "media": {"payload": payload}
                }))
                await asyncio.sleep(0.02)
                
            print("Audio sent. Waiting for response...")
            start_time = time.time()
            
            while time.time() - start_time < 15:
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    data = json.loads(response)
                    if data.get("event") == "media":
                        payload_len = len(data["media"]["payload"])
                        print(f"Received media payload of length {payload_len}")
                    else:
                        print(f"Received event: {data.get('event')}")
                except asyncio.TimeoutError:
                    continue
                    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
