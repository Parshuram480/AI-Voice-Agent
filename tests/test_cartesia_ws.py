import asyncio, os, time
from cartesia import AsyncCartesia
from dotenv import load_dotenv
load_dotenv()

async def test_ws():
    client = AsyncCartesia(api_key=os.getenv('CARTESIA_API_KEY'))
    ws = await client.tts.websocket()
    await ws.connect()
    
    ctx = ws.context()
    print("context created!")
    
    t0 = time.time()
    await ctx.send(
        model_id="sonic-3.5",
        transcript="Hello world, testing websocket.",
        voice={"mode": "id", "id": "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"},
        output_format={
            "container": "raw", 
            "encoding": "pcm_s16le", 
            "sample_rate": 24000
        },
        continue_=False
    )
    
    count = 0
    with open('tests/output2.txt', 'w', encoding='utf-8') as f:
        async for output in ctx.receive():
            f.write(str(type(output)) + "\n")
            if hasattr(output, "model_dump"):
                f.write(str(output.model_dump()) + "\n")
            if hasattr(output, "audio"):
                if count == 0:
                    print(f"TTFA: {(time.time() - t0)*1000:.0f}ms")
                count += 1
                
    print(f"Received {count} chunks.")
    await ws.close()

asyncio.run(test_ws())
