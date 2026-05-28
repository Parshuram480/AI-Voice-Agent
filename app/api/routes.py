"""HTTP API routes."""

from typing import Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse
from pathlib import Path

from app.schemas.requests import SimulateRequest

AUDIO_CACHE_DIR = Path("audio_cache")


def create_api_router(
    get_pipeline: Callable[[], object],
    get_streaming_pipeline: Callable[[], object],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/simulate")
    async def simulate_call(req: SimulateRequest):
        pipeline = get_pipeline()
        result = await pipeline.process_text_query(
            name=req.name,
            dob=req.dob,
            query=req.query,
        )

        if result.get("audio_url"):
            filename = result["audio_url"].split("/")[-1]
            result["audio_url"] = f"/audio/{filename}"

        return JSONResponse(content=result)

    @router.post("/api/mic")
    async def process_microphone(request: Request):
        audio_bytes = await request.body()
        if len(audio_bytes) < 1000:
            return JSONResponse(
                status_code=400,
                content={"error": "Audio too short. Please speak longer."},
            )

        streaming_pipeline = get_streaming_pipeline()
        result = await streaming_pipeline.process_audio_streaming(
            audio_bytes,
            call_sid=None,
            is_mulaw=False,
        )

        if result.get("audio_url"):
            filename = result["audio_url"].split("/")[-1]
            result["audio_url"] = f"/audio/{filename}"

        result.pop("audio_bytes", None)
        return JSONResponse(content=result)

    @router.get("/audio/{filename}")
    async def serve_audio(filename: str):
        filepath = AUDIO_CACHE_DIR / filename
        if not filepath.exists():
            return JSONResponse(
                status_code=404,
                content={"error": f"Audio file '{filename}' not found"},
            )

        media_type = "audio/webm" if filename.endswith(".webm") else "audio/wav"
        return FileResponse(
            path=str(filepath),
            media_type=media_type,
            filename=filename,
        )

    return router
