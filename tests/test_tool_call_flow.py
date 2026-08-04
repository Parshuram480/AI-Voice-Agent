import asyncio
import os

from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types

async def main():
    client = genai.Client(api_key=os.getenv('GOOGLE_API_KEY'))
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        tools=[{"function_declarations": [{"name": "get_time", "description": "Get current time"}]}]
    )
    async with client.aio.live.connect(model=os.getenv('GEMINI_LIVE_MODEL', 'gemini-2.0-flash-live-001'), config=config) as session:
        print("Connected.")
        
        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text="What time is it?")]),
            turn_complete=True
        )
        
        while True:
            try:
                async for response in session.receive():
                    sc = response.server_content
                    tc = response.tool_call
                    
                    if tc:
                        print("Got tool call:", tc.function_calls[0].name)
                        resp = types.FunctionResponse(
                            name="get_time",
                            id=tc.function_calls[0].id,
                            response={"time": "12:00 PM"}
                        )
                        print("Sending tool response...")
                        await session.send_tool_response(function_responses=[resp])
                        
                    if sc:
                        if sc.model_turn:
                            for part in sc.model_turn.parts:
                                if part.text:
                                    print("Agent Text:", part.text)
                                if part.inline_data:
                                    print("Agent Audio chunk!")
                        if getattr(sc, "output_transcription", None):
                            print("Trans:", sc.output_transcription.text)
                        if sc.turn_complete:
                            print("Turn Complete!")
                            return
            except Exception as e:
                print("Error:", e)
                break

asyncio.run(main())
