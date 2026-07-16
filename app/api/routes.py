"""HTTP API routes for authentication and configuration."""

import logging
from typing import Callable, Optional
from pathlib import Path
from fastapi import APIRouter, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from app.schemas.requests import SimulateRequest
from app.system_database import SystemDatabase, verify_password
from app.dynamic_db_client import DynamicDbClient

logger = logging.getLogger(__name__)
AUDIO_CACHE_DIR = Path("audio_cache")

# Initialize central System Database
system_db = SystemDatabase()

# --- Pydantic Schemas ---
class RegisterRequest(BaseModel):
    company_name: str
    client_name: str
    email: str
    password: str
    phone: Optional[str] = None
    domain_id: int
    db_type: str
    server_name: Optional[str] = None
    port: Optional[int] = None
    db_name: str
    username: Optional[str] = None
    password_db: Optional[str] = None
    schema_name: Optional[str] = None
    enable_ssl: Optional[bool] = False
    trust_server_certificate: Optional[bool] = False
    connection_timeout: Optional[int] = 5

class LoginRequest(BaseModel):
    email: str
    password: str

class DbConfigRequest(BaseModel):
    db_type: str
    server_name: Optional[str] = None
    port: Optional[int] = None
    db_name: str
    username: Optional[str] = None
    password: Optional[str] = None
    schema_name: Optional[str] = None
    enable_ssl: Optional[bool] = False
    trust_server_certificate: Optional[bool] = False
    connection_timeout: Optional[int] = 5

class CallRequest(BaseModel):
    phone_number: str
    client_id: Optional[int] = None


def create_api_router(
    get_pipeline: Callable[[], object],
    get_streaming_pipeline: Callable[[], object],
    get_twilio_handler: Optional[Callable[[], object]] = None,
) -> APIRouter:
    router = APIRouter()

    # -------------------------------------------------------------------------
    # Authentication & Registration APIs
    # -------------------------------------------------------------------------

    @router.get("/api/domains")
    async def get_domains():
        """Retrieve list of active domains from system database."""
        try:
            return await system_db.get_domains()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/api/auth/register")
    async def register_tenant(req: RegisterRequest):
        """Register a new SaaS client tenant with database configuration."""
        try:
            # Check if email already registered
            existing = await system_db.get_client_by_email(req.email)
            if existing:
                raise HTTPException(status_code=400, detail="Email is already registered.")

            client_data = {
                "company_name": req.company_name,
                "client_name": req.client_name,
                "email": req.email,
                "password": req.password,
                "phone": req.phone
            }

            db_config = {
                "db_type": req.db_type,
                "server_name": req.server_name,
                "port": req.port,
                "db_name": req.db_name,
                "username": req.username,
                "password": req.password_db,
                "schema_name": req.schema_name,
                "enable_ssl": req.enable_ssl,
                "trust_server_certificate": req.trust_server_certificate,
                "connection_timeout": req.connection_timeout
            }

            client_id = await system_db.register_client(client_data, db_config, req.domain_id)
            return {"success": True, "client_id": client_id, "message": "Registration successful."}
        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Error during tenant registration: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/api/auth/login")
    async def login_tenant(req: LoginRequest, response: Response):
        """Authenticates client and sets cookie session token."""
        client = await system_db.get_client_by_email(req.email)
        if not client:
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        
        if not verify_password(req.password, client["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        if client["status"] != "Active":
            raise HTTPException(status_code=403, detail="Account is disabled.")

        # Set session cookie (valid for 1 day)
        response.set_cookie(
            key="session_token",
            value=str(client["id"]),
            httponly=True,
            max_age=86400,
            samesite="lax"
        )
        return {"success": True, "message": "Login successful."}

    @router.post("/api/auth/logout")
    async def logout_tenant(response: Response):
        """Clears auth cookie session."""
        response.delete_cookie(key="session_token")
        return {"success": True, "message": "Logged out successfully."}

    @router.get("/api/auth/me")
    async def get_current_client(request: Request):
        """Retrieves details of the currently logged-in client."""
        client_id_str = request.cookies.get("session_token")
        if not client_id_str:
            raise HTTPException(status_code=401, detail="Unauthorized session.")
        
        try:
            client_id = int(client_id_str)
            request.app.state.last_active_client_id = client_id
            client = await system_db.get_client_by_id(client_id)
            if not client:
                raise HTTPException(status_code=401, detail="Session client not found.")
            
            db_config = await system_db.get_client_db_config(client_id)
            mapping = await system_db.get_client_domain_mapping(client_id)
            
            # Strip sensitive data before returning
            client.pop("password_hash", None)
            if db_config:
                db_config.pop("password", None)
            
            import os
            pipeline_mode = os.getenv("PIPELINE_MODE", "cascade").lower()
            return {
                "client": client,
                "db_config": db_config,
                "pipeline_mode": pipeline_mode,
                "domain": {
                    "id": mapping["domain_id"] if mapping else None,
                    "name": mapping["domain_name"] if mapping else None,
                    "verification_query": mapping["verification_query"] if mapping else None,
                    "data_query": mapping["data_query"] if mapping else None
                } if mapping else None
            }
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid session cookie.")

    @router.post("/api/tenant/test-connection")
    async def test_db_connection(req: DbConfigRequest):
        """Checks DB connectivity dynamically before saving settings."""
        # Normalize fields
        config = {
            "db_type": req.db_type,
            "db_name": req.db_name,
            "server_name": req.server_name,
            "port": req.port,
            "username": req.username,
            "password": req.password,
            "connection_timeout": req.connection_timeout,
            "trust_server_certificate": req.trust_server_certificate
        }
        client = DynamicDbClient(config)
        success, message = await client.test_connection()
        return {"success": success, "message": message}

    @router.post("/api/tenant/db-config")
    async def update_db_config(req: DbConfigRequest, request: Request):
        """Saves dynamic database settings for the logged-in client."""
        client_id_str = request.cookies.get("session_token")
        if not client_id_str:
            raise HTTPException(status_code=401, detail="Unauthorized session.")
        
        try:
            client_id = int(client_id_str)
            # Fetch existing configuration to preserve passwords if field is blank
            existing = await system_db.get_client_db_config(client_id)
            
            passwd = req.password
            if not passwd and existing:
                passwd = existing.get("password")

            config = {
                "db_type": req.db_type,
                "server_name": req.server_name,
                "port": req.port,
                "db_name": req.db_name,
                "username": req.username,
                "password": passwd,
                "schema_name": req.schema_name,
                "enable_ssl": req.enable_ssl,
                "trust_server_certificate": req.trust_server_certificate,
                "connection_timeout": req.connection_timeout
            }
            await system_db.save_client_db_config(client_id, config)
            return {"success": True, "message": "Database configuration saved successfully."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/api/twilio/call")
    async def make_twilio_call(req: CallRequest, request: Request):
        """Triggers an outbound Twilio phone call to any destination number."""
        client_id = req.client_id
        if client_id is None:
            client_id_str = request.cookies.get("session_token")
            if not client_id_str:
                raise HTTPException(status_code=401, detail="Unauthorized session.")
            try:
                client_id = int(client_id_str)
            except ValueError:
                raise HTTPException(status_code=401, detail="Invalid session token.")
        
        request.app.state.last_active_client_id = client_id
        try:
            import os
            th = get_twilio_handler() if get_twilio_handler else None
            if not th:
                raise HTTPException(status_code=500, detail="Twilio handler is not initialized on the server.")
            
            # Dynamically determine the callback server host
            server_host = os.getenv("SERVER_HOST")
            if not server_host:
                proto = request.headers.get("x-forwarded-proto", request.url.scheme)
                server_host = f"{proto}://{request.url.netloc}"
            
            call_sid = await th.make_outbound_call(
                to_number=req.phone_number,
                client_id=client_id,
                server_host=server_host
            )
            return {"success": True, "call_sid": call_sid, "message": f"Call initiated successfully. Call SID: {call_sid}"}
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as e:
            logger.error(f"Error initiating outbound Twilio call: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/api/twilio/call/{call_sid}")
    async def get_twilio_call_status(call_sid: str):
        """Retrieve the current real-time status of a Twilio call."""
        th = get_twilio_handler() if get_twilio_handler else None
        if not th:
            raise HTTPException(status_code=500, detail="Twilio handler is not initialized on the server.")
        try:
            status = await th.get_call_status(call_sid)
            return {"success": True, "status": status}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/api/twilio/call/{call_sid}/end")
    async def end_twilio_call(call_sid: str):
        """Hangs up / terminates an active Twilio call."""
        th = get_twilio_handler() if get_twilio_handler else None
        if not th:
            raise HTTPException(status_code=500, detail="Twilio handler is not initialized on the server.")
        try:
            success = await th.end_call(call_sid)
            return {"success": success}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


    # -------------------------------------------------------------------------
    # Legacy Pipeline Simulation & Audio Cache Serving APIs (Preserve compatibility)
    # -------------------------------------------------------------------------

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
