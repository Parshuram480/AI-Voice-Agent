"""Executor for running dynamic tool queries against PostgreSQL."""

import logging
import asyncpg
from typing import Dict, Any, Optional
from google.genai import types
import datetime
import decimal

logger = logging.getLogger(__name__)

class DynamicToolExecutor:
    """Executes dynamic SQL maps safely."""

    def __init__(self, pool: asyncpg.Pool, execution_map: Dict[str, dict], identity_table: str, identity_name_col: str = None, identity_verify_col: str = None):
        self._pool = pool
        self.execution_map = execution_map
        self.identity_table = identity_table
        self.identity_name_col = identity_name_col
        self.identity_verify_col = identity_verify_col

    async def execute(self, tool_call_id: str, name: str, args: dict, state: dict) -> types.FunctionResponse:
        """Execute the tool and return FunctionResponse."""
        if name not in self.execution_map:
            logger.warning(f"Unknown tool call: {name}")
            return types.FunctionResponse(
                name=name, id=tool_call_id, response={"error": f"Unknown function {name}"}
            )
            
        tool_entry = self.execution_map[name]
        sql = tool_entry["sql"]
        tool_type = tool_entry["type"]
        limit = tool_entry.get("limit")
        logger.info(f"Executing Dynamic Tool: {name} with args {args} - SQL: {sql}")

        try:
            response_data = {}
            async with self._pool.acquire() as conn:
                if name.startswith("verify_"):
                    # SECURITY FIX: Prevent re-authentication hijacking
                    if state.get("verified") is True:
                        logger.warning(f"SECURITY BLOCK: Attempted re-authentication. Current state: {state}")
                        response_data = {
                            "verified": True,
                            "error": "SECURITY BLOCK: A user is already verified in this session. You cannot verify as a different person during the same call."
                        }
                        return types.FunctionResponse(name=name, id=tool_call_id, response=response_data)

                    # Execute verification logic
                    logger.info(f"Running verification for args: {args}")
                    
                    params = [args.get(k) for k in tool_entry.get("param_order", args.keys())]
                    rows = await conn.fetch(sql, *params)
                    
                    if not rows:
                        response_data = {
                            "verified": False,
                            "message": f"No record found in {self.identity_table} matching provided details."
                        }
                    else:
                        row = dict(rows[0])
                        # Convert date/time to string
                        for k, v in row.items():
                            if isinstance(v, (datetime.date, datetime.datetime, datetime.time)):
                                row[k] = v.isoformat()

                        response_data = {
                            "verified": True,
                            "user_details": row,
                            "message": "User verified successfully."
                        }
                        
                        # Set identity_id in state
                        pk_col = tool_entry.get("pk_col")
                        if pk_col and pk_col in row:
                            state["identity_id"] = row[pk_col]
                        else:
                            # Fallback if no PK is defined in schema
                            state["identity_id"] = list(row.keys())[0] if row else None
                        state["verified"] = True
                        
                elif tool_type == "linked":
                    # Linked Table Tool (e.g., get_appointments)
                    logger.info(f"Running linked query for args: {args}")
                    if not state.get("verified") or not state.get("identity_id"):
                        response_data = {"error": "User not verified. Please verify identity first."}
                    else:
                        rows = await conn.fetch(sql, state["identity_id"])
                        
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
                        if limit and len(results) >= limit:
                            response_data["note"] = f"Results limited to top {limit}."
                
                else:
                    # Unlinked lookup execution
                    logger.info(f"Running unlinked query for args: {args}")
                    
                    params = [args.get(k) for k in tool_entry.get("param_order", args.keys())]
                    if params and params[0] is not None:
                        rows = await conn.fetch(sql, params[0])
                    else:
                        rows = await conn.fetch(sql)
                    
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
                    if limit and len(results) >= limit:
                        response_data["note"] = f"Results limited to top {limit}."

            return types.FunctionResponse(
                name=name, id=tool_call_id, response=response_data
            )
            
        except Exception as e:
            logger.error(f"Database error executing tool {name}: {e}")
            return types.FunctionResponse(
                name=name, id=tool_call_id, response={"error": f"Database error: {str(e)}"}
            )
