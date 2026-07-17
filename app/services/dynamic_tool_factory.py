"""Factory for dynamically generating Gemini tools and SQL maps."""

import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

class DynamicToolFactory:
    """Generates Gemini function declarations and SQL maps from schema."""

    def __init__(self, config: Dict[str, Any], schema_metadata: Dict[str, Any]):
        self.config = config
        self.schema = schema_metadata
        self.identity_table = config.get("identity", {}).get("table")
        self.identity_name_col = config.get("identity", {}).get("name_column")
        self.identity_verify_col = config.get("identity", {}).get("verification_column")
        self.selected_tables = config.get("selected_tables", {})

    def _map_pg_type_to_gemini(self, pg_type: str) -> str:
        """Map PostgreSQL data types to Gemini OpenAPI types."""
        pg_type = pg_type.lower()
        if any(t in pg_type for t in ["int", "serial"]):
            return "INTEGER"
        elif any(t in pg_type for t in ["numeric", "decimal", "real", "double"]):
            return "NUMBER"
        elif any(t in pg_type for t in ["bool"]):
            return "BOOLEAN"
        else:
            return "STRING"

    def generate_tools(self) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """
        Returns:
            - List of Gemini function declarations.
            - Dict mapping function names to SQL templates.
        """
        tools = []
        execution_map = {}

        for table_name, selected_cols in self.selected_tables.items():
            if table_name not in self.schema["tables"]:
                logger.warning(f"Table {table_name} not found in schema metadata. Skipping.")
                continue
                
            schema_table = self.schema["tables"][table_name]

            # Determine relationships
            linked_to_identity = False
            foreign_key_col = None
            if table_name != self.identity_table:
                for fk in schema_table.get("foreign_keys", []):
                    if fk["references_table"] == self.identity_table:
                        linked_to_identity = True
                        foreign_key_col = fk["column"]
                        break

            # Handle Identity Table
            if table_name == self.identity_table:
                tool_name = f"verify_{table_name}"
                description = f"Verify user identity in the {table_name} table. REQUIRES both {self.identity_name_col} and {self.identity_verify_col}."
                
                properties = {
                    self.identity_name_col: {"type": "STRING", "description": f"User's {self.identity_name_col}"},
                    self.identity_verify_col: {"type": "STRING", "description": f"User's {self.identity_verify_col}. If this represents a date, you MUST format it as YYYY-MM-DD."}
                }
                
                tools.append({
                    "name": tool_name,
                    "description": description,
                    "parameters": {
                        "type": "OBJECT",
                        "properties": properties,
                        "required": [self.identity_name_col, self.identity_verify_col]
                    }
                })

                # SQL generation
                cols_str = ", ".join(selected_cols)
                sql = f"SELECT {cols_str} FROM {table_name} WHERE LOWER({self.identity_name_col}) ILIKE $1 AND {self.identity_verify_col}::text = $2"
                execution_map[tool_name] = sql

            # Handle Linked Tables (requires identity_id)
            elif linked_to_identity:
                tool_name = f"get_{table_name}"
                description = f"Get records from {table_name} for the verified user. Do not pass parameters, the system will automatically inject the verified user's ID."
                
                # Gemini requires at least an empty object for parameters if they are not explicitly forbidden,
                # but to make it foolproof we define an empty object schema.
                tools.append({
                    "name": tool_name,
                    "description": description,
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "dummy": {"type": "STRING", "description": "Optional dummy parameter"}
                        }
                    }
                })

                cols_str = ", ".join(selected_cols)
                sql = f"SELECT {cols_str} FROM {table_name} WHERE {foreign_key_col} = $1"
                execution_map[tool_name] = sql

            # Handle Unlinked Tables (Standalone search)
            else:
                tool_name = f"lookup_{table_name}"
                description = f"Lookup information in the {table_name} table."
                
                properties = {}
                # Only allow searching by the primary key for simplicity in MVP
                pk = schema_table.get("primary_key")
                if pk and pk in selected_cols:
                    properties[pk] = {"type": "INTEGER", "description": f"The primary key {pk}"}
                
                tools.append({
                    "name": tool_name,
                    "description": description,
                    "parameters": {
                        "type": "OBJECT",
                        "properties": properties,
                        "required": [pk] if pk else []
                    }
                })

                cols_str = ", ".join(selected_cols)
                if pk:
                    sql = f"SELECT {cols_str} FROM {table_name} WHERE {pk} = $1"
                else:
                    sql = f"SELECT {cols_str} FROM {table_name} LIMIT 10" # fallback
                execution_map[tool_name] = sql

        return tools, execution_map
