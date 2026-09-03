import hashlib
import os
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv
import asyncpg
from app.utils.prompt_loader import get_prompts
from app.utils.encryption import encrypt, decrypt

load_dotenv()
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
    _instance = None
    _init_lock = None # Will be set to threading.Lock() on first load

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SystemDatabase, cls).__new__(cls)
            cls._instance._pool = None
            cls._instance._lock = None
            
            import threading
            cls._init_lock = threading.Lock()
        return cls._instance

    def __init__(self):
        pass

    async def _get_conn(self):
        if self._lock is None:
            with self._init_lock:
                if self._lock is None:
                    import asyncio
                    self._lock = asyncio.Lock()
            
        if not self._pool:
            async with self._lock:
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
                active_path     VARCHAR(50) DEFAULT 'customer_support',
                active_domain_id INTEGER,
                created_date    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            ALTER TABLE clients ADD COLUMN IF NOT EXISTS active_domain_id INTEGER;
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
                path_type           VARCHAR(50) DEFAULT 'customer_support',
                status              VARCHAR(50) DEFAULT 'Active',
                created_date        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            await conn.execute("ALTER TABLE domains ADD COLUMN IF NOT EXISTS path_type VARCHAR(50) DEFAULT 'customer_support';")

            # 3. Client Database Configurations
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS client_database_configurations (
                id                          SERIAL PRIMARY KEY,
                client_id                   INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                domain_id                   INTEGER REFERENCES domains(id) ON DELETE CASCADE,
                path_type                   VARCHAR(50) DEFAULT 'customer_support',
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
                connection_string           TEXT,
                UNIQUE(client_id, domain_id)
            );
            ALTER TABLE client_database_configurations ADD COLUMN IF NOT EXISTS domain_id INTEGER REFERENCES domains(id) ON DELETE CASCADE;
            """)

            # 4. Client Domain Mappings
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS client_domain_mappings (
                id                  SERIAL PRIMARY KEY,
                client_id           INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                domain_id           INTEGER NOT NULL REFERENCES domains(id),
                path_type           VARCHAR(50) DEFAULT 'customer_support',
                dynamic_config      TEXT,
                ui_config_metadata  TEXT,
                status              VARCHAR(50) DEFAULT 'Active',
                UNIQUE(client_id, domain_id)
            );
            ALTER TABLE client_domain_mappings ADD COLUMN IF NOT EXISTS ui_config_metadata TEXT;
            ALTER TABLE client_domain_mappings ADD COLUMN IF NOT EXISTS dynamic_config TEXT;
            ALTER TABLE client_domain_mappings ADD COLUMN IF NOT EXISTS path_type VARCHAR(50) DEFAULT 'customer_support';
            """)

            # 5. Call Logs
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS call_logs (
                session_id              VARCHAR(100) PRIMARY KEY,
                user_id                 INTEGER,
                pipeline_mode           VARCHAR(50),
                history                 JSONB,
                summary                 TEXT,
                intent                  VARCHAR(100),
                total_input_tokens          INTEGER DEFAULT 0,
                total_output_tokens         INTEGER DEFAULT 0,
                total_input_output_tokens   INTEGER DEFAULT 0,
                summary_input_tokens        INTEGER DEFAULT 0,
                summary_output_tokens       INTEGER DEFAULT 0,
                summary_input_output_tokens INTEGER DEFAULT 0,
                total_tokens                INTEGER DEFAULT 0,
                average_latency         FLOAT,
                client_id               INTEGER,
                domain                  VARCHAR(255),
                total_input_cost        DECIMAL(10, 6) DEFAULT 0.0,
                total_output_cost       DECIMAL(10, 6) DEFAULT 0.0,
                total_cost              DECIMAL(10, 6) DEFAULT 0.0,
                created_at              TIMESTAMPTZ DEFAULT NOW()
            );
            """)

            # 6. Fix Constraints for multi-domain support (Migration)
            for constraint_query in [
                "ALTER TABLE client_database_configurations DROP CONSTRAINT IF EXISTS client_database_configurations_client_id_path_type_key;",
                "ALTER TABLE client_database_configurations DROP CONSTRAINT IF EXISTS client_database_configurations_client_id_key;",
                "ALTER TABLE client_domain_mappings DROP CONSTRAINT IF EXISTS client_domain_mappings_client_id_path_type_key;",
                "ALTER TABLE client_domain_mappings DROP CONSTRAINT IF EXISTS client_domain_mappings_client_id_key;"
            ]:
                try:
                    await conn.execute(constraint_query)
                except Exception as e:
                    logger.debug(f"Constraint drop exception: {e}")

            try:
                await conn.execute("ALTER TABLE client_database_configurations ADD CONSTRAINT client_database_configurations_client_id_domain_id_key UNIQUE (client_id, domain_id);")
            except Exception as e:
                pass

            try:
                await conn.execute("ALTER TABLE client_domain_mappings ADD CONSTRAINT client_domain_mappings_client_id_domain_id_key UNIQUE (client_id, domain_id);")
            except Exception as e:
                pass
                
            # 6. Backfill legacy data to avoid domain_id=NULL blocking access
            try:
                await conn.execute('''
                    UPDATE clients c
                    SET active_domain_id = m.domain_id
                    FROM client_domain_mappings m
                    WHERE c.id = m.client_id AND c.active_domain_id IS NULL
                ''')
                await conn.execute('''
                    UPDATE client_database_configurations cfg
                    SET domain_id = m.domain_id
                    FROM client_domain_mappings m
                    WHERE cfg.client_id = m.client_id AND cfg.path_type = m.path_type AND cfg.domain_id IS NULL
                ''')
            except Exception as e:
                logger.warning(f"Warning backfilling domain_id: {e}")
            # Ensure all Gemini and Twilio credential columns exist (from develop)
            await conn.execute("ALTER TABLE client_database_configurations ADD COLUMN IF NOT EXISTS gemini_api_key VARCHAR(255);")
            await conn.execute("ALTER TABLE client_database_configurations ADD COLUMN IF NOT EXISTS twilio_account_sid VARCHAR(255);")
            await conn.execute("ALTER TABLE client_database_configurations ADD COLUMN IF NOT EXISTS twilio_auth_token VARCHAR(255);")
            await conn.execute("ALTER TABLE client_database_configurations ADD COLUMN IF NOT EXISTS twilio_phone_number VARCHAR(50);")

            # 7. Continuous Learning: Caller Semantic Profiles
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS caller_profiles (
                id                  SERIAL PRIMARY KEY,
                client_id           INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                domain_id           INTEGER REFERENCES domains(id) ON DELETE CASCADE,
                caller_identifier   VARCHAR(255) NOT NULL,
                profile_data        JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(client_id, domain_id, caller_identifier)
            );
            CREATE INDEX IF NOT EXISTS idx_caller_profiles_lookup ON caller_profiles(client_id, domain_id, caller_identifier);
            CREATE INDEX IF NOT EXISTS idx_caller_profiles_gin ON caller_profiles USING gin (profile_data);
            """)

            # 8. Continuous Learning: Post-Call Quality Evaluations (LLM-as-a-Judge)
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS call_evaluations (
                id                      SERIAL PRIMARY KEY,
                session_id              VARCHAR(100) REFERENCES call_logs(session_id) ON DELETE CASCADE,
                client_id               INTEGER,
                domain_id               INTEGER,
                task_completion_score   INTEGER DEFAULT 0,
                friction_score          INTEGER DEFAULT 1,
                tool_accuracy_score     INTEGER DEFAULT 0,
                evaluation_details      JSONB DEFAULT '{}'::jsonb,
                mistakes_detected       JSONB DEFAULT '[]'::jsonb,
                actionable_lessons      JSONB DEFAULT '[]'::jsonb,
                extracted_facts         JSONB DEFAULT '{}'::jsonb,
                created_at              TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_call_evaluations_session ON call_evaluations(session_id);
            CREATE INDEX IF NOT EXISTS idx_call_evaluations_client_domain ON call_evaluations(client_id, domain_id);
            """)

            # 9. Continuous Learning: Procedural Learned Rules
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS domain_learned_rules (
                id                  SERIAL PRIMARY KEY,
                client_id           INTEGER REFERENCES clients(id) ON DELETE CASCADE,
                domain_id           INTEGER REFERENCES domains(id) ON DELETE CASCADE,
                rule_category       VARCHAR(100) DEFAULT 'general',
                trigger_condition   TEXT NOT NULL,
                instruction         TEXT NOT NULL,
                confidence_score    FLOAT DEFAULT 1.0,
                status              VARCHAR(50) DEFAULT 'active',
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_learned_rules_domain_status ON domain_learned_rules(domain_id, status);
            """)

            # 10. Continuous Learning: Vectorized Caller Semantic Memories (pgvector Memory RAG)
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS caller_memory_vectors (
                    id                  SERIAL PRIMARY KEY,
                    client_id           INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    domain_id           INTEGER REFERENCES domains(id) ON DELETE CASCADE,
                    caller_identifier   VARCHAR(255) NOT NULL,
                    memory_key          VARCHAR(100) NOT NULL,
                    content             TEXT NOT NULL,
                    embedding           vector(768) NOT NULL,
                    confidence_score    FLOAT DEFAULT 1.0,
                    created_at          TIMESTAMPTZ DEFAULT NOW(),
                    updated_at          TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(client_id, domain_id, caller_identifier, memory_key)
                );
                CREATE INDEX IF NOT EXISTS idx_caller_memory_vectors_lookup 
                    ON caller_memory_vectors(client_id, domain_id, caller_identifier);
                CREATE INDEX IF NOT EXISTS idx_caller_memory_hnsw 
                    ON caller_memory_vectors USING hnsw (embedding vector_cosine_ops);
                """)
            except Exception as vec_init_err:
                logger.warning(f"pgvector native table init warning (falling back to jsonb if extension absent): {vec_init_err}")
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS caller_memory_vectors (
                    id                  SERIAL PRIMARY KEY,
                    client_id           INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    domain_id           INTEGER REFERENCES domains(id) ON DELETE CASCADE,
                    caller_identifier   VARCHAR(255) NOT NULL,
                    memory_key          VARCHAR(100) NOT NULL,
                    content             TEXT NOT NULL,
                    embedding           JSONB NOT NULL,
                    confidence_score    FLOAT DEFAULT 1.0,
                    created_at          TIMESTAMPTZ DEFAULT NOW(),
                    updated_at          TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(client_id, domain_id, caller_identifier, memory_key)
                );
                CREATE INDEX IF NOT EXISTS idx_caller_memory_vectors_lookup 
                    ON caller_memory_vectors(client_id, domain_id, caller_identifier);
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
            INSERT INTO domains (name, description, system_prompt_llm1, system_prompt_llm2, tools_schema, path_type)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (name) DO NOTHING
            """,
                "Healthcare",
                "Medical patient assistant for checking appointments and patient records.",
                hc_llm1_prompt,
                hc_llm2_prompt,
                json.dumps(base_tools),
                "customer_support"
            )

            # Order Tracking Seed
            await conn.execute("""
            INSERT INTO domains (name, description, system_prompt_llm1, system_prompt_llm2, tools_schema, path_type)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (name) DO NOTHING
            """,
                "Order Tracking",
                "Customer support voice agent for tracking and checking order delivery status.",
                f"{prompts.get('cascade', {}).get('llm1_base', '')}\n{prompts.get('multimodal', {}).get('domains', {}).get('order tracking', '')}",
                f"{prompts.get('cascade', {}).get('llm2_base', '')}\n{prompts.get('multimodal', {}).get('domains', {}).get('order tracking', '')}",
                json.dumps(base_tools),
                "customer_support"
            )

            # Other Customer Support domains
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
                INSERT INTO domains (name, description, system_prompt_llm1, system_prompt_llm2, tools_schema, path_type)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (name) DO NOTHING
                """,
                    name, desc, 
                    f"{prompts.get('cascade', {}).get('llm1_base', '')}\n{prompts.get('multimodal', {}).get('domains', {}).get(domain_key, '')}", 
                    f"{prompts.get('cascade', {}).get('llm2_base', '')}\n{prompts.get('multimodal', {}).get('domains', {}).get(domain_key, '')}", 
                    json.dumps(base_tools),
                    "customer_support"
                )

            # Outreach domains
            outreach_domains = [
                ("B2B Sales", "Proactive outbound B2B software/hardware sales agent"),
                ("Real Estate", "Proactive outbound property listings agent")
            ]
            for name, desc in outreach_domains:
                # Use a generic outreach prompt base if specific domain prompt is missing
                domain_key = "outreach" 
                await conn.execute("""
                INSERT INTO domains (name, description, system_prompt_llm1, system_prompt_llm2, tools_schema, path_type)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (name) DO NOTHING
                """,
                    name, desc, 
                    f"{prompts.get('cascade', {}).get('llm1_base', '')}\n{prompts.get('multimodal', {}).get('domains', {}).get(domain_key, '')}", 
                    f"{prompts.get('cascade', {}).get('llm2_base', '')}\n{prompts.get('multimodal', {}).get('domains', {}).get(domain_key, '')}", 
                    json.dumps(base_tools),
                    "outreach"
                )

    async def get_domains(self) -> List[Dict[str, Any]]:
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, name, description, status, path_type FROM domains WHERE status = 'Active'")
            return [dict(r) for r in rows]

    async def register_client(self, client_data: Dict[str, Any], db_config: Dict[str, Any], domain_id: int) -> int:
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            tx = conn.transaction()
            await tx.start()
            try:
                # 0. Get the path_type for the selected domain
                domain_row = await conn.fetchrow("SELECT path_type FROM domains WHERE id = $1", domain_id)
                path_type = domain_row["path_type"] if domain_row else "customer_support"

                # 1. Insert client
                client_id = await conn.fetchval("""
                INSERT INTO clients (company_name, client_name, email, password_hash, phone, active_path, active_domain_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
                """,
                    client_data["company_name"],
                    client_data["client_name"],
                    client_data["email"],
                    hash_password(client_data["password"]),
                    client_data.get("phone"),
                    path_type,
                    domain_id
                )

                # 2. Insert DB Config
                await conn.execute("""
                INSERT INTO client_database_configurations (
                    client_id, domain_id, path_type, db_type, server_name, port, db_name, username, password, schema_name,
                    enable_ssl, trust_server_certificate, connection_timeout, connection_string
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                """,
                    client_id,
                    domain_id,
                    path_type,
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
                INSERT INTO client_domain_mappings (client_id, domain_id, path_type)
                VALUES ($1, $2, $3)
                """, client_id, domain_id, path_type)

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

    async def get_client_db_config(self, client_id: int, domain_id: Optional[int] = None, path_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            if domain_id is not None:
                row = await conn.fetchrow("""
                    SELECT * FROM client_database_configurations
                    WHERE client_id = $1 AND domain_id = $2
                """, client_id, domain_id)
            elif path_type is not None:
                row = await conn.fetchrow("""
                    SELECT cdc.* FROM client_database_configurations cdc
                    JOIN client_domain_mappings m ON cdc.domain_id = m.domain_id AND cdc.client_id = m.client_id
                    JOIN domains d ON m.domain_id = d.id
                    WHERE cdc.client_id = $1 AND d.path_type = $2
                    ORDER BY cdc.id DESC LIMIT 1
                """, client_id, path_type)
            else:
                row = await conn.fetchrow("""
                    SELECT * FROM client_database_configurations
                    WHERE client_id = $1
                    AND domain_id = (SELECT active_domain_id FROM clients WHERE id = $1)
                """, client_id)
                
            if not row:
                return None
            config = dict(row)
            config["password"] = decrypt(config.get("password"))
            config["connection_string"] = decrypt(config.get("connection_string"))
            config["gemini_api_key"] = decrypt(config.get("gemini_api_key")) if config.get("gemini_api_key") else None
            config["twilio_auth_token"] = decrypt(config.get("twilio_auth_token")) if config.get("twilio_auth_token") else None
            return config

    async def save_client_db_config(self, client_id: int, db_config: Dict[str, Any], domain_id: int, path_type: str = 'customer_support'):
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            await conn.execute("""
            INSERT INTO client_database_configurations (
                client_id, domain_id, path_type, db_type, server_name, port, db_name, username, password, schema_name,
                enable_ssl, trust_server_certificate, connection_timeout, connection_string
            ) VALUES ($1, $2, $3::varchar, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT (client_id, domain_id) DO UPDATE SET
                path_type = EXCLUDED.path_type,
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
                domain_id,
                path_type,
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


    async def save_client_gemini_key(self, client_id: int, api_key: str):
        """Save encrypted Gemini API key for a client."""
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            await conn.execute("""
            UPDATE client_database_configurations
            SET gemini_api_key = $1
            WHERE client_id = $2
            """, encrypt(api_key), client_id)

    async def get_client_gemini_key(self, client_id: int) -> Optional[str]:
        """Get decrypted Gemini API key for a client."""
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT gemini_api_key FROM client_database_configurations WHERE client_id = $1",
                client_id
            )
            if row and row["gemini_api_key"]:
                return decrypt(row["gemini_api_key"])
            return None

    async def save_client_twilio_config(self, client_id: int, account_sid: str, auth_token: str, phone_number: str):
        """Save encrypted Twilio config for a client."""
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            await conn.execute("""
            UPDATE client_database_configurations
            SET twilio_account_sid = $1,
                twilio_auth_token = $2,
                twilio_phone_number = $3
            WHERE client_id = $4
            """, account_sid, encrypt(auth_token) if auth_token else "", phone_number, client_id)

    async def get_client_twilio_config(self, client_id: int) -> Optional[Dict[str, Any]]:
        """Get decrypted Twilio configuration for a client."""
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
            SELECT twilio_account_sid, twilio_auth_token, twilio_phone_number
            FROM client_database_configurations
            WHERE client_id = $1
            """, client_id)
            if row and row["twilio_account_sid"]:
                return {
                    "account_sid": row["twilio_account_sid"],
                    "auth_token": decrypt(row["twilio_auth_token"]) if row["twilio_auth_token"] else "",
                    "phone_number": row["twilio_phone_number"]
                }
            return None

    async def get_client_domain_mapping(self, client_id: int, domain_id: Optional[int] = None, path_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            if domain_id is not None:
                row = await conn.fetchrow("""
                SELECT m.*, d.name as domain_name, d.path_type as mapped_path_type, d.system_prompt_llm1, d.system_prompt_llm2, d.tools_schema, c.company_name
                FROM client_domain_mappings m
                JOIN domains d ON m.domain_id = d.id
                JOIN clients c ON m.client_id = c.id
                WHERE m.client_id = $1 AND m.domain_id = $2
                """, client_id, domain_id)
            elif path_type is not None:
                row = await conn.fetchrow("""
                SELECT m.*, d.name as domain_name, d.path_type as mapped_path_type, d.system_prompt_llm1, d.system_prompt_llm2, d.tools_schema, c.company_name
                FROM client_domain_mappings m
                JOIN domains d ON m.domain_id = d.id
                JOIN clients c ON m.client_id = c.id
                WHERE m.client_id = $1 AND d.path_type = $2
                ORDER BY m.id DESC LIMIT 1
                """, client_id, path_type)
            else:
                row = await conn.fetchrow("""
                SELECT m.*, d.name as domain_name, d.path_type as mapped_path_type, d.system_prompt_llm1, d.system_prompt_llm2, d.tools_schema, c.company_name
                FROM client_domain_mappings m
                JOIN domains d ON m.domain_id = d.id
                JOIN clients c ON m.client_id = c.id
                WHERE m.client_id = $1 AND m.domain_id = (SELECT active_domain_id FROM clients WHERE id = $1)
                """, client_id)
            return dict(row) if row else None

    async def update_client_domain_mapping(self, client_id: int, domain_id: int, dynamic_config: str, ui_config_metadata: Optional[str] = None, path_type: str = 'customer_support'):
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            await conn.execute("""
            INSERT INTO client_domain_mappings (client_id, domain_id, path_type, dynamic_config, ui_config_metadata)
            VALUES ($1, $2, $3::varchar, $4, $5)
            ON CONFLICT (client_id, domain_id) DO UPDATE SET
                path_type = EXCLUDED.path_type,
                dynamic_config = EXCLUDED.dynamic_config,
                ui_config_metadata = EXCLUDED.ui_config_metadata
            """, client_id, domain_id, path_type, dynamic_config, ui_config_metadata)

    async def update_client_profile(self, client_id: int, company_name: str, client_name: str, email: str, phone: Optional[str], domain_id: int):
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            tx = conn.transaction()
            await tx.start()
            try:
                # Get the path_type of the selected domain
                domain_row = await conn.fetchrow("SELECT path_type FROM domains WHERE id = $1", domain_id)
                new_path_type = domain_row["path_type"] if domain_row else "customer_support"

                # 1. Update basic client profile details and set their new active_path and active_domain_id
                await conn.execute("""
                UPDATE clients
                SET company_name = $1, client_name = $2, email = $3, phone = $4, active_path = $6, active_domain_id = $7
                WHERE id = $5
                """, company_name, client_name, email, phone, client_id, new_path_type, domain_id)

                await tx.commit()
            except Exception as e:
                await tx.rollback()
                logger.error(f"Failed to execute profile updates: {e}")
                raise e

    # --- Continuous Learning: Caller Profile Methods ---
    async def get_caller_profile(self, client_id: int, domain_id: Optional[int], caller_identifier: str) -> Optional[Dict[str, Any]]:
        """Fetch caller profile/semantic memory for a specific caller under a client/domain."""
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            if domain_id is not None:
                row = await conn.fetchrow("""
                SELECT * FROM caller_profiles
                WHERE client_id = $1 AND domain_id = $2 AND caller_identifier = $3
                """, client_id, domain_id, caller_identifier)
            else:
                row = await conn.fetchrow("""
                SELECT * FROM caller_profiles
                WHERE client_id = $1 AND caller_identifier = $2
                ORDER BY updated_at DESC LIMIT 1
                """, client_id, caller_identifier)
            
            if row:
                result = dict(row)
                if isinstance(result.get("profile_data"), str):
                    result["profile_data"] = json.loads(result["profile_data"])
                return result
            return None

    async def upsert_caller_profile(self, client_id: int, domain_id: Optional[int], caller_identifier: str, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update caller semantic memory."""
        pool = await self._get_conn()
        json_data = json.dumps(profile_data)
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
            INSERT INTO caller_profiles (client_id, domain_id, caller_identifier, profile_data, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, NOW())
            ON CONFLICT (client_id, domain_id, caller_identifier)
            DO UPDATE SET
                profile_data = EXCLUDED.profile_data,
                updated_at = NOW()
            RETURNING *;
            """, client_id, domain_id, caller_identifier, json_data)
            
            result = dict(row)
            if isinstance(result.get("profile_data"), str):
                result["profile_data"] = json.loads(result["profile_data"])
            return result

    # --- Continuous Learning: Call Evaluation Methods ---
    async def save_call_evaluation(self, evaluation_data: Dict[str, Any]) -> bool:
        """Save post-call quality evaluation scores and analysis."""
        session_id = evaluation_data.get("session_id")
        client_id = evaluation_data.get("client_id")
        domain_id = evaluation_data.get("domain_id")
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            try:
                # Ensure a placeholder record in call_logs exists for chat or voice sessions so FK constraint is satisfied
                if session_id:
                    await conn.execute("""
                    INSERT INTO call_logs (session_id, client_id, pipeline_mode, history, summary, intent, total_tokens, total_cost)
                    VALUES ($1, $2, 'chat', '[]'::jsonb, 'Interaction evaluation', 'chat', 0, 0.0)
                    ON CONFLICT (session_id) DO NOTHING;
                    """, session_id, client_id)

                await conn.execute("""
                INSERT INTO call_evaluations (
                    session_id, client_id, domain_id,
                    task_completion_score, friction_score, tool_accuracy_score,
                    evaluation_details, mistakes_detected, actionable_lessons, extracted_facts
                ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9::jsonb, $10::jsonb)
                """,
                session_id,
                client_id,
                domain_id,
                evaluation_data.get("task_completion_score", 0),
                evaluation_data.get("friction_score", 1),
                evaluation_data.get("tool_accuracy_score", 0),
                json.dumps(evaluation_data.get("evaluation_details", {})),
                json.dumps(evaluation_data.get("mistakes_detected", [])),
                json.dumps(evaluation_data.get("actionable_lessons", [])),
                json.dumps(evaluation_data.get("extracted_facts", {}))
                )
                return True
            except Exception as e:
                logger.error(f"Failed to save call evaluation: {e}")
                return False


    async def get_call_evaluation(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve evaluation details for a call session."""
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
            SELECT * FROM call_evaluations WHERE session_id = $1
            """, session_id)
            if row:
                result = dict(row)
                for json_col in ("evaluation_details", "mistakes_detected", "actionable_lessons", "extracted_facts"):
                    if isinstance(result.get(json_col), str):
                        result[json_col] = json.loads(result[json_col])
                return result
            return None

    # --- Continuous Learning: Procedural Learned Rules ---
    async def get_active_learned_rules(self, client_id: Optional[int], domain_id: Optional[int], limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch active procedural guidelines for prompt injection."""
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
            SELECT * FROM domain_learned_rules
            WHERE status = 'active'
              AND (client_id = $1 OR client_id IS NULL)
              AND (domain_id = $2 OR domain_id IS NULL)
            ORDER BY confidence_score DESC, updated_at DESC
            LIMIT $3
            """, client_id, domain_id, limit)
            return [dict(r) for r in rows]

    async def upsert_learned_rule(
        self,
        client_id: Optional[int],
        domain_id: Optional[int],
        rule_category: str,
        trigger_condition: str,
        instruction: str,
        confidence_score: float = 1.0,
        status: str = 'active'
    ) -> Dict[str, Any]:
        """Add or update a learned procedural rule."""
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
            INSERT INTO domain_learned_rules (
                client_id, domain_id, rule_category, trigger_condition, instruction, confidence_score, status, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            RETURNING *;
            """, client_id, domain_id, rule_category, trigger_condition, instruction, confidence_score, status)
            return dict(row)

    # --- Continuous Learning: Vectorized Caller Semantic Memories (pgvector Memory RAG) ---
    async def upsert_memory_vector(
        self,
        client_id: int,
        domain_id: Optional[int],
        caller_identifier: str,
        memory_key: str,
        content: str,
        embedding: List[float],
        confidence_score: float = 1.0
    ) -> Dict[str, Any]:
        """Insert or update a caller memory vector embedding using native pgvector or JSONB."""
        pool = await self._get_conn()
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
        async with pool.acquire() as conn:
            try:
                # Try native pgvector column insertion
                row = await conn.fetchrow("""
                INSERT INTO caller_memory_vectors (
                    client_id, domain_id, caller_identifier, memory_key, content, embedding, confidence_score, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6::vector, $7, NOW())
                ON CONFLICT (client_id, domain_id, caller_identifier, memory_key)
                DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    confidence_score = EXCLUDED.confidence_score,
                    updated_at = NOW()
                RETURNING id, client_id, domain_id, caller_identifier, memory_key, content, confidence_score, created_at, updated_at;
                """, client_id, domain_id, caller_identifier, memory_key, content, vec_str, confidence_score)
                res = dict(row)
                res["embedding"] = embedding
                return res
            except Exception as vec_err:
                logger.warning(f"Native vector insert fallback error: {type(vec_err)} - {vec_err}")
                emb_json = json.dumps(embedding)
                row = await conn.fetchrow("""
                INSERT INTO caller_memory_vectors (
                    client_id, domain_id, caller_identifier, memory_key, content, embedding, confidence_score, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, NOW())
                ON CONFLICT (client_id, domain_id, caller_identifier, memory_key)
                DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    confidence_score = EXCLUDED.confidence_score,
                    updated_at = NOW()
                RETURNING *;
                """, client_id, domain_id, caller_identifier, memory_key, content, emb_json, confidence_score)
                res = dict(row)
                if isinstance(res.get("embedding"), str):
                    res["embedding"] = json.loads(res["embedding"])
                return res

    async def delete_stale_memory_vectors(
        self,
        client_id: int,
        domain_id: Optional[int],
        caller_identifier: str,
        active_keys: List[str]
    ) -> bool:
        """Deletes vector memory chunks that are no longer present in the active profile."""
        if not active_keys:
            return False
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            try:
                if domain_id:
                    await conn.execute("""
                    DELETE FROM caller_memory_vectors
                    WHERE client_id = $1 AND domain_id = $2 AND caller_identifier = $3
                      AND memory_key != ALL($4::text[])
                    """, client_id, domain_id, caller_identifier, active_keys)
                else:
                    await conn.execute("""
                    DELETE FROM caller_memory_vectors
                    WHERE client_id = $1 AND caller_identifier = $2
                      AND memory_key != ALL($3::text[])
                    """, client_id, caller_identifier, active_keys)
                return True
            except Exception as del_err:
                logger.warning(f"Error cleaning up stale vector memories: {del_err}")
                return False

    async def get_memory_vectors_for_caller(
        self,
        client_id: int,
        domain_id: Optional[int],
        caller_identifier: str
    ) -> List[Dict[str, Any]]:
        """Retrieve all vector memory chunks for a given caller."""
        pool = await self._get_conn()
        async with pool.acquire() as conn:
            if domain_id:
                rows = await conn.fetch("""
                SELECT id, client_id, domain_id, caller_identifier, memory_key, content, confidence_score, created_at, updated_at
                FROM caller_memory_vectors
                WHERE client_id = $1 AND domain_id = $2 AND caller_identifier = $3
                ORDER BY updated_at DESC
                """, client_id, domain_id, caller_identifier)
            else:
                rows = await conn.fetch("""
                SELECT id, client_id, domain_id, caller_identifier, memory_key, content, confidence_score, created_at, updated_at
                FROM caller_memory_vectors
                WHERE client_id = $1 AND caller_identifier = $2
                ORDER BY updated_at DESC
                """, client_id, caller_identifier)
            
            return [dict(r) for r in rows]

    async def search_caller_memory_vectors(
        self,
        client_id: int,
        domain_id: Optional[int],
        caller_identifier: str,
        query_vector: List[float],
        top_k: int = 3,
        min_similarity: float = 0.5
    ) -> List[Dict[str, Any]]:
        """Perform semantic Top-K cosine similarity search using native pgvector cosine operator (<=>) with HNSW."""
        if not query_vector:
            return []
        
        vec_str = "[" + ",".join(str(x) for x in query_vector) + "]"
        pool = await self._get_conn()
        
        try:
            async with pool.acquire() as conn:
                if domain_id:
                    rows = await conn.fetch("""
                    SELECT id, client_id, domain_id, caller_identifier, memory_key, content, confidence_score,
                           (1 - (embedding <=> $4::vector)) AS similarity,
                           created_at, updated_at
                    FROM caller_memory_vectors
                    WHERE client_id = $1 AND domain_id = $2 AND caller_identifier = $3
                      AND (1 - (embedding <=> $4::vector)) >= $5
                    ORDER BY embedding <=> $4::vector ASC
                    LIMIT $6;
                    """, client_id, domain_id, caller_identifier, vec_str, min_similarity, top_k)
                else:
                    rows = await conn.fetch("""
                    SELECT id, client_id, domain_id, caller_identifier, memory_key, content, confidence_score,
                           (1 - (embedding <=> $3::vector)) AS similarity,
                           created_at, updated_at
                    FROM caller_memory_vectors
                    WHERE client_id = $1 AND caller_identifier = $2
                      AND (1 - (embedding <=> $3::vector)) >= $4
                    ORDER BY embedding <=> $3::vector ASC
                    LIMIT $5;
                    """, client_id, caller_identifier, vec_str, min_similarity, top_k)

                results = []
                for r in rows:
                    item = dict(r)
                    item["similarity"] = round(float(item["similarity"]), 4)
                    results.append(item)
                return results

        except Exception as native_err:
            logger.debug(f"pgvector native search fallback to in-memory cosine: {native_err}")
            # In-memory fallback if pgvector operator fails
            vectors = await self.get_memory_vectors_for_caller(client_id, domain_id, caller_identifier)
            if not vectors:
                return []

            scored_memories = []
            norm_q = sum(x * x for x in query_vector) ** 0.5
            if norm_q == 0:
                return []

            for vec in vectors:
                emb = vec.get("embedding", [])
                if not emb or len(emb) != len(query_vector):
                    continue
                
                dot = sum(a * b for a, b in zip(query_vector, emb))
                norm_v = sum(x * x for x in emb) ** 0.5
                if norm_v == 0:
                    continue
                
                sim = dot / (norm_q * norm_v)
                if sim >= min_similarity:
                    vec_copy = dict(vec)
                    vec_copy["similarity"] = round(sim, 4)
                    scored_memories.append(vec_copy)

            scored_memories.sort(key=lambda x: x["similarity"], reverse=True)
            return scored_memories[:top_k]




