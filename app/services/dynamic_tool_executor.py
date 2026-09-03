"""Executor for running dynamic tool queries against PostgreSQL."""

import logging
from typing import Dict, Any, Optional
from google.genai import types
import datetime
import decimal

logger = logging.getLogger(__name__)

class DynamicToolExecutor:
    """Executes dynamic SQL maps safely."""

    def __init__(self, db_client, execution_map: Dict[str, dict], identity_table: str, identity_name_col: str = None, identity_verify_col: str = None):
        self._db_client = db_client
        self.execution_map = execution_map
        self.identity_table = identity_table
        self.identity_name_col = identity_name_col
        self.identity_verify_col = identity_verify_col

    async def execute(self, tool_call_id: str, name: str, args: dict, state: dict) -> types.FunctionResponse:
        # 1. Alias resolution for common function names
        if name not in self.execution_map:
            if name == "verify_user" and "verify_user_identity" in self.execution_map:
                name = "verify_user_identity"
            elif name == "verify_user_identity" and "verify_user" in self.execution_map:
                name = "verify_user"
            elif name.startswith("get_") and f"lookup_{name[4:]}" in self.execution_map:
                name = f"lookup_{name[4:]}"
            elif name.startswith("lookup_") and f"get_{name[7:]}" in self.execution_map:
                name = f"get_{name[7:]}"

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
                
                import re
                
                def _normalize_dob(dob_str: str) -> str:
                    clean = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', str(dob_str).lower().strip())
                    clean = clean.replace(',', ' ').strip()
                    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%m-%d-%Y", "%m/%d/%Y", "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y"):
                        try:
                            return datetime.datetime.strptime(clean, fmt).strftime("%Y-%m-%d")
                        except ValueError:
                            pass
                    return str(dob_str).strip()

                params = []
                for k in tool_entry.get("param_order", args.keys()):
                    val = args.get(k)
                    if val is None:
                        # Synonym fallback matching
                        if k in (self.identity_name_col, "full_name", "name", "customer_name", "username"):
                            val = args.get("name") or args.get("full_name") or args.get("customer_name") or args.get("username")
                        elif k in (self.identity_verify_col, "date_of_birth", "dob", "birth_date"):
                            val = args.get("dob") or args.get("date_of_birth") or args.get("birth_date") or args.get("date")

                    if isinstance(val, str):
                        if k == self.identity_name_col or k in ("name", "full_name", "username"):
                            clean_val = re.sub(r'[^\w\s]', '%', val)
                            clean_val = re.sub(r'%+', '%', clean_val).strip()
                            val = f"%{clean_val}%"
                        elif "date" in k.lower() or "birth" in k.lower() or "dob" in k.lower() or k == self.identity_verify_col:
                            val = _normalize_dob(val)
                    params.append(val)
                rows = await self._db_client.execute_query(sql, tuple(params))

                if not rows:
                    response_data = {
                        "verified": False,
                        "message": f"No record found in {self.identity_table} matching provided details."
                    }
                else:
                    row = rows[0]
                    # Convert date/time to string, and Decimal to float
                    for k, v in row.items():
                        if isinstance(v, (datetime.date, datetime.datetime, datetime.time)):
                            row[k] = v.isoformat()
                        elif isinstance(v, decimal.Decimal):
                            row[k] = float(v)

                    response_data = {
                        "verified": True,
                        "user_details": row,
                        "message": "User verified successfully."
                    }

                    # Preload caller memory facts directly into verification response
                    try:
                        from app.system_database import SystemDatabase
                        sys_db = SystemDatabase()
                        name_val = row.get(self.identity_name_col) or row.get("full_name") or row.get("name")
                        id_val = row.get("id")
                        phone_val = row.get("phone") or row.get("phone_number") or row.get("phone_num") or state.get("caller_phone") or state.get("caller_identifier")
                        
                        raw_cid = state.get("client_id")
                        client_id_val = int(raw_cid) if raw_cid and str(raw_cid).isdigit() else 1
                        
                        merged_profile_data = {}
                        candidate_keys = []
                        for cand in [name_val, str(id_val) if id_val is not None else None, phone_val]:
                            if cand and str(cand).strip():
                                clean_cand = str(cand).strip()
                                if clean_cand not in candidate_keys:
                                    candidate_keys.append(clean_cand)
                                p = await sys_db.get_caller_profile(client_id_val, None, clean_cand)
                                if p and p.get("profile_data"):
                                    for k, v in p["profile_data"].items():
                                        v_val = v.get("value") if isinstance(v, dict) else v
                                        if v_val is not None and str(v_val).strip() != "" and str(v_val).lower() not in ("none", "null", "no known allergies", "no allergies"):
                                            merged_profile_data[k] = v
                                        elif k not in merged_profile_data:
                                            merged_profile_data[k] = v

                        if merged_profile_data:
                            response_data["caller_profile_preferences"] = {
                                k: v.get("value") if isinstance(v, dict) else v
                                for k, v in merged_profile_data.items()
                            }
                            # Sync merged data across candidate identifiers for consistency
                            for clean_cand in candidate_keys:
                                try:
                                    await sys_db.upsert_caller_profile(client_id_val, state.get("domain_id"), clean_cand, merged_profile_data)
                                except Exception:
                                    pass
                    except Exception as mem_fetch_err:
                        logger.warning(f"Could not attach caller memory to verification response: {mem_fetch_err}")
                    
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
                    final_sql = tool_entry.get("sql", sql)
                    params = [state["identity_id"]]
                    
                    if "base_sql" in tool_entry:
                        final_sql = tool_entry["base_sql"]
                        search_query = args.get("search_query")
                        
                        if search_query and tool_entry.get("search_sql"):
                            final_sql += tool_entry["search_sql"]
                            params.extend([search_query] * tool_entry.get("param_count", 0))
                            
                        final_sql += tool_entry.get("order_limit_sql", "")
                        
                    rows = await self._db_client.execute_query(final_sql, tuple(params))
                    
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
                    # In DynamicToolFactory we made all unlinked queries use `param_order = ["search_query"] * len(search_cols)`
                    # Wait, if param_order has multiple entries of the same search_query, params will naturally be a list of the same values!
                    rows = await self._db_client.execute_query(sql, tuple(params))
                else:
                    rows = await self._db_client.execute_query(sql)
                
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
