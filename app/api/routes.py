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
from app.services.email_service import EmailService
import os

logger = logging.getLogger(__name__)
AUDIO_CACHE_DIR = Path("audio_cache")

# Initialize central System Database
system_db = SystemDatabase()
email_service = EmailService()

# --- Pydantic Schemas ---
class SendOtpRequest(BaseModel):
    email: str
    client_name: str

class VerifyOtpRequest(BaseModel):
    email: str
    otp: str

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

class UpdateProfileRequest(BaseModel):
    company_name: str
    client_name: str
    email: str
    phone: Optional[str] = None
    domain_id: int

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

class GeminiKeyRequest(BaseModel):
    api_key: str

class TwilioConfigRequest(BaseModel):
    account_sid: str
    auth_token: str
    phone_number: str

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





class SaveRulesRequest(BaseModel):
    db_config: DbConfigRequest
    domain_id: int
    identity: dict[str, Any]
    selected_tables: dict[str, list[str]]
    client_id: Optional[int] = None
    ui_config_metadata: Optional[dict[str, Any]] = None

class OutreachConfigRequest(BaseModel):
    db_config: DbConfigRequest
    campaign_type: str
    product_table: str
    selected_columns: list[str]
    company_name: str
    closing_goal: str
    ui_config_metadata: Optional[dict[str, Any]] = None

class OutreachCallRequest(BaseModel):
    phone_number: str
    customer_name: str
    language: Optional[str] = "en"

from app.auth_jwt import create_access_token, verify_and_get_client_id


def get_authenticated_client_id(request: Request) -> int:
    """Extracts client_id from Authorization Bearer JWT token header or session cookie."""
    # 1. Bearer Token Header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token_str = auth_header.split(" ", 1)[1].strip()
        client_id = verify_and_get_client_id(token_str)
        if client_id is not None:
            return client_id

    # 2. Session Cookie Fallback
    cookie_str = request.cookies.get("session_token")
    if cookie_str:
        client_id = verify_and_get_client_id(cookie_str)
        if client_id is not None:
            return client_id

    raise HTTPException(status_code=401, detail="Unauthorized: Missing, invalid, or expired JWT token.")


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

    @router.post("/api/auth/send-otp")
    async def send_otp(req: SendOtpRequest):
        """Generate and send an OTP validation code to a client's email."""
        try:
            existing = await system_db.get_client_by_email(req.email)
            if existing:
                raise HTTPException(status_code=400, detail="Email is already registered.")

            await email_service.send_otp_email(req.email, req.client_name)
            return {"success": True, "message": "Verification code sent successfully."}
        except HTTPException as he:
            raise he
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/api/auth/verify-otp")
    async def verify_otp(req: VerifyOtpRequest):
        """Verify the OTP validation code submitted by the user."""
        try:
            is_valid = email_service.verify_otp(req.email, req.otp)
            if not is_valid:
                raise HTTPException(status_code=400, detail="Invalid or expired verification code.")
            return {"success": True, "message": "Email verified successfully."}
        except HTTPException as he:
            raise he
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
            jwt_token = create_access_token(client_id=client_id, email=req.email)
            response.set_cookie(key="session_token", value=jwt_token, httponly=True, samesite="lax")
            return {
                "success": True,
                "token": jwt_token,
                "client_id": client_id,
                "message": "Registration successful."
            }
        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Error during tenant registration: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/api/auth/login")
    async def login_tenant(req: LoginRequest, response: Response):
        """Authenticates client and sets token/cookie."""
        client = await system_db.get_client_by_email(req.email)
        if not client:
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        
        if not verify_password(req.password, client["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        if client["status"] != "Active":
            raise HTTPException(status_code=403, detail="Account is disabled.")

        jwt_token = create_access_token(client_id=client["id"], email=client["email"])
        response.set_cookie(
            key="session_token",
            value=jwt_token,
            httponly=True,
            max_age=86400 * 7,
            samesite="lax"
        )
        return {
            "success": True,
            "token": jwt_token,
            "client_id": client["id"],
            "message": "Login successful."
        }

    @router.post("/api/auth/logout")
    async def logout_tenant(response: Response):
        """Clears auth cookie session."""
        response.delete_cookie(key="session_token")
        return {"success": True, "message": "Logged out successfully."}

    @router.put("/api/auth/profile")
    async def update_profile(req: UpdateProfileRequest, request: Request):
        """Update client profile and industry domain details."""
        try:
            client_id = get_authenticated_client_id(request)
        except Exception:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid session or token.")

        # Check if the new email is already taken by another user
        existing = await system_db.get_client_by_email(req.email)
        if existing and existing["id"] != client_id:
            raise HTTPException(status_code=400, detail="Email is already taken by another account.")

        try:
            await system_db.update_client_profile(
                client_id=client_id,
                company_name=req.company_name,
                client_name=req.client_name,
                email=req.email,
                phone=req.phone,
                domain_id=req.domain_id
            )
            # Retrieve updated client data
            updated_client = await system_db.get_client_by_id(client_id)
            updated_client.pop("password_hash", None)
            
            # Retrieve new domain name
            domains = await system_db.get_domains()
            domain_name = next((d["name"] for d in domains if d["id"] == req.domain_id), "Unknown")
            
            return {
                "success": True, 
                "message": "Profile updated successfully.",
                "client": updated_client,
                "domain_name": domain_name
            }
        except Exception as e:
            logger.error(f"Error updating profile: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/api/auth/me")
    async def get_current_client(request: Request):
        """Retrieves details of the currently logged-in client via token or cookie."""
        try:
            client_id = get_authenticated_client_id(request)
            request.app.state.last_active_client_id = client_id
            client = await system_db.get_client_by_id(client_id)
            if not client:
                raise HTTPException(status_code=401, detail="Session client not found.")
            
            db_config = await system_db.get_client_db_config(client_id)
            mapping = await system_db.get_client_domain_mapping(client_id)
            
            client.pop("password_hash", None)
            if db_config:
                db_config.pop("password", None)
                db_config.pop("gemini_api_key", None)
                db_config.pop("twilio_account_sid", None)
                db_config.pop("twilio_auth_token", None)
                db_config.pop("twilio_phone_number", None)
            
            import os
            pipeline_mode = os.getenv("PIPELINE_MODE", "cascade").lower()
            jwt_token = create_access_token(client_id=client_id, email=client.get("email", ""))
            return {
                "token": jwt_token,
                "client": client,
                "db_config": db_config,
                "pipeline_mode": pipeline_mode,
                "domain": {
                    "id": mapping["domain_id"] if mapping else None,
                    "name": mapping["domain_name"] if mapping else None,
                    "path_type": mapping["path_type"] if mapping else None,
                    "dynamic_config": mapping["dynamic_config"] if mapping else None,
                    "ui_config_metadata": mapping["ui_config_metadata"] if mapping else None,
                } if mapping else None
            }
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid token format.")

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
            client = await system_db.get_client_by_id(client_id)
            if not client:
                raise HTTPException(status_code=401, detail="Client not found.")
            active_path = client.get("active_path", "customer_support")
            active_domain_id = client.get("active_domain_id")
            if not active_domain_id:
                raise HTTPException(status_code=400, detail="No active domain selected.")

            # Fetch existing configuration to preserve passwords if field is blank
            existing = await system_db.get_client_db_config(client_id, domain_id=active_domain_id)
            
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
            await system_db.save_client_db_config(client_id, config, domain_id=active_domain_id, path_type=active_path)
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
        
        schema = await client.introspect_schema_full()
        return {"success": True, "message": "Database introspected successfully.", "schema": schema}





    @router.post("/api/tenant/db-config/save-rules")
    async def save_db_rules(req: SaveRulesRequest, request: Request, response: Response):
        """Saves DB configuration, SQL rules, and UI metadata for tenant."""
        try:
            client_id = get_authenticated_client_id(request)
        except HTTPException:
            if req.client_id:
                client_id = req.client_id
                response.set_cookie(key="session_token", value=str(client_id), httponly=True, samesite="lax")
            else:
                raise
                
        try:
            client = await system_db.get_client_by_id(client_id)
            if not client:
                raise HTTPException(status_code=401, detail="Client not found.")
            active_path = client.get("active_path", "customer_support")

            existing = await system_db.get_client_db_config(client_id, domain_id=req.domain_id)
            
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
            await system_db.save_client_db_config(client_id, config, domain_id=req.domain_id, path_type=active_path)
            
            import json
            dynamic_config_dict = {
                "identity": req.identity,
                "selected_tables": req.selected_tables
            }
            dyn_json = json.dumps(dynamic_config_dict)
            meta_json = json.dumps(req.ui_config_metadata) if req.ui_config_metadata else None
            await system_db.update_client_domain_mapping(
                client_id=client_id,
                domain_id=req.domain_id,
                dynamic_config=dyn_json,
                ui_config_metadata=meta_json,
                path_type=active_path
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
            
            from app.services.schema_service import SchemaService
            schema_service = SchemaService(dict(db_config))
            metadata = await schema_service.refresh()
            
            return {
                "success": True,
                "tables_found": list(metadata["tables"].keys()),
                "relationships_found": len(metadata["relationships"]),
            }
        except Exception as e:
            logger.error(f"Error refreshing schema: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # -------------------------------------------------------------------------
    # Outreach APIs
    # -------------------------------------------------------------------------

    @router.post("/api/outreach/save-config")
    async def save_outreach_config(req: OutreachConfigRequest, request: Request):
        client_id = get_authenticated_client_id(request)
        try:
            client = await system_db.get_client_by_id(client_id)
            if not client:
                raise HTTPException(status_code=401, detail="Client not found.")
            
            # Outreach config should always be saved under the 'outreach' path_type
            path_type = "outreach"

            # 2. Get the correct outreach domain ID based on the campaign type
            pool = await system_db._get_conn()
            async with pool.acquire() as conn:
                domain_name = "B2B Sales" if req.campaign_type == "sales" else "Real Estate"
                row = await conn.fetchrow("SELECT id FROM domains WHERE path_type = 'outreach' AND name = $1", domain_name)
                if not row:
                    row = await conn.fetchrow("SELECT id FROM domains WHERE path_type = 'outreach' LIMIT 1")
                if not row:
                    raise HTTPException(status_code=500, detail="No outreach domains found in database.")
                domain_id = row["id"]
            
            # 1. Save DB Config
            existing = await system_db.get_client_db_config(client_id, domain_id=domain_id)
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
            await system_db.save_client_db_config(client_id, config, domain_id=domain_id, path_type=path_type)
            
            import json
            dynamic_config_dict = {
                "pipeline_type": "outreach",
                "campaign_type": req.campaign_type,
                "product_table": req.product_table,
                "selected_columns": req.selected_columns,
                "company_name": req.company_name,
                "closing_goal": req.closing_goal
            }
            dyn_json = json.dumps(dynamic_config_dict)
            meta_json = json.dumps(req.ui_config_metadata) if req.ui_config_metadata else None
            
            await system_db.update_client_domain_mapping(
                client_id=client_id,
                domain_id=domain_id,
                dynamic_config=dyn_json,
                ui_config_metadata=meta_json,
                path_type=path_type
            )
            return {"success": True, "message": "Outreach config saved successfully!"}
        except Exception as e:
            logger.error(f"Error saving outreach config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/api/outreach/config")
    async def get_outreach_config(request: Request):
        client_id = get_authenticated_client_id(request)
        try:
            mapping = await system_db.get_client_domain_mapping(client_id, path_type="outreach")
            if not mapping or not mapping.get("dynamic_config"):
                return {"config": None}
            
            import json
            dyn_cfg = json.loads(mapping["dynamic_config"])
            if dyn_cfg.get("pipeline_type") != "outreach":
                return {"config": None}
                
            return {"config": dyn_cfg, "ui_config_metadata": json.loads(mapping.get("ui_config_metadata") or "{}")}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/api/outreach/generate-dummy")
    async def generate_dummy_db(request: Request):
        try:
            req_data = await request.json()
            campaign_type = req_data.get("campaign_type", "sales")
            
            import sqlite3
            import os
            from pathlib import Path
            
            db_path = f"dummy_{campaign_type}_db.sqlite"
            if os.path.exists(db_path):
                os.remove(db_path)
                
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            if campaign_type == "real_estate":
                cursor.execute('''
                    CREATE TABLE properties (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        category TEXT,
                        price TEXT,
                        status TEXT,
                        bedrooms INTEGER,
                        bathrooms REAL,
                        sqft INTEGER,
                        lot_size TEXT,
                        year_built INTEGER,
                        address TEXT,
                        neighborhood TEXT,
                        description TEXT,
                        features TEXT,
                        nearby TEXT,
                        hoa_fee TEXT,
                        property_tax TEXT,
                        open_house TEXT,
                        rating REAL,
                        discount TEXT
                    )
                ''')
                
                json_path = os.path.join("client_configs", "realestate_listings.json")
                if os.path.exists(json_path):
                    import json
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    for prop in data.get("properties", []):
                        features_str = json.dumps(prop.get("features", [])) if "features" in prop else None
                        nearby_str = json.dumps(prop.get("nearby", {})) if "nearby" in prop else None
                        
                        cursor.execute(
                            "INSERT INTO properties VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                prop.get("id"),
                                prop.get("name"),
                                prop.get("category"),
                                prop.get("price"),
                                prop.get("status"),
                                prop.get("bedrooms"),
                                prop.get("bathrooms"),
                                prop.get("sqft"),
                                prop.get("lot_size"),
                                prop.get("year_built"),
                                prop.get("address"),
                                prop.get("neighborhood"),
                                prop.get("description"),
                                features_str,
                                nearby_str,
                                prop.get("hoa_fee"),
                                prop.get("property_tax"),
                                prop.get("open_house"),
                                prop.get("rating"),
                                prop.get("discount")
                            )
                        )
                schema = {"properties": ["id", "name", "category", "price", "status", "bedrooms", "bathrooms", "sqft", "lot_size", "year_built", "address", "neighborhood", "description", "features", "nearby", "hoa_fee", "property_tax", "open_house", "rating", "discount"]}
            else:
                cursor.execute('''
                    CREATE TABLE products (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        category TEXT,
                        price TEXT,
                        in_stock BOOLEAN,
                        rating REAL,
                        description TEXT,
                        discount TEXT
                    )
                ''')
                
                json_path = os.path.join("client_configs", "sales_products.json")
                if os.path.exists(json_path):
                    import json
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    for prod in data.get("products", []):
                        cursor.execute(
                            "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                prod.get("id"),
                                prod.get("name"),
                                prod.get("category"),
                                prod.get("price"),
                                prod.get("in_stock"),
                                prod.get("rating"),
                                prod.get("description"),
                                prod.get("discount")
                            )
                        )
                schema = {"products": ["id", "name", "category", "price", "in_stock", "rating", "description", "discount"]}
                
            conn.commit()
            conn.close()
            
            return {
                "success": True, 
                "db_path": str(Path(db_path).absolute()),
                "schema": schema
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/api/outreach/call")
    async def make_outreach_call(req: OutreachCallRequest, request: Request):
        client_id = get_authenticated_client_id(request)
        try:
            th = get_twilio_handler() if get_twilio_handler else None
            if not th:
                raise HTTPException(status_code=500, detail="Twilio handler is not initialized.")
            
            ngrok_url = os.getenv("NGROK_URL", "")
            if not ngrok_url:
                raise HTTPException(status_code=500, detail="NGROK_URL is not configured.")
                
            import urllib.parse
            encoded_name = urllib.parse.quote(req.customer_name)
            encoded_lang = urllib.parse.quote(req.language or "en")
            
            # Build voice_url — handle NGROK_URL that may already contain /voice
            if "/voice" in ngrok_url:
                voice_url = ngrok_url
                if "?" in voice_url:
                    voice_url += f"&client_id={client_id}&customer_name={encoded_name}&language={encoded_lang}&pipeline_type=outreach"
                else:
                    voice_url += f"?client_id={client_id}&customer_name={encoded_name}&language={encoded_lang}&pipeline_type=outreach"
            else:
                voice_url = f"{ngrok_url.rstrip('/')}/voice?client_id={client_id}&customer_name={encoded_name}&language={encoded_lang}&pipeline_type=outreach"
            
            call_sid = th._client.calls.create(
                to=req.phone_number,
                from_=os.getenv("TWILIO_PHONE_NUMBER"),
                url=voice_url,
                method="POST"
            ).sid
            
            return {"success": True, "call_sid": call_sid}
        except Exception as e:
            logger.error(f"Error making outreach call: {e}")
            raise HTTPException(status_code=500, detail=str(e))


    # -------------------------------------------------------------------------
    # Gemini API Key Management
    # -------------------------------------------------------------------------

    @router.post("/api/tenant/gemini-key")
    async def save_gemini_key(req: GeminiKeyRequest, request: Request):
        """Save or update the client's Gemini API key."""
        try:
            client_id = get_authenticated_client_id(request)
        except HTTPException:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid session or token.")

        if not req.api_key or not req.api_key.strip():
            raise HTTPException(status_code=400, detail="API key cannot be empty.")

        try:
            await system_db.save_client_gemini_key(client_id, req.api_key.strip())
            return {"success": True, "message": "Gemini API key saved successfully."}
        except Exception as e:
            logger.error(f"Error saving Gemini key: {e}")
            raise HTTPException(status_code=500, detail=str(e))


    @router.get("/api/tenant/gemini-key")
    async def get_gemini_key(request: Request):
        """Check if the client has a Gemini API key configured (returns masked preview)."""
        try:
            client_id = get_authenticated_client_id(request)
        except HTTPException:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid session or token.")

        try:
            import os
            server_key_exists = bool(os.getenv("GOOGLE_API_KEY"))
            
            key = await system_db.get_client_gemini_key(client_id)
            if key:
                # Return masked preview (first 8 and last 4 characters)
                masked = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "****"
                return {"has_key": True, "masked_key": masked, "server_key_exists": server_key_exists}
            return {"has_key": False, "masked_key": None, "server_key_exists": server_key_exists}
        except Exception as e:
            logger.error(f"Error retrieving Gemini key: {e}")
            raise HTTPException(status_code=500, detail=str(e))


    @router.delete("/api/tenant/gemini-key")
    async def delete_gemini_key(request: Request):
        """Remove the client's Gemini API key (falls back to env var)."""
        try:
            client_id = get_authenticated_client_id(request)
        except HTTPException:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid session or token.")

        try:
            # Save empty string to clear the key
            await system_db.save_client_gemini_key(client_id, "")
            return {"success": True, "message": "Gemini API key removed. Will use server default."}
        except Exception as e:
            logger.error(f"Error deleting Gemini key: {e}")
            raise HTTPException(status_code=500, detail=str(e))    # -------------------------------------------------------------------------
    # Twilio Configuration Management
    # -------------------------------------------------------------------------

    @router.post("/api/tenant/twilio-config")
    async def save_twilio_config(req: TwilioConfigRequest, request: Request):
        """Save or update the client's Twilio configuration."""
        try:
            client_id = get_authenticated_client_id(request)
        except HTTPException:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid session or token.")

        if not req.account_sid or not req.auth_token or not req.phone_number:
            raise HTTPException(status_code=400, detail="All Twilio configuration fields are required.")

        try:
            await system_db.save_client_twilio_config(
                client_id, req.account_sid.strip(), req.auth_token.strip(), req.phone_number.strip()
            )
            return {"success": True, "message": "Twilio configuration saved successfully."}
        except Exception as e:
            logger.error(f"Error saving Twilio config: {e}")
            raise HTTPException(status_code=500, detail=str(e))


    @router.get("/api/tenant/twilio-config")
    async def get_twilio_config(request: Request):
        """Retrieve the client's Twilio configuration (returns masked token)."""
        try:
            client_id = get_authenticated_client_id(request)
        except HTTPException:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid session or token.")

        try:
            import os
            server_key_exists = bool(os.getenv("TWILIO_ACCOUNT_SID"))
            
            cfg = await system_db.get_client_twilio_config(client_id)
            if cfg and cfg.get("account_sid"):
                masked_token = f"{cfg['auth_token'][:4]}...{cfg['auth_token'][-4:]}" if len(cfg['auth_token']) > 8 else "****"
                return {
                    "has_config": True,
                    "account_sid": cfg["account_sid"],
                    "masked_auth_token": masked_token,
                    "phone_number": cfg["phone_number"],
                    "server_key_exists": server_key_exists
                }
            return {"has_config": False, "server_key_exists": server_key_exists}
        except Exception as e:
            logger.error(f"Error retrieving Twilio config: {e}")
            raise HTTPException(status_code=500, detail=str(e))


    @router.delete("/api/tenant/twilio-config")
    async def delete_twilio_config(request: Request):
        """Remove the client's Twilio configuration (falls back to env vars)."""
        try:
            client_id = get_authenticated_client_id(request)
        except HTTPException:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid session or token.")

        try:
            await system_db.save_client_twilio_config(client_id, "", "", "")
            return {"success": True, "message": "Twilio configuration removed. Will use server default."}
        except Exception as e:
            logger.error(f"Error deleting Twilio config: {e}")
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
    async def get_twilio_call_status(call_sid: str, request: Request):
        """Retrieve the current real-time status of a Twilio call."""
        th = get_twilio_handler() if get_twilio_handler else None
        if not th:
            raise HTTPException(status_code=500, detail="Twilio handler is not initialized on the server.")
        
        client_id = None
        client_id_str = request.cookies.get("session_token")
        if client_id_str:
            try:
                client_id = int(client_id_str)
            except ValueError:
                pass

        try:
            status = await th.get_call_status(call_sid, client_id=client_id)
            return {"success": True, "status": status}
        except Exception as e:
            logger.error(f"Error retrieving Twilio call status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/api/twilio/call/{call_sid}/end")
    async def end_twilio_call(call_sid: str, request: Request):
        """Hangs up / terminates an active Twilio call."""
        th = get_twilio_handler() if get_twilio_handler else None
        if not th:
            raise HTTPException(status_code=500, detail="Twilio handler is not initialized on the server.")

        client_id = None
        client_id_str = request.cookies.get("session_token")
        if client_id_str:
            try:
                client_id = int(client_id_str)
            except ValueError:
                pass

        try:
            success = await th.end_call(call_sid, client_id=client_id)
            return {"success": success}
        except Exception as e:
            logger.error(f"Error ending Twilio call: {e}")
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
