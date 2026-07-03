import asyncio, inspect
from cartesia import AsyncCartesia

async def test():
    ws = await AsyncCartesia().tts.websocket()
    print("ws.send:", inspect.signature(ws.send))
    print("ws.context:", inspect.signature(ws.context))

asyncio.run(test())
