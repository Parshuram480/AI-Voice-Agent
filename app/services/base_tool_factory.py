"""Base factory for generating Gemini tools and SQL maps."""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class BaseToolFactory:
    """Base class for generating Gemini function declarations and SQL maps from schema."""

    def __init__(self, config: Dict[str, Any], schema_metadata: Dict[str, Any]):
        self.config = config
        self.schema = schema_metadata
        self.db_type = config.get("database", {}).get("db_type", "postgresql").lower()
        self.selected_tables = config.get("selected_tables", {})

    def _format_query(self, select_cols: str, table_and_joins: str, where_clause: str = "", order_by: str = "", limit: int = None) -> str:
        """Formats the query according to the dialect."""
        if self.db_type == "sql server" and limit and not order_by:
            sql = f"SELECT TOP {limit} {select_cols} FROM {table_and_joins}"
        else:
            sql = f"SELECT {select_cols} FROM {table_and_joins}"
            
        if where_clause:
            sql += f" WHERE {where_clause}"
        if order_by:
            sql += f" ORDER BY {order_by}"
            
        if limit:
            if self.db_type == "sql server" and order_by:
                sql += f" OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"
            elif self.db_type == "oracle":
                sql += f" FETCH FIRST {limit} ROWS ONLY"
            elif self.db_type != "sql server":
                # PostgreSQL, MySQL, SQLite
                sql += f" LIMIT {limit}"
                
        return sql

    def _format_search_clause(self, col: str) -> str:
        """Formats a case-insensitive search clause according to the dialect."""
        if self.db_type == "sql server":
            return f"LOWER({col}) LIKE LOWER('%' + ? + '%')"
        elif self.db_type in ("mysql", "mariadb"):
            return f"LOWER({col}) LIKE LOWER(CONCAT('%', ?, '%'))"
        else:
            # PostgreSQL, SQLite, Oracle
            return f"LOWER({col}) LIKE LOWER('%' || ? || '%')"

    def _is_text_type(self, col_type: str) -> bool:
        """Determines if a column is a searchable text type across all dialects."""
        col_type = col_type.lower()
        return any(t in col_type for t in ("char", "text", "varchar", "nvar", "clob"))

    def _get_json_type(self, pg_type: str) -> str:
        """Map PostgreSQL data types to Gemini OpenAPI types."""
        if not pg_type:
            return "STRING"
        pg_type = pg_type.lower()
        if any(t in pg_type for t in ["int", "serial"]):
            return "INTEGER"
        elif any(t in pg_type for t in ["numeric", "decimal", "real", "double"]):
            return "NUMBER"
        elif any(t in pg_type for t in ["bool"]):
            return "BOOLEAN"
        else:
            return "STRING"
