import os
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

keys_to_test = {
    "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
    "GROQ_LLM1_API_KEY": os.getenv("GROQ_LLM1_API_KEY"),
    "GROQ_LLM2_API_KEY": os.getenv("GROQ_LLM2_API_KEY"),
    "GROQ_SUMMARY_API_KEY": os.getenv("GROQ_SUMMARY_API_KEY"),
}

async def test_key(name, key):
    if not key:
        print(f"[NOT FOUND] {name} is missing in .env")
        return
        
    url = "https://api.groq.com/openai/v1/models"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    print(f"[SUCCESS] {name}: WORKING (Status 200)")
                else:
                    text = await response.text()
                    print(f"[FAILED] {name}: FAILED (Status {response.status}) - {text}")
    except Exception as e:
        print(f"[ERROR] {name}: ERROR - {str(e)}")

async def main():
    print("Testing Groq API Keys...\n" + "="*30)
    for name, key in keys_to_test.items():
        if name != "GROQ_API_KEY" or key: # only test default if present
            await test_key(name, key)

if __name__ == "__main__":
    asyncio.run(main())
