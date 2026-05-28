# Architecture

## Overview
The voice agent uses a deterministic conversation layer on top of the existing low-latency streaming pipeline. The state machine, intent routing, and slot filling drive all business logic. The LLM is optional and only used to rephrase deterministic responses.

## Core Modules
- api/ - HTTP and WebSocket routes.
- intents/ - Rule-based intent router and slot filler.
- services/ - Conversation, verification, and order services.
- repositories/ - SQL-safe data access.
- session/ - In-memory session store with TTL and bounded history.
- state_machine/ - Conversation state transitions.
- observability/ - Latency metrics tracking.
- logging/ - Structured logging helpers.

## Conversation States
- IDLE
- GREETING
- WAITING_FOR_INTENT
- WAITING_FOR_NAME
- WAITING_FOR_DOB
- VERIFYING_USER
- FETCHING_ORDER
- RESPONDING
- FOLLOWUP
- END_CALL
- FALLBACK

## Data Safety
- All queries are parameterized.
- No dynamic SQL generation.
- Soft deletes are enforced with deleted_at filters.

## Controlled LLM Usage
- LLM is optional and only rephrases the response text.
- LLM never makes decisions, queries SQL, or changes state.
