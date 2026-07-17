"""Executor for running dynamic tool queries against PostgreSQL."""

import logging
import asyncpg
from typing import Dict, Any, Optional
from google.genai import types
import datetime

logger = logging.getLogger(__name__)

class DynamicToolExecutor:
    """Executes dynamic SQL maps safely."""

    def __init__(self, db_config: Dict[str, Any], execution_map: Dict[str, str], identity_table: str, identity_name_col: str = None, identity_verify_col: str = None):
        self.db_config = db_config
        self.execution_map = execution_map
        self.identity_table = identity_table
        self.identity_name_col = identity_name_col
        self.identity_verify_col = identity_verify_col
        
        # Connect to Postgres
        self.host = db_config.get("server_name", "localhost")
        self.port = db_config.get("port", 5432)
        self.database = db_config.get("db_name")
        self.user = db_config.get("username")
        self.password = db_config.get("password")

    async def execute(self, tool_call_id: str, name: str, args: dict, state: dict) -> types.FunctionResponse:
        """Execute the tool and return FunctionResponse."""
        if name not in self.execution_map:
            logger.warning(f"Unknown tool call: {name}")
            return types.FunctionResponse(
                name=name, id=tool_call_id, response={"error": f"Unknown function {name}"}
            )
            
        sql = self.execution_map[name]
        logger.info(f"Executing Dynamic Tool: {name} with args {args} - SQL: {sql}")

        try:
            conn = await asyncpg.connect(
                host=self.host, port=self.port, database=self.database, user=self.user, password=self.password
            )
        except Exception as e:
            logger.error(f"Failed to connect to PG for tool execution: {e}")
            return types.FunctionResponse(
                name=name, id=tool_call_id, response={"error": "Database connection failed."}
            )

        try:
            response_data = {}
            
            # 1. Identity Verification Tool (e.g., verify_patients)
            if name == f"verify_{self.identity_table}":
                if state.get("verified"):
                    return types.FunctionResponse(
                        name=name, id=tool_call_id, response={"error": "You are already verified for this session. You cannot change your identity during an active call."}
                    )
                    
                val1 = args.get(self.identity_name_col)
                val2 = args.get(self.identity_verify_col)
                
                if val1 is not None and val2 is not None:
                    rows = await conn.fetch(sql, val1, str(val2))
                    if rows:
                        row = dict(rows[0])
                        # Convert date/time to string
                        for k, v in row.items():
                            if isinstance(v, (datetime.date, datetime.datetime, datetime.time)):
                                row[k] = v.isoformat()
                                
                        state["verified"] = True
                        # Assume the primary key is 'id' or the first column
                        state["identity_id"] = row.get("id") or list(row.values())[0]
                        state["identity_data"] = row
                        
                        response_data = {
                            "verified": True,
                            "message": "Identity successfully verified.",
                            "data": row
                        }
                    else:
                        response_data = {
                            "verified": False,
                            "message": "Verification failed. Record not found."
                        }
                else:
                    response_data = {"error": "Missing required verification parameters."}
                    
            # 2. Linked Table Tool (e.g., get_appointments)
            elif name.startswith("get_"):
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
                        results.append(r)
                    response_data = {"results": results, "count": len(results)}

            # 3. Unlinked/Lookup Tool
            else:
                # Standalone lookup by primary key
                params = list(args.values())
                if params:
                    rows = await conn.fetch(sql, params[0])
                else:
                    rows = await conn.fetch(sql)
                    
                results = []
                for row in rows:
                    r = dict(row)
                    for k, v in r.items():
                        if isinstance(v, (datetime.date, datetime.datetime)):
                            r[k] = v.isoformat()
                    results.append(r)
                response_data = {"results": results}

            return types.FunctionResponse(
                name=name, id=tool_call_id, response=response_data
            )
            
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            return types.FunctionResponse(
                name=name, id=tool_call_id, response={"error": str(e)}
            )
        finally:
            await conn.close()
