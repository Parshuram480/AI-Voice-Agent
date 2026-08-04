"""Executor for running dynamic outreach tools against PostgreSQL."""

import logging
from typing import Dict, Any, Optional
from google.genai import types
import datetime
import decimal

logger = logging.getLogger(__name__)

class OutreachToolExecutor:
    """Executes dynamic SQL maps safely for outreach scenarios (no auth required)."""

    def __init__(self, db_client, execution_map: Dict[str, dict]):
        self._db_client = db_client
        self.execution_map = execution_map

    async def execute(self, tool_call_id: str, name: str, args: dict, state: dict) -> types.FunctionResponse:
        """Execute the tool and return FunctionResponse."""
        if name not in self.execution_map:
            logger.warning(f"Unknown tool call: {name}")
            return types.FunctionResponse(
                name=name, id=tool_call_id, response={"error": f"Unknown function {name}"}
            )
            
        tool_entry = self.execution_map[name]
        tool_type = tool_entry["type"]
        logger.info(f"Executing Outreach Tool: {name} with args {args}")

        try:
            if tool_type == "outreach":
                # Simple queries or search with pre-built SQL
                sql = tool_entry["sql"]
                params = [args.get(k) for k in tool_entry.get("param_order", [])]
                
                if params and params[0] is not None:
                    rows = await self._db_client.execute_query(sql, tuple(params))
                else:
                    rows = await self._db_client.execute_query(sql)
                    
            elif tool_type == "outreach_details":
                base_sql = tool_entry["sql_base"]
                pk_col = tool_entry.get("pk_col")
                name_col = tool_entry.get("name_col")
                db_type = tool_entry.get("db_type")
                
                where_clauses = []
                params = []
                
                if pk_col and pk_col in args:
                    where_clauses.append(f"{pk_col} = ?")
                    params.append(args[pk_col])
                elif name_col and name_col in args:
                    if db_type == "sql server":
                        where_clauses.append(f"LOWER({name_col}) LIKE LOWER('%' + ? + '%')")
                    elif db_type in ("mysql", "mariadb"):
                        where_clauses.append(f"LOWER({name_col}) LIKE LOWER(CONCAT('%', ?, '%'))")
                    else:
                        where_clauses.append(f"LOWER({name_col}) LIKE LOWER('%' || ? || '%')")
                    params.append(args[name_col])
                
                if where_clauses:
                    sql = f"{base_sql} WHERE {' OR '.join(where_clauses)}"
                    rows = await self._db_client.execute_query(sql, tuple(params))
                else:
                    return types.FunctionResponse(
                        name=name, id=tool_call_id, response={"error": "Must provide either ID or Name."}
                    )

            elif tool_type == "outreach_recommend":
                base_sql = tool_entry["sql_base"]
                price_col = tool_entry.get("price_col")
                category_col = tool_entry.get("category_col")
                db_type = tool_entry.get("db_type")
                limit = tool_entry.get("limit", 3)
                
                where_clauses = []
                params = []
                
                if price_col and "max_price" in args:
                    where_clauses.append(f"{price_col} <= ?")
                    params.append(args["max_price"])
                    
                if category_col and "category" in args:
                    if db_type == "sql server":
                        where_clauses.append(f"LOWER({category_col}) LIKE LOWER('%' + ? + '%')")
                    elif db_type in ("mysql", "mariadb"):
                        where_clauses.append(f"LOWER({category_col}) LIKE LOWER(CONCAT('%', ?, '%'))")
                    else:
                        where_clauses.append(f"LOWER({category_col}) LIKE LOWER('%' || ? || '%')")
                    params.append(args["category"])
                    
                sql = base_sql
                if where_clauses:
                    sql += f" WHERE {' AND '.join(where_clauses)}"
                
                if db_type == "sql server":
                    sql += f" OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"
                elif db_type == "oracle":
                    sql += f" FETCH FIRST {limit} ROWS ONLY"
                elif db_type != "sql server":
                    sql += f" LIMIT {limit}"
                    
                if params:
                    rows = await self._db_client.execute_query(sql, tuple(params))
                else:
                    rows = await self._db_client.execute_query(sql)
            else:
                rows = []

            results = []
            for row in rows:
                r = dict(row)
                for k, v in r.items():
                    if isinstance(v, (datetime.date, datetime.datetime, datetime.time)):
                        r[k] = v.isoformat()
                    elif isinstance(v, decimal.Decimal):
                        r[k] = float(v)
                results.append(r)

            response_data = {
                "results": results,
                "count": len(results)
            }
            return types.FunctionResponse(
                name=name, id=tool_call_id, response=response_data
            )
            
        except Exception as e:
            logger.error(f"Database error executing outreach tool {name}: {e}")
            return types.FunctionResponse(
                name=name, id=tool_call_id, response={"error": f"Database error: {str(e)}"}
            )
