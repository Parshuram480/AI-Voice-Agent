"""Factory for dynamically generating Gemini tools and SQL maps."""

import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

class DynamicToolFactory:
    """Generates Gemini function declarations and SQL maps from schema."""
    MAX_TOOLS = 7

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

    def generate_tools(self) -> Tuple[List[Dict[str, Any]], Dict[str, dict]]:
        """
        Returns:
            - List of Gemini function declarations.
            - Dict mapping function names to SQL tool execution metadata (sql, type, limit).
        """
        tools = []
        execution_map: Dict[str, dict] = {}

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
                description = f"Verify user identity in the {table_name} table. REQUIRES BOTH {self.identity_name_col} and {self.identity_verify_col}. NEVER call this tool if the user has not explicitly provided BOTH of these details. Do NOT guess or hallucinate missing information."
                
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

                # Ensure PK is in the selected columns so we can use it for state
                pk = schema_table.get("primary_key")
                if pk and pk not in selected_cols:
                    selected_cols.insert(0, pk)

                # SQL generation
                cols_str = ", ".join(selected_cols)
                sql = f"SELECT {cols_str} FROM {table_name} WHERE LOWER({self.identity_name_col}) ILIKE $1 AND {self.identity_verify_col}::text = $2"
                execution_map[tool_name] = {
                    "sql": sql,
                    "type": "identity",
                    "limit": 1,
                    "pk_col": pk,
                    "param_order": [self.identity_name_col, self.identity_verify_col]
                }

            # Handle Linked Tables (requires identity_id)
            elif linked_to_identity:
                tool_name = f"get_{table_name}"
                description = f"Get records from {table_name} for the verified user. Do not pass parameters, the system will automatically inject the verified user's ID."
                
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

                pk = schema_table.get("primary_key", selected_cols[0])
                
                # Auto-JOIN logic
                join_clauses = []
                extra_cols = []
                for fk in schema_table.get("foreign_keys", []):
                    ref_table = fk["references_table"]
                    if ref_table == self.identity_table:
                        continue  # Skip identity link
                    if ref_table not in self.schema["tables"]:
                        continue
                    
                    ref_schema = self.schema["tables"][ref_table]
                    display_cols = []
                    for col_name, col_info in ref_schema["columns"].items():
                        if col_info["type"] in ("character varying", "text", "varchar"):
                            display_cols.append(col_name)
                    
                    if display_cols:
                        join_clauses.append(
                            f"LEFT JOIN {ref_table} ON {table_name}.{fk['column']} = {ref_table}.{fk['references_column']}"
                        )
                        for d_col in display_cols:
                            alias = f"{ref_table}_{d_col}"
                            extra_cols.append(f"{ref_table}.{d_col} AS {alias}")

                all_cols = [f"{table_name}.{c}" for c in selected_cols] + extra_cols
                cols_str = ", ".join(all_cols)
                joins = " ".join(join_clauses)
                
                sql = f"SELECT {cols_str} FROM {table_name} {joins} WHERE {table_name}.{foreign_key_col} = $1 ORDER BY {table_name}.{pk} DESC LIMIT 10"
                execution_map[tool_name] = {
                    "sql": sql,
                    "type": "linked",
                    "limit": 10
                }

            # Handle Unlinked Tables (Standalone search)
            else:
                tool_name = f"lookup_{table_name}"
                description = f"Lookup information in the {table_name} table."
                pk = schema_table.get("primary_key")
                
                # Find all text columns for search
                search_cols = []
                for col_name, col_info in schema_table["columns"].items():
                    if col_name in selected_cols and col_info["type"] in ("character varying", "text", "varchar"):
                        search_cols.append(f"{table_name}.{col_name}")

                # Auto-JOIN logic
                join_clauses = []
                extra_cols = []
                for fk in schema_table.get("foreign_keys", []):
                    ref_table = fk["references_table"]
                    if ref_table not in self.schema["tables"]:
                        continue
                    
                    ref_schema = self.schema["tables"][ref_table]
                    display_cols = []
                    for col_name, col_info in ref_schema["columns"].items():
                        if col_info["type"] in ("character varying", "text", "varchar"):
                            display_cols.append(col_name)
                    
                    if display_cols:
                        join_clauses.append(
                            f"LEFT JOIN {ref_table} ON {table_name}.{fk['column']} = {ref_table}.{fk['references_column']}"
                        )
                        for d_col in display_cols:
                            alias = f"{ref_table}_{d_col}"
                            extra_cols.append(f"{ref_table}.{d_col} AS {alias}")
                            search_cols.append(f"{ref_table}.{d_col}")

                properties = {}
                required = []
                all_cols = [f"{table_name}.{c}" for c in selected_cols] + extra_cols
                cols_str = ", ".join(all_cols)
                joins = " ".join(join_clauses)
                
                if search_cols:
                    desc_cols = " or ".join([c.split('.')[-1] for c in search_cols])
                    properties["search_query"] = {
                        "type": "STRING",
                        "description": f"Search term to find records by {desc_cols}."
                    }
                    required.append("search_query")
                    
                    where_clauses = [f"{col} ILIKE '%' || $1 || '%'" for col in search_cols]
                    where_str = " OR ".join(where_clauses)
                    sql = f"SELECT {cols_str} FROM {table_name} {joins} WHERE {where_str} LIMIT 5"
                elif pk and pk in selected_cols:
                    properties[pk] = {"type": "INTEGER", "description": f"The primary key {pk}"}
                    required.append(pk)
                    sql = f"SELECT {cols_str} FROM {table_name} {joins} WHERE {table_name}.{pk} = $1 LIMIT 5"
                else:
                    # fallback
                    sql = f"SELECT {cols_str} FROM {table_name} {joins} LIMIT 5"
                
                tools.append({
                    "name": tool_name,
                    "description": description,
                    "parameters": {
                        "type": "OBJECT",
                        "properties": properties,
                        "required": required
                    }
                })

                execution_map[tool_name] = {
                    "sql": sql,
                    "type": "unlinked",
                    "limit": 5,
                    "param_order": ["search_query"]
                }

        # Apply Hard Cap
        if len(tools) > self.MAX_TOOLS:
            identity_tools = [t for t in tools if t["name"].startswith("verify_")]
            linked_tools = [t for t in tools if t["name"].startswith("get_")]
            
            # Sort linked_tools by number of columns as a proxy for "importance"
            linked_tools.sort(key=lambda t: len(self.selected_tables.get(t["name"][4:], [])), reverse=True)
            
            unlinked_tools = [t for t in tools if t["name"].startswith("lookup_")]
            
            prioritized = identity_tools + linked_tools + unlinked_tools
            excluded = prioritized[self.MAX_TOOLS:]
            tools = prioritized[:self.MAX_TOOLS]
            
            for t in excluded:
                execution_map.pop(t["name"], None)
                
            logger.warning(
                f"Tool cap reached ({self.MAX_TOOLS}). Excluded: "
                f"{[t['name'] for t in excluded]}"
            )

        return tools, execution_map
