# Implementation Prompt for Voice-Agent Project

You are to implement the voice-agent system as described.  Create a **Python 3.x FastAPI** project with a modular OOP design and use the `python-dotenv` package to manage configuration.  Include a `requirements.txt` listing all necessary packages (FastAPI, Uvicorn, python-dotenv, psycopg2 or asyncpg, Twilio helper SDK, Groq SDK or `requests`, etc.).  Organize code into modules/classes such as `twilio_handler.py`, `groq_client.py`, `database.py`, and `main.py`.  Use classes and functions to separate concerns.  Load all secret keys and endpoints from a `.env` file (e.g. `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `GROQ_API_KEY`, `DB_HOST`, etc.) using `dotenv`.  

## Twilio Media Stream Integration  
- Create a FastAPI endpoint (e.g. `/voice`) to handle incoming voice requests.  This endpoint should respond with TwiML that uses `<Start><Stream>` (or `<Connect><Stream>`) to begin streaming the call audio to your server via WebSocket. For example, use the Twilio Python SDK or simple XML to return:
  ```xml
  <Response>
    <Start>
      <Stream url="wss://<your-server-host>/audio-stream"/>
    </Start>
    <Say voice="alice">Hello, please state your order query.</Say>
  </Response>
  ```  
- Implement a WebSocket endpoint (e.g. `/audio-stream`) in FastAPI that receives audio chunks from Twilio. Ensure you set the correct headers (e.g. `Upgrade: websocket`). This WebSocket will receive raw call audio frames from Twilio in near real-time. 

## Groq STT/LLM/TTS Clients  
- In `groq_client.py`, create a class (e.g. `GroqClient`) or separate functions to call Groq’s APIs. Use the Groq SDK or REST API endpoints with your `GROQ_API_KEY` from the environment. Implement methods for:  
  1. **Speech-to-Text**: send audio data (WAV/FLAC, 16 kHz mono) to Groq’s transcription endpoint. Return the transcribed text.  
  2. **Chat Completion (LLM)**: given a list of messages (system/user), call Groq’s chat completion API (e.g. model `llama-3.1-8b-instant`) and obtain a response. Use streaming (`stream=True`) if supported to speed up output.  
  3. **Text-to-Speech**: send the final response text to Groq’s TTS endpoint (e.g. `canopylabs/orpheus-v1-english`) with a chosen voice. Save or return the resulting WAV audio bytes or file path.  
- Ensure these calls are asynchronous (use `async`/`await`) and reuse HTTP sessions to minimize latency. 

## Processing Pipeline and Logic  
- When audio comes in via WebSocket, buffer it and detect end-of-speech (e.g. using silence or a fixed chunk). Once you have a complete user query, call your STT method.  
- Parse the text to determine intent. If the query is about “order status,” you can directly query the database. Otherwise, formulate a chat prompt (system instructions) and pass the text to the Groq LLM to generate a natural conversational response.  
- **Database Access**: In `database.py`, connect to the local PostgreSQL (use `psycopg2` or `asyncpg` and credentials from `.env`). Write a function to validate the user’s identity (e.g. by name and DOB) and retrieve their latest order status. Ensure the orders table is indexed for fast lookup.  
- After obtaining the necessary information (e.g. order status), construct the reply text. You may include verification (“Your name and DOB match our records.”) and the status (“Your last order is shipped and will arrive Tuesday.”). This text should be concise.  
- Call the Groq TTS function with this reply text to get back the audio file. Save it to a static location or memory.

## Serving the Response (Twilio Playback)  
- Once you have the reply audio, instruct Twilio to play it. You can do this by closing the WebSocket (if using `<Connect><Stream>`, Twilio will then execute remaining TwiML). Alternatively, use the Twilio REST API to update the call’s TwiML to include a `<Play>` tag with the URL of the audio file, for example:  
  ```xml
  <Response>
    <Play>https://<your-server-host>/static/reply.wav</Play>
    <Hangup/>
  </Response>
  ```  
- Ensure the audio file is accessible (serve it via FastAPI’s static files or a simple file endpoint). Twilio will fetch and play this audio immediately.  
- Use asynchronous code so that STT, LLM, and TTS calls overlap where possible, to keep total latency <1 second.

## Local UI for Testing  
- Build a minimal frontend (HTML/JS) or an interactive FastAPI endpoint to test the flow locally. For example, a simple webpage with a “Simulate Call” button or form where you can enter a user’s name, DOB, and query. When submitted, it should invoke your FastAPI endpoint as if it were Twilio (you might POST JSON or use WebSocket simulation).  
- Display or play back the resulting TTS audio response on the page (for example, use an HTML audio tag). This lets you verify the agent’s answer without making an actual phone call.  
- Alternatively, use ngrok or the Twilio CLI to route a real phone call to your local `/voice` endpoint for end-to-end testing.

## Additional Requirements  
- **Environment Variables**: Clearly document in the prompt that the coding agent should define all keys in a `.env` file and load them (no hard-coded secrets). Specify placeholders like `<TWILIO_ACCOUNT_SID>` etc.  
- **Latency Goal**: Emphasize that the implementation must be optimized for speed: use async I/O, small audio chunks, streaming outputs, and efficient DB queries.  
- **Dependencies**: Include commands or a `requirements.txt` for installing dependencies (e.g. `pip install fastapi uvicorn python-dotenv twilio groq psycopg2-binary` etc.).  
- **Modular OOP**: Remind the agent to use classes and separate files for clarity (e.g. a `TwilioHandler` class, `GroqClient`, `DatabaseClient`).  
- **Testing**: Instruct the agent to include example data (e.g. a sample orders table with one record) and a brief README or inline comments on how to run the server and test the flow.

Ensure the prompt covers *all* the above points in clear, step-by-step detail, so that the coding agent has a complete guide to implement the system on a local machine.