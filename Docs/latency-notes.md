# Latency Optimization Notes

## Streaming Pipeline
- STT, response generation, and TTS run concurrently using asyncio queues.
- Early STT reduces time-to-first-intent.

## Caching
- TTS responses are cached with an LRU cache to reduce repeat synthesis latency.

## Networking
- Groq HTTP clients keep connections warm to avoid TLS setup latency.

## Deterministic Control
- Intent routing and slot filling are synchronous and lightweight.
- LLM usage is optional and limited to rephrasing.

## End-to-End Goal
- Target total latency under 2 seconds for the first response.
