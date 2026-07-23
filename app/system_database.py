import hashlib
import os
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncpg
from app.utils.prompt_loader import get_prompts
from app.utils.encryption import encrypt, decrypt

logger = logging.getLogger(__name__)

# --- Environment Variables ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "voice_agent")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "postgres")

# Password hashing utilities
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return salt.hex() + ":" + pw_hash.hex()

def verify_password(password: str, hashed: str) -> bool:
    try:
        salt_hex, hash_hex = hashed.split(":")
        salt = bytes.fromhex(salt_hex)
        pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return pw_hash.hex() == hash_hex
    except Exception:
        return False

class SystemDatabase:
    def __init__(self):
        self._pool = None

    async def _get_conn(self):
        if not self._pool:
            try:
                self._pool = await asyncpg.create_pool(
                    host=DB_HOST,
                    port=DB_PORT,
                    database=DB_NAME,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    min_size=1,
                    max_size=10,
                    command_timeout=10,
                )
                await self._init_db()
            except Exception as e:
                logger.error(f"PostgreSQL connection/init failed in SystemDatabase: {e}")
                raise e
        return self._pool

    async def close(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _init_db(self):
        async with self._pool.acquire() as conn:
            # 1. Clients
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id              SERIAL PRIMARY KEY,
                company_name    VARCHAR(255) NOT NULL,
                client_name     VARCHAR(255) NOT NULL,
                email           VARCHAR(255) UNIQUE NOT NULL,
                password_hash   VARCHAR(255) NOT NULL,
                phone           VARCHAR(50),
                status          VARCHAR(50) DEFAULT 'Active',
                created_date    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 2. Domains
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id                  SERIAL PRIMARY KEY,
                name                VARCHAR(255) UNIQUE NOT NULL,
                description         TEXT,
                system_prompt_llm1  TEXT NOT NULL,
                system_prompt_llm2  TEXT NOT NULL,
                tools_schema        TEXT NOT NULL, -- JSON formatted tools array
                status              VARCHAR(50) DEFAULT 'Active',
                created_date        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 3. Client Database Configurations
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS client_database_configurations (
                id                          SERIAL PRIMARY KEY,
                client_id                   INTEGER NOT NULL UNIQUE REFERENCES clients(id) ON DELETE CASCADE,
                db_type                     VARCHAR(50) NOT NULL,
                server_name                 VARCHAR(255),
                port                        INTEGER,
                db_name                     VARCHAR(255) NOT NULL,
                username                    VARCHAR(255),
                password                    VARCHAR(255),
                schema_name                 VARCHAR(255),
                enable_ssl                  INTEGER DEFAULT 0,
                trust_server_certificate    INTEGER DEFAULT 0,
                connection_timeout          INTEGER DEFAULT 5,
                connection_string           TEXT
            );
            """)

            # 4. Client Domain Mappings
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS client_domain_mappings (
                id                  SERIAL PRIMARY KEY,
                client_id           INTEGER NOT NULL UNIQUE REFERENCES clients(id) ON DELETE CASCADE,
                domain_id           INTEGER NOT NULL REFERENCES domains(id),
                dynamic_config      TEXT,
                ui_config_metadata  TEXT,
                status              VARCHAR(50) DEFAULT 'Active'
            );
            ALTER TABLE client_domain_mappings ADD COLUMN IF NOT EXISTS ui_config_metadata TEXT;
            ALTER TABLE client_domain_mappings ADD COLUMN IF NOT EXISTS dynamic_config TEXT;
            """)

        # Seed standard domains
        await self._seed_domains()

    async def _seed_domains(self):
        prompts = get_prompts()
        cascade_prompts = prompts.get("cascade", {})
        
        # Healthcare prompts & schema
        hc_llm1_prompt = cascade_prompts.get("llm1_base", "") + "\n" + prompts.get("multimodal", {}).get("domains", {}).get("healthcare", "")
        hc_llm2_prompt = cascade_prompts.get("llm2_base", "") + "\n" + prompts.get("multimodal", {}).get("domains", {}).get("healthcare", "")

        # Generic Base Tools for all domains
        base_tools = [
            {
                "type": "function",
                "function": {
                    "name": "verify_user",
                    "description": "Verifies user account AND fetches their records automatically. REQUIRES BOTH the defined name and verification fields. NEVER call this tool until the user has explicitly confirmed their verification details.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "User's full name."},
                            "dob": {"type": "string", "description": "Verification field (e.g. YYYY-MM-DD or Phone number)."}
                        },
                        "required": ["name", "dob"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_records",
                    "description": "Fetches associated records and data for the verified user. CRITICAL: NEVER call this tool if the user is not verified yet.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Optional. Automatically ignored by backend."},
                            "dob": {"type": "string", "description": "Optional. Automatically ignored by backend."}
                        }
                    }
                }
            }
        ]

        pool = await self._get_conn()
        async with pool.acquire() as conn:
            # Healthcare Seed
            await conn.execute("""
            INSERT INTO domains (name, description, system_prompt_llm1, system_prompt_llm2, tools_schema)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (name) DO NOTHING
            """,
                "Healthcare",
                "Medical patient assistant for checking appointments and patient records.",
                hc_llm1_prompt,
                hc_llm2_prompt,
                json.dumps(base_tools)
            )

            # Order Tracking Seed
            await conn.execute("""
            INSERT INTO domains (name, description, system_prompt_llm1, system_prompt_llm2, tools_schema)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (name) DO NOTHING
            """,
                "Order Tracking",
                "Customer support voice agent for tracking and checking order delivery status.",
                f"{prompts.get('cascade', {}).get('llm1_base', '')}\n{prompts.get('multimodal', {}).get('domains', {}).get('order tracking', '')}",
                f"{prompts.get('cascade', {}).get('llm2_base', '')}\n{prompts.get('multimodal', {}).get('domains', {}).get('order tracking', '')}",
                json.dumps(base_tools)
            )

            # Other domains
            other_domains = [
                ("Banking", "Client database banking query assistant"),
                ("Insurance", "Client insurance plans check assistant"),
                ("HR", "Corporate HR policies and leaves assistant"),
                ("CRM", "Client relationship database search"),
                ("Education", "Student grades and schedules assistant"),
                ("Hotel", "Room booking status checker"),
                ("Travel", "Flight and travel schedule assistant"),
                ("Logistics", "Delivery status tracker for supply chain"),
                ("Ecommerce", "Store cart status check and support")
            ]
            for name, desc in other_domains:
                domain_key = name.lower()
                await conn.execute("""
                INSERT INTO domains (name, description, system_prompt_llm1, system_prompt_llm2, tools_schema)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (name) DO NOTHING
                """,
                    name, desc, 
                    f"{prompts.get('cascade', {}).get('llm1_base', '')}\n{prompts.get('multimodal', {}).get('domains', {}).get(domain_key, '')}", 
                    f"{prompts.get('cascade', {}).get('llm2_base', '')}\n{prompts.get('multimodal', {}).get('domains', {}).get(domain_key, '')}", 
                    json.dumps(base_tools)
                )

    async def get_domains(self) -> List[Dict[str, Any]]:
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, name, description, status FROM domains WHERE status = 'Active'")
            return [dict(r) for r in rows]

    async def register_client(self, client_data: Dict[str, Any], db_config: Dict[str, Any], domain_id: int) -> int:
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            tx = conn.transaction()
            await tx.start()
            try:
                # 1. Insert client
                client_id = await conn.fetchval("""
                INSERT INTO clients (company_name, client_name, email, password_hash, phone)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                    client_data["company_name"],
                    client_data["client_name"],
                    client_data["email"],
                    hash_password(client_data["password"]),
                    client_data.get("phone")
                )

                # 2. Insert DB Config
                await conn.execute("""
                INSERT INTO client_database_configurations (
                    client_id, db_type, server_name, port, db_name, username, password, schema_name,
                    enable_ssl, trust_server_certificate, connection_timeout, connection_string
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """,
                    client_id,
                    db_config["db_type"],
                    db_config.get("server_name"),
                    db_config.get("port"),
                    db_config["db_name"],
                    db_config.get("username"),
                    encrypt(db_config.get("password")),
                    db_config.get("schema_name"),
                    1 if db_config.get("enable_ssl") else 0,
                    1 if db_config.get("trust_server_certificate") else 0,
                    db_config.get("connection_timeout", 5),
                    encrypt(db_config.get("connection_string"))
                )

                # 3. Mappings queries (Legacy seeding removed for dynamic config)
                await conn.execute("""
                INSERT INTO client_domain_mappings (client_id, domain_id)
                VALUES ($1, $2)
                """, client_id, domain_id)

                await tx.commit()
                return client_id
            except Exception as e:
                await tx.rollback()
                logger.error(f"Failed to register client in PostgreSQL: {e}")
                raise e

    async def get_client_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM clients WHERE email = $1", email)
            return dict(row) if row else None

    async def get_client_by_id(self, client_id: int) -> Optional[Dict[str, Any]]:
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM clients WHERE id = $1", client_id)
            return dict(row) if row else None

    async def get_client_db_config(self, client_id: int) -> Optional[Dict[str, Any]]:
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM client_database_configurations WHERE client_id = $1", client_id)
            if not row:
                return None
            config = dict(row)
            config["password"] = decrypt(config.get("password"))
            config["connection_string"] = decrypt(config.get("connection_string"))
            return config

    async def save_client_db_config(self, client_id: int, db_config: Dict[str, Any]):
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            await conn.execute("""
            INSERT INTO client_database_configurations (
                client_id, db_type, server_name, port, db_name, username, password, schema_name,
                enable_ssl, trust_server_certificate, connection_timeout, connection_string
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (client_id) DO UPDATE SET
                db_type = EXCLUDED.db_type,
                server_name = EXCLUDED.server_name,
                port = EXCLUDED.port,
                db_name = EXCLUDED.db_name,
                username = EXCLUDED.username,
                password = EXCLUDED.password,
                schema_name = EXCLUDED.schema_name,
                enable_ssl = EXCLUDED.enable_ssl,
                trust_server_certificate = EXCLUDED.trust_server_certificate,
                connection_timeout = EXCLUDED.connection_timeout,
                connection_string = EXCLUDED.connection_string
            """,
                client_id,
                db_config["db_type"],
                db_config.get("server_name"),
                db_config.get("port"),
                db_config["db_name"],
                db_config.get("username"),
                encrypt(db_config.get("password")),
                db_config.get("schema_name"),
                1 if db_config.get("enable_ssl") else 0,
                1 if db_config.get("trust_server_certificate") else 0,
                db_config.get("connection_timeout", 5),
                encrypt(db_config.get("connection_string"))
            )

    async def get_client_domain_mapping(self, client_id: int) -> Optional[Dict[str, Any]]:
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
            SELECT m.*, d.name as domain_name, d.system_prompt_llm1, d.system_prompt_llm2, d.tools_schema
            FROM client_domain_mappings m
            JOIN domains d ON m.domain_id = d.id
            WHERE m.client_id = $1
            """, client_id)
            return dict(row) if row else None

    async def update_client_domain_mapping(self, client_id: int, domain_id: int, dynamic_config: str, ui_config_metadata: Optional[str] = None):
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            await conn.execute("""
            INSERT INTO client_domain_mappings (client_id, domain_id, dynamic_config, ui_config_metadata)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (client_id) DO UPDATE SET
                domain_id = EXCLUDED.domain_id,
                dynamic_config = EXCLUDED.dynamic_config,
                ui_config_metadata = EXCLUDED.ui_config_metadata
            """, client_id, domain_id, dynamic_config, ui_config_metadata)

