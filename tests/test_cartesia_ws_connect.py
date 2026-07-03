import asyncio, os, time
from cartesia import AsyncCartesia
from dotenv import load_dotenv
load_dotenv()

async def test_ws():
    client = AsyncCartesia(api_key=os.getenv('CARTESIA_API_KEY'))
    t_start = time.time()
    ws = await client.tts.websocket()
    await ws.connect()
    t_connected = time.time()
    print(f"WS Connect Time: {(t_connected - t_start)*1000:.0f}ms")
    await ws.close()

asyncio.run(test_ws())
