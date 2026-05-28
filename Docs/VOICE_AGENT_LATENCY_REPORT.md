# Voice Agent Project Summary and Latency Report

## Purpose and current result
This project is an AI voice agent for order support. A caller or a browser user speaks, the system transcribes the speech, understands intent, checks orders, generates a short reply, and speaks it back. The reported end-to-end latency was about 7 seconds earlier and is now typically under 2 seconds in local testing. That improvement comes from turning a sequential pipeline into a streaming, overlapping pipeline and from several smaller optimizations across audio handling, network reuse, and caching.

## User flow (simple, end-to-end)
A phone call comes into Twilio and Twilio starts a media stream to the server. The server receives audio chunks on a WebSocket, converts them from mu-law to 16 kHz PCM, detects speech and silence, and starts speech-to-text early so it does not wait for the full utterance. As soon as a transcript is available, the system runs a lightweight intent check, verifies the customer in the database, builds context, and streams the LLM response token-by-token. Those tokens are buffered into sentences and sent to TTS immediately, so audio playback can start while the LLM is still finishing the reply. The final audio is cached and served back through Twilio as a playable URL.

For local browser testing, the flow is similar. The mic is captured with an AudioWorklet, streamed by WebSocket, and the UI shows partial STT, live LLM tokens, and audio chunks that play progressively. This mirrors the real call path but stays fully local.

## Main components and what each does
The backend is a FastAPI app that exposes HTTP and WebSocket endpoints for Twilio, for the browser mic stream, and for local simulation. The voice logic is separated into two pipelines: a legacy batch pipeline for simple text simulation and a streaming pipeline optimized for low latency. The streaming pipeline runs three async workers (STT, LLM, TTS) connected by queues, so work overlaps instead of waiting for each stage to finish. The audio utilities handle mu-law decoding, resampling to 16 kHz, WAV building, silence detection, and trimming. The database client uses asyncpg for PostgreSQL and has a fallback in-memory dataset for local testing. The Twilio handler builds TwiML and can update calls to play generated audio.

The frontend UI is a static page that can simulate calls or record a real microphone stream. It shows stage status, logs, and timing metrics. It also plays TTS audio as it arrives so perceived latency is lower even if the total response still takes longer.

Configuration is loaded from .env and exposes tuning knobs for early STT chunk size, silence thresholds, LLM max tokens, and TTS cache size. Dependencies are pinned in requirements.txt for consistent local setup.

## Models and services used
Speech-to-text uses Groq Whisper with the model whisper-large-v3-turbo. The LLM uses Groq chat completions with llama-3.1-8b-instant, and the TTS uses canopylabs/orpheus-v1-english with the voice "hannah." Twilio provides telephony and the media stream. PostgreSQL is the primary database, but the system works without it due to the fallback store.

## What changed to cut latency from ~7s to under 2s
The largest win is the streaming pipeline. Instead of waiting for STT to finish, then the LLM, then TTS, the system starts STT early on the first audio chunk, begins LLM as soon as a transcript exists, and starts TTS sentence-by-sentence as tokens stream in. That overlaps work and gives the user audio sooner.

Other improvements are smaller but add up. The Groq clients are kept warm so the first real call does not pay connection setup costs. HTTP keep-alive and connection pooling are enabled for the TTS client. Silence detection stops recording quickly, so there is less dead time. LLM outputs are kept short with a small max token limit and a short system prompt. TTS results are cached by reply text so common phrases do not need to be synthesized again. The UI streams audio chunks and schedules playback without gaps, which reduces perceived delay.

## How we measure latency
The streaming pipeline records timestamps for early STT, final STT, first LLM token, first TTS audio, and total end-to-end time. The browser UI displays these values in milliseconds so we can compare changes and verify the improvement.

## Does local <2s mean production will be <1s automatically?
No, not automatically. Production latency depends on network distance to Groq, Twilio streaming overhead, server CPU, load, and where you host the API. The current architecture is designed for low latency, but production can be faster or slower than local depending on deployment choices. To reach sub-1s reliably, you typically need a fast region close to Groq and Twilio, dedicated resources, and continued tuning of audio chunking, models, and caching.

## How we can push latency below 1 second
There are several practical options to reduce latency further without changing the core architecture. Reduce STT early chunk seconds and silence duration so the system decides "end of speech" faster. Shorten the LLM output even more, or switch to a smaller model or lower max tokens. Use the bidirectional Twilio media stream to send audio back through the live stream instead of updating the call to play a URL, which can save network fetch time. Add a small TTS pre-cache for common responses and warm that cache at startup. Keep the service in a region close to Groq and Twilio and use higher CPU instances to reduce event-loop latency. If needed, move TTS to a streaming-compatible engine so playback can start earlier than full sentence boundaries.

## Files and features at a glance
The main server and routes live in app/main.py. The streaming pipeline is in app/streaming_pipeline.py, the legacy batch pipeline in app/pipeline.py, the Groq client in app/groq_client.py, and the Twilio integration in app/twilio_handler.py. Audio utilities are in app/audio_utils.py. Database access and the fallback store are in app/database.py. The UI lives in static/index.html, static/app.js, and static/audio-processor.js. Configuration is in app/config.py and dependencies are in requirements.txt.

## Summary in simple words
We built a voice agent that listens, understands, and speaks back very quickly. The key change was switching from a step-by-step pipeline to a streaming pipeline where STT, LLM, and TTS overlap. We also made small speedups like connection warmup, caching, silence detection, and short replies. That is why the local end-to-end time dropped from about 7 seconds to under 2 seconds. Production speed depends on hosting and network distance, so it will not automatically be under 1 second, but the architecture makes that goal realistic with the right deployment and tuning.
