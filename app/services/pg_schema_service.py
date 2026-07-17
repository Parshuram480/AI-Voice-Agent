"""Service for introspecting PostgreSQL databases to map schema for LLMs."""

import logging
from typing import Dict, Any, List

import asyncpg

logger = logging.getLogger(__name__)


class PgSchemaService:
    """Introspects PostgreSQL schema using information_schema."""

    def __init__(self, db_config: dict):
        self.db_config = db_config

    async def get_schema_metadata(self) -> Dict[str, Any]:
        """
        Connect to DB, fetch tables, columns, and foreign keys,
        and return a structured metadata dictionary.
        """
        try:
            conn = await asyncpg.connect(
                host=self.db_config.get("server_name", "localhost"),
                port=self.db_config.get("port", 5432),
                database=self.db_config.get("db_name"),
                user=self.db_config.get("username"),
                password=self.db_config.get("password"),
            )
        except Exception as e:
            logger.error(f"Failed to connect to PG for introspection: {e}")
            raise e

        try:
            metadata = {
                "tables": {},
                "relationships": []
            }

            # 1. Get user-defined tables in 'public' schema
            tables_query = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
            tables = await conn.fetch(tables_query)
            for t in tables:
                metadata["tables"][t["table_name"]] = {
                    "columns": {},
                    "primary_key": None,
                    "foreign_keys": []
                }

            # 2. Get columns
            columns_query = """
                SELECT table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
            """
            columns = await conn.fetch(columns_query)
            for c in columns:
                t_name = c["table_name"]
                if t_name in metadata["tables"]:
                    metadata["tables"][t_name]["columns"][c["column_name"]] = {
                        "type": c["data_type"],
                        "nullable": c["is_nullable"] == "YES"
                    }

            # 3. Get primary keys
            pk_query = """
                SELECT kcu.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'
            """
            pks = await conn.fetch(pk_query)
            for pk in pks:
                t_name = pk["table_name"]
                if t_name in metadata["tables"]:
                    metadata["tables"][t_name]["primary_key"] = pk["column_name"]

            # 4. Get foreign keys
            fk_query = """
                SELECT
                    tc.table_name AS from_table,
                    kcu.column_name AS from_column,
                    ccu.table_name AS to_table,
                    ccu.column_name AS to_column
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                  AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
            """
            fks = await conn.fetch(fk_query)
            for fk in fks:
                f_table = fk["from_table"]
                t_table = fk["to_table"]
                if f_table in metadata["tables"] and t_table in metadata["tables"]:
                    rel = {
                        "from_table": f_table,
                        "from_column": fk["from_column"],
                        "to_table": t_table,
                        "to_column": fk["to_column"]
                    }
                    metadata["relationships"].append(rel)
                    metadata["tables"][f_table]["foreign_keys"].append({
                        "column": fk["from_column"],
                        "references_table": t_table,
                        "references_column": fk["to_column"]
                    })

            return metadata
        finally:
            await conn.close()
