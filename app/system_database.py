import hashlib
import os
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncpg

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
                verification_query  TEXT NOT NULL,
                data_query          TEXT NOT NULL,
                ui_config_metadata  TEXT,
                status              VARCHAR(50) DEFAULT 'Active'
            );
            ALTER TABLE client_domain_mappings ADD COLUMN IF NOT EXISTS ui_config_metadata TEXT;
            """)

        # Seed standard domains
        await self._seed_domains()

    async def _seed_domains(self):
        # Healthcare prompts & schema
        hc_llm1_prompt = """You are the first point of contact for a healthcare patient assistant. Speak in 1-2 short sentences. No markdown, no emojis, no symbols. This is spoken over the phone.

TOPICS YOU ALLOW:
- Greetings like "Hello" or "Hi" - reply politely and briefly.
- Audio checks like "Can you hear me?" — reply "Yes, I can hear you."
- Any requests about checking appointment details, schedules, or patient record status.

TOPICS YOU REFUSE:
- General knowledge questions (weather, math, news, facts, people, etc). Say: "I can only help with patient record and appointment questions."
- Requests to check someone else's records (a friend, spouse, coworker, etc). Say: "I can only help with your own account."
- NOTE: If the user says something like "tell me what is my appointment status", DO NOT refuse them. Simply follow the VERIFICATION STEPS.

TOOL RULES:
- Never write JSON, tags, or function names out loud. Only use the tool_calls mechanism.
- Never guess or make up patient details. If a detail isn't in the tool output, say you don't have that information.
- Only call get_patient_records if the patient is verified.

VERIFICATION STEPS (only for unverified users, do these in order):
1. Ask: "Can I have your full name please?"
2. Ask: "Can I have your date of birth please?"
3. Once you have both name and date of birth, say: "So your name is [name] and your date of birth is [date], is that correct?"
4. Wait for their confirmation.
   - If they say Yes (or confirm it is correct): call verify_user now.
   - If they say No, or say that something is wrong: ask "Which one is wrong, your name or your date of birth?"
     - If they say the name is wrong, ask only for the correct name.
     - If they say the date of birth is wrong, ask only for the correct date of birth.
     - After getting the correction, go back to step 3.
-- Never call verify_user unless the user has explicitly confirmed BOTH pieces of info in step 3."""

        hc_llm2_prompt = """You are a helpful medical assistant. 
You are speaking over the phone. Speak in 1-2 short sentences. No markdown, no emojis, no symbols.
You have just received information from a backend tool (e.g. appointment list or verification result).
Your job is to read the tool output and formulate a polite, conversational reply to the user based on the tool result.
If the tool says verification failed, explain why politely and ask for their information again.
If the tool provides appointment details, summarize them briefly and politely. For example: "Your appointment with Dr. Sarah Connor is scheduled for July 20, 2026."
DO NOT invent information. DO NOT write JSON or tags out loud."""

        hc_tools = [
            {
                "type": "function",
                "function": {
                    "name": "verify_user",
                    "description": "Verifies patient account AND fetches their records automatically. REQUIRES BOTH full name and DOB. NEVER call this tool until the user has explicitly answered 'Yes' to confirm their Name and DOB.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Patient's full name."},
                            "dob": {"type": "string", "description": "YYYY-MM-DD. Ask for missing info (e.g. year) if incomplete."}
                        },
                        "required": ["name", "dob"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_patient_records",
                    "description": "Fetches medical records and appointments for verified patient. CRITICAL: NEVER call this tool if the user is not verified yet.",
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

        # Order Tracking prompts & schema
        ot_llm1_prompt = """You are the first point of contact for an order system. Speak in 1-2 short sentences. No markdown, no emojis, no symbols. This is spoken over the phone.

TOPICS YOU ALLOW:
- Greetings like "Hello" or "Hi" — reply politely and briefly.
- Audio checks like "Can you hear me?" — reply "Yes, I can hear you."
- Any requests about order status, tracking, or delivery.

TOPICS YOU REFUSE:
- General knowledge questions (weather, math, news, facts, people, etc). Say: "I can only help with order related questions."
- Requests to check someone else's order (a friend, spouse, coworker, etc). Say: "I can only help with your own account."
- NOTE: If the user says something like "tell me what is my orders status", DO NOT refuse them. Simply follow the VERIFICATION STEPS.

TOOL RULES:
- Never write JSON, tags, or function names out loud. Only use the tool_calls mechanism.
- Never guess or make up order details (like costs or prices). If a detail isn't in the tool output, say you don't have that information.
- Only call get_order_status if the user is verified.

VERIFICATION STEPS (only for unverified users, do these in order):
1. Ask: "Can I have your full name please?"
2. Ask: "Can I have your date of birth please?"
3. Once you have both name and date of birth, say: "So your name is [name] and your date of birth is [date], is that correct?"
4. Wait for their confirmation.
   - If they say Yes (or confirm it is correct): call verify_user now.
   - If they say No, or say that something is wrong (e.g. "My name is wrong"): ask "Which one is wrong, your name or your date of birth?"
     - If they say the name is wrong, ask only for the correct name.
     - If they say the date of birth is wrong, ask only for the correct date of birth.
     - After getting the correction, go back to step 3.
-- Never call verify_user unless the user has explicitly confirmed BOTH pieces of info in step 3."""

        ot_llm2_prompt = """You are a helpful customer support agent for an order system. 
You are speaking over the phone. Speak in 1-2 short sentences. No markdown, no emojis, no symbols.
You have just received information from a backend tool (e.g. order status or verification result).
Your job is to read the tool output and formulate a polite, conversational reply to the user based on the tool result.
If the tool says verification failed, explain why politely and ask for their information again.
If the tool provides order details, summarize them briefly and politely.
DO NOT invent information. DO NOT write JSON or tags out loud."""

        ot_tools = [
            {
                "type": "function",
                "function": {
                    "name": "verify_user",
                    "description": "Verifies account AND fetches their orders automatically. REQUIRES BOTH full name and DOB. NEVER call this tool until the user has explicitly answered 'Yes' to confirm their Name and DOB.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "User's full name."},
                            "dob": {"type": "string", "description": "YYYY-MM-DD. Ask for missing info (e.g. year) if incomplete."}
                        },
                        "required": ["name", "dob"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_order_status",
                    "description": "Fetches latest orders for verified user. CRITICAL: NEVER call this tool if the user is not verified yet.",
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
                json.dumps(hc_tools)
            )

            # Order Tracking Seed
            await conn.execute("""
            INSERT INTO domains (name, description, system_prompt_llm1, system_prompt_llm2, tools_schema)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (name) DO NOTHING
            """,
                "Order Tracking",
                "Customer support voice agent for tracking and checking order delivery status.",
                ot_llm1_prompt,
                ot_llm2_prompt,
                json.dumps(ot_tools)
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
                await conn.execute("""
                INSERT INTO domains (name, description, system_prompt_llm1, system_prompt_llm2, tools_schema)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (name) DO NOTHING
                """,
                    name, desc, ot_llm1_prompt, ot_llm2_prompt, json.dumps(ot_tools)
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
                    db_config.get("password"),
                    db_config.get("schema_name"),
                    1 if db_config.get("enable_ssl") else 0,
                    1 if db_config.get("trust_server_certificate") else 0,
                    db_config.get("connection_timeout", 5),
                    db_config.get("connection_string")
                )

                # 3. Mappings queries
                domain_name = await conn.fetchval("SELECT name FROM domains WHERE id = $1", domain_id)
                if not domain_name:
                    domain_name = "Order Tracking"

                if domain_name == "Healthcare":
                    v_query = "SELECT id, full_name, date_of_birth, phone FROM patients WHERE LOWER(full_name) = ? AND date_of_birth = ? AND deleted_at IS NULL LIMIT 1"
                    d_query = "SELECT appointment_date, doctor_name, reason, status FROM appointments WHERE patient_id = ? AND deleted_at IS NULL ORDER BY appointment_date DESC"
                else:
                    v_query = "SELECT id, full_name, date_of_birth, phone FROM customers WHERE LOWER(full_name) = ? AND date_of_birth = ? AND deleted_at IS NULL LIMIT 1"
                    d_query = "SELECT order_number, status, estimated_arrival, items_summary FROM orders WHERE customer_id = ? AND deleted_at IS NULL ORDER BY created_at DESC"

                await conn.execute("""
                INSERT INTO client_domain_mappings (client_id, domain_id, verification_query, data_query)
                VALUES ($1, $2, $3, $4)
                """, client_id, domain_id, v_query, d_query)

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
            return dict(row) if row else None

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
                db_config.get("password"),
                db_config.get("schema_name"),
                1 if db_config.get("enable_ssl") else 0,
                1 if db_config.get("trust_server_certificate") else 0,
                db_config.get("connection_timeout", 5),
                db_config.get("connection_string")
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

    async def update_client_domain_mapping(self, client_id: int, domain_id: int, verification_query: str, data_query: str, ui_config_metadata: Optional[str] = None):
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            await conn.execute("""
            INSERT INTO client_domain_mappings (client_id, domain_id, verification_query, data_query, ui_config_metadata)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (client_id) DO UPDATE SET
                domain_id = EXCLUDED.domain_id,
                verification_query = EXCLUDED.verification_query,
                data_query = EXCLUDED.data_query,
                ui_config_metadata = EXCLUDED.ui_config_metadata
            """, client_id, domain_id, verification_query, data_query, ui_config_metadata)
