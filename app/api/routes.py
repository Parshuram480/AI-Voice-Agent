"""HTTP API routes for authentication and configuration."""

import logging
from typing import Callable, Optional, Any, Dict, List
from pathlib import Path
from fastapi import APIRouter, Request, Response, HTTPException, status, UploadFile, File
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

class IntrospectRequest(BaseModel):
    db_type: str
    server_name: Optional[str] = None
    port: Optional[int] = None
    db_name: str
    username: Optional[str] = None
    password: Optional[str] = None
    connection_timeout: Optional[int] = 5

class GenerateRulesRequest(BaseModel):
    db_config: DbConfigRequest
    customer_table: str
    verification_fields: list[str]
    data_table: str
    data_fields: list[str]
    schema_data: dict[str, list[str]]

class TestQueryRequest(BaseModel):
    db_config: DbConfigRequest
    verification_query: str
    data_query: str
    test_inputs: list[str] = []

class SaveRulesRequest(BaseModel):
    db_config: DbConfigRequest
    domain_id: int
    verification_query: str
    data_query: str
    client_id: Optional[int] = None
    ui_config_metadata: Optional[dict[str, Any]] = None


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
    async def register_tenant(req: RegisterRequest, response: Response):
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
            response.set_cookie(key="session_token", value=str(client_id), httponly=True, samesite="lax")
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
                    "data_query": mapping["data_query"] if mapping else None,
                    "ui_config_metadata": mapping["ui_config_metadata"] if mapping else None,
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

    @router.post("/api/tenant/upload-sqlite")
    async def upload_sqlite_db(file: UploadFile = File(...)):
        """Uploads an SQLite database file (.db, .sqlite) to the server."""
        try:
            filename = file.filename or "uploaded_database.db"
            if not (filename.endswith(".db") or filename.endswith(".sqlite") or filename.endswith(".sqlite3")):
                filename += ".db"
                
            upload_dir = Path("uploads/db_files")
            upload_dir.mkdir(parents=True, exist_ok=True)
            
            save_path = upload_dir / filename
            content = await file.read()
            with open(save_path, "wb") as f:
                f.write(content)
                
            db_path_str = str(save_path).replace("\\", "/")
            return {
                "success": True,
                "db_name": db_path_str,
                "message": f"Database '{filename}' uploaded successfully."
            }
        except Exception as e:
            logger.error(f"Error uploading SQLite database: {e}")
            raise HTTPException(status_code=500, detail=f"File upload failed: {e}")

    @router.post("/api/tenant/db-config/introspect")
    async def introspect_db_schema(req: IntrospectRequest):
        """Introspects database schema to extract tables and column names."""
        config = {
            "db_type": req.db_type,
            "db_name": req.db_name,
            "server_name": req.server_name,
            "port": req.port,
            "username": req.username,
            "password": req.password,
            "connection_timeout": req.connection_timeout
        }
        client = DynamicDbClient(config)
        success, message = await client.test_connection()
        if not success:
            return {"success": False, "message": message, "schema": {}}
        
        schema = await client.introspect_schema()
        return {"success": True, "message": "Database introspected successfully.", "schema": schema}

    @router.post("/api/tenant/db-config/generate-rules")
    async def generate_db_rules(req: GenerateRulesRequest):
        """Uses LLM to construct dialect-specific SQL queries and natural language summary."""
        import json
        import os
        
        db_type = req.db_config.db_type.lower()
        placeholder_hint = "$1, $2, ..." if db_type == "postgresql" else ("?" if db_type != "oracle" else ":1, :2, ...")
        
        prompt = f"""You are an expert SQL engineer. Generate standard, parameterized SQL queries matching the user's requirements.

DATABASE TYPE: {db_type}
PARAMETER PLACEHOLDER HINT: Use {placeholder_hint} for parameters.

SCHEMA METADATA:
{json.dumps(req.schema_data, indent=2)}

USER SELECTIONS:
- Verification Table: {req.customer_table}
- Verification Criteria Fields: {json.dumps(req.verification_fields)}
- Business Data Table: {req.data_table}
- Business Data Fields to Retrieve: {json.dumps(req.data_fields)}

INSTRUCTIONS:
1. Locate columns matching verification fields in '{req.customer_table}'.
2. Write a verification_query:
   - Must SELECT primary key 'id' plus verified fields from '{req.customer_table}'.
   - CRITICAL: Write the WHERE clause filters in the EXACT SAME ORDER as verification_fields: {json.dumps(req.verification_fields)}.
   - Must filter using LOWER() on text fields where applicable.
   - Example (PostgreSQL): SELECT id, full_name, email_address FROM {req.customer_table} WHERE LOWER(full_name) = $1 AND email_address = $2 LIMIT 1
   - Example (SQLite/MySQL): SELECT id, full_name, email_address FROM {req.customer_table} WHERE LOWER(full_name) = ? AND email_address = ? LIMIT 1
3. Write a data_query:
   - Must SELECT specified data fields ({json.dumps(req.data_fields) if req.data_fields else '*'}) from '{req.data_table}'.
   - Must filter by foreign key referencing customer id (e.g. patient_id, customer_id, or id = $1 / ?).
4. Provide a friendly 2-sentence natural_language_summary explaining how the agent will identify callers and what records it will look up.

Return ONLY a JSON object:
{{
  "natural_language_summary": "...",
  "verification_query": "...",
  "data_query": "..."
}}"""

        try:
            import asyncio
            from google import genai

            api_key = os.getenv("GEMINI_API_KEY")
            model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

            def _call_gemini():
                client = genai.Client(api_key=api_key)
                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                return resp.text or ""

            res_text = await asyncio.to_thread(_call_gemini)
            
            clean_json = res_text.strip()
            if clean_json.startswith("```"):
                clean_json = clean_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                
            data = json.loads(clean_json)
            return {
                "success": True,
                "summary": data.get("natural_language_summary", ""),
                "verification_query": data.get("verification_query", ""),
                "data_query": data.get("data_query", "")
            }
        except Exception as e:
            logger.error(f"Error generating AI SQL rules via Gemini: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to generate SQL rules: {e}")

    @router.post("/api/tenant/db-config/test-query")
    async def test_db_rules(req: TestQueryRequest):
        """Executes verification and data queries with sample inputs to produce readable preview result."""
        config = {
            "db_type": req.db_config.db_type,
            "db_name": req.db_config.db_name,
            "server_name": req.db_config.server_name,
            "port": req.db_config.port,
            "username": req.db_config.username,
            "password": req.db_config.password,
            "connection_timeout": req.db_config.connection_timeout
        }
        client = DynamicDbClient(config)
        
        try:
            params = []
            import re
            for val in req.test_inputs:
                v_str = str(val).strip()
                if re.match(r"^\d{4}[-/.]\d{2}[-/.]\d{2}$", v_str) or v_str.isdigit():
                    params.append(v_str)
                else:
                    params.append(v_str.lower())
                
            rows = await client.execute_query(req.verification_query, tuple(params))
            if not rows:
                return {
                    "success": False,
                    "verified": False,
                    "message": f"Verification failed. No matching record found for input values: {req.test_inputs}."
                }
                
            customer = dict(rows[0])
            for k, v in customer.items():
                if hasattr(v, "isoformat"):
                    customer[k] = v.isoformat()
                    
            records_rows = await client.execute_query(req.data_query, (customer.get("id", 1),))
            records = [dict(r) for r in records_rows]
            for r in records:
                for k, v in r.items():
                    if hasattr(v, "isoformat"):
                        r[k] = v.isoformat()
                        
            return {
                "success": True,
                "verified": True,
                "customer": customer,
                "records": records,
                "message": f"Verified successfully! Found {len(records)} matching records."
            }
        except Exception as e:
            logger.error(f"Error testing DB queries: {e}")
            return {"success": False, "verified": False, "message": f"Query execution error: {e}"}

    @router.post("/api/tenant/db-config/save-rules")
    async def save_db_rules(req: SaveRulesRequest, request: Request, response: Response):
        """Saves DB configuration, SQL rules, and UI metadata for tenant."""
        client_id_str = request.cookies.get("session_token")
        client_id = None
        if client_id_str:
            try:
                client_id = int(client_id_str)
            except ValueError:
                pass
                
        if not client_id and req.client_id:
            client_id = req.client_id
            response.set_cookie(key="session_token", value=str(client_id), httponly=True, samesite="lax")
            
        if not client_id:
            raise HTTPException(status_code=401, detail="Unauthorized session.")
            
        try:
            existing = await system_db.get_client_db_config(client_id)
            
            passwd = req.db_config.password
            if not passwd and existing:
                passwd = existing.get("password")
                
            config = {
                "db_type": req.db_config.db_type,
                "server_name": req.db_config.server_name,
                "port": req.db_config.port,
                "db_name": req.db_config.db_name,
                "username": req.db_config.username,
                "password": passwd,
                "schema_name": req.db_config.schema_name,
                "enable_ssl": req.db_config.enable_ssl,
                "trust_server_certificate": req.db_config.trust_server_certificate,
                "connection_timeout": req.db_config.connection_timeout
            }
            await system_db.save_client_db_config(client_id, config)
            
            import json
            meta_json = json.dumps(req.ui_config_metadata) if req.ui_config_metadata else None
            await system_db.update_client_domain_mapping(
                client_id=client_id,
                domain_id=req.domain_id,
                verification_query=req.verification_query,
                data_query=req.data_query,
                ui_config_metadata=meta_json
            )
            return {"success": True, "message": "Database and AI voice agent rules saved successfully!"}
        except Exception as e:
            logger.error(f"Error saving rules: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/api/tenant/refresh-schema")
    async def refresh_schema(request: Request):
        """Force-refresh the schema metadata for the logged-in tenant's database."""
        client_id_str = request.cookies.get("session_token")
        if not client_id_str:
            raise HTTPException(status_code=401, detail="Unauthorized session.")
        
        try:
            client_id = int(client_id_str)
            db_config = await system_db.get_client_db_config(client_id)
            if not db_config:
                raise HTTPException(status_code=404, detail="No database configuration found.")
            
            from app.services.pg_schema_service import PgSchemaService
            schema_service = PgSchemaService(dict(db_config))
            metadata = await schema_service.refresh()
            
            return {
                "success": True,
                "tables_found": list(metadata["tables"].keys()),
                "relationships_found": len(metadata["relationships"]),
            }
        except Exception as e:
            logger.error(f"Error refreshing schema: {e}")
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
