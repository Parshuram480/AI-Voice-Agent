"""Assembler for combining dynamic context into a system prompt."""

import logging
from typing import Dict, Any, List
from app.utils.prompt_loader import get_prompts

logger = logging.getLogger(__name__)

class DynamicPromptAssembler:
    """Combines base rules, domain prompts, and DB relationship context using centralized YAML prompts."""

    @staticmethod
    def assemble(config: Dict[str, Any], schema: Dict[str, Any], tools: List[Dict[str, Any]]) -> str:
        prompts_yaml = get_prompts()
        multimodal_prompts = prompts_yaml.get("multimodal", {})
        
        base_prompt = multimodal_prompts.get("base_prompt", "You are a helpful assistant.")
        
        domain = config.get("domain", "default").lower()
        domain_prompts = multimodal_prompts.get("domains", {})
        domain_prompt = domain_prompts.get(domain, "")
        
        identity_table = config.get("identity", {}).get("table")
        identity_name = config.get("identity", {}).get("name_column")
        identity_verify = config.get("identity", {}).get("verification_column")
        
        context_lines = [
            "\n--- DATABASE SCHEMA CONTEXT ---",
            f"The '{identity_table}' table is the central identity table.",
            f"To verify a user, you must ask for their '{identity_name}' AND '{identity_verify}'.",
            "DO NOT call ANY tools starting with 'get_' until you have successfully verified the user using the verify tool.",
            "If verification fails, allow the user to keep retrying. Do not refuse to authenticate them or redirect them to human support prematurely.",
            "Once a user is verified, they are authenticated for the session and you cannot authenticate them as someone else."
        ]
        
        # Add context for linked tables
        for table, schema_info in schema.get("tables", {}).items():
            if table == identity_table:
                continue
            
            # Check if this table has a foreign key to the identity table
            linked = False
            for fk in schema_info.get("foreign_keys", []):
                if fk["references_table"] == identity_table:
                    linked = True
                    break
            
            if linked:
                context_lines.append(f"Table '{table}' is linked to the verified user. Use the get_{table} tool to query it after verification.")
            else:
                context_lines.append(f"Table '{table}' is a standalone lookup table. Use the lookup_{table} tool.")
                
        context_prompt = "\n".join(context_lines)
        
        final_prompt = f"{base_prompt}\n{domain_prompt}\n{context_prompt}"
        return final_prompt
