"""Factory for dynamically generating Outreach Gemini tools and SQL maps."""

import logging
from typing import Dict, Any, List, Tuple
from app.services.base_tool_factory import BaseToolFactory

logger = logging.getLogger(__name__)

class OutreachToolFactory(BaseToolFactory):
    """Generates sales-oriented Gemini function declarations and SQL maps from a product table schema."""
    MAX_TOOLS = 5

    def __init__(self, config: Dict[str, Any], schema_metadata: Dict[str, Any]):
        super().__init__(config, schema_metadata)
        self.product_table = config.get("product_table")
        self.selected_columns = config.get("selected_columns", [])
        
        # If no explicit columns were selected, select all columns except ID/timestamps by default
        if not self.selected_columns and self.product_table in self.schema.get("tables", {}):
            for col in self.schema["tables"][self.product_table]["columns"].keys():
                if col.lower() not in ("id", "created_at", "updated_at"):
                    self.selected_columns.append(col)

    def generate_tools(self) -> Tuple[List[Dict[str, Any]], Dict[str, dict]]:
        tools = []
        execution_map = {}

        if not self.product_table or self.product_table not in self.schema.get("tables", {}):
            logger.error(f"Product table '{self.product_table}' not found in schema.")
            return tools, execution_map

        schema_table = self.schema["tables"][self.product_table]
        pk = schema_table.get("primary_key")
        
        # Ensure PK is in selected_cols for identification
        if pk and pk not in self.selected_columns:
            self.selected_columns.insert(0, pk)

        # Identify numeric and text columns for search/recommendations
        numeric_cols = []
        text_cols = []
        for col_name, col_info in schema_table["columns"].items():
            if col_name in self.selected_columns:
                if self._is_text_type(col_info["type"]):
                    text_cols.append(col_name)
                elif self._get_json_type(col_info["type"]) in ("INTEGER", "NUMBER"):
                    if col_name != pk:
                        numeric_cols.append(col_name)

        cols_str = ", ".join(self.selected_columns)
        table_name = self.product_table

        # 1. get_all_products
        tool_name = "get_all_products"
        tools.append({
            "name": tool_name,
            "description": f"Get a general list of available {table_name}.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "dummy": {"type": "STRING", "description": "Optional dummy parameter"}
                }
            }
        })
        execution_map[tool_name] = {
            "sql": self._format_query(cols_str, table_name, limit=10),
            "type": "outreach",
            "param_order": []
        }

        # 2. search_products
        if text_cols:
            tool_name = "search_products"
            desc_cols = " or ".join(text_cols)
            tools.append({
                "name": tool_name,
                "description": f"Search for {table_name} by keyword matching {desc_cols}.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "search_query": {
                            "type": "STRING",
                            "description": "Keyword to search for."
                        }
                    },
                    "required": ["search_query"]
                }
            })
            where_clauses = [self._format_search_clause(col) for col in text_cols]
            where_str = " OR ".join(where_clauses)
            execution_map[tool_name] = {
                "sql": self._format_query(cols_str, table_name, where_clause=where_str, limit=5),
                "type": "outreach",
                "param_order": ["search_query"] * len(text_cols)
            }

        # 3. get_product_details
        tool_name = "get_product_details"
        properties = {}
        required = []
        if pk:
            properties[pk] = {"type": "INTEGER", "description": f"The exact {pk} of the product."}
        
        # Find a suitable "name" column for the fallback search
        name_col = next((c for c in text_cols if "name" in c.lower() or "title" in c.lower()), None)
        if name_col:
            properties[name_col] = {"type": "STRING", "description": f"The exact {name_col} of the product."}

        if properties:
            # We want at least one of these to be provided, but GenAI doesn't support oneOf easily, so we make them optional but instruct the model.
            tools.append({
                "name": tool_name,
                "description": f"Get full details for a specific product from {table_name}. Provide either the {pk} or the {name_col}.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": properties
                }
            })
            
            # The executor will need special logic to handle dynamic WHERE based on which param is provided.
            execution_map[tool_name] = {
                "sql_base": self._format_query(cols_str, table_name),
                "type": "outreach_details",
                "pk_col": pk,
                "name_col": name_col,
                "db_type": self.db_type # Pass down for the search clause in executor
            }

        # 4. recommend_product (if we have price/budget and category)
        price_col = next((c for c in numeric_cols if "price" in c.lower() or "cost" in c.lower() or "budget" in c.lower()), None)
        category_col = next((c for c in text_cols if "category" in c.lower() or "type" in c.lower()), None)
        
        if price_col or category_col:
            tool_name = "recommend_product"
            rec_props = {}
            if price_col:
                rec_props["max_price"] = {"type": "NUMBER", "description": f"Maximum {price_col} the customer is willing to pay."}
            if category_col:
                rec_props["category"] = {"type": "STRING", "description": f"The preferred {category_col}."}

            tools.append({
                "name": tool_name,
                "description": f"Recommend {table_name} based on customer preferences.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": rec_props
                }
            })
            
            execution_map[tool_name] = {
                "sql_base": self._format_query(cols_str, table_name),
                "type": "outreach_recommend",
                "price_col": price_col,
                "category_col": category_col,
                "db_type": self.db_type,
                "limit": 3
            }

        return tools[:self.MAX_TOOLS], execution_map
