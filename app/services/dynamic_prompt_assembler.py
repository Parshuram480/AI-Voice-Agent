"""Assembler for combining dynamic context into a system prompt."""

import logging
from typing import Dict, Any, List, Optional
from app.utils.prompt_loader import get_prompts
from app.memory.memory_manager import MemoryManager

logger = logging.getLogger(__name__)

class DynamicPromptAssembler:
    """Combines base rules, domain prompts, DB relationships, and Continuous Learning memory."""

    @staticmethod
    def assemble(
        config: Dict[str, Any],
        schema: Dict[str, Any],
        tools: List[Dict[str, Any]],
        caller_memory: Optional[Dict[str, Any]] = None,
        learned_rules: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        prompts_yaml = get_prompts()
        multimodal_prompts = prompts_yaml.get("multimodal", {})
        
        base_prompt = multimodal_prompts.get("base_prompt", "You are a helpful assistant.")
        
        domain = config.get("domain", "default").lower()
        domain_prompt = config.get("system_prompt")
        
        if not domain_prompt:
            domain_prompts = multimodal_prompts.get("domains", {})
            domain_prompt = domain_prompts.get(domain, "")
            
        identity_table = config.get("identity", {}).get("table")
        identity_name = config.get("identity", {}).get("name_column")
        identity_verify = config.get("identity", {}).get("verification_column")
        
        context_lines = [
            "\n--- DATABASE SCHEMA CONTEXT ---",
            f"The '{identity_table}' table is the central identity table.",
            f"To verify a user, you must ask for their '{identity_name}' AND '{identity_verify}' (e.g. Full Name and Date of Birth). NEVER ask for a user ID or account number. Then call the 'verify_user_identity' tool.",
            "DO NOT call ANY tools starting with 'get_' until you have successfully verified the user using the 'verify_user_identity' tool.",
            "Once a user is verified, they are authenticated for the session and you cannot authenticate them as someone else.",
            "When the user shares personal preferences, notes, or constraints (e.g. appointment times, video calls, allergies), warmly acknowledge and accept them. If they have not provided their name yet, ask for their name so the note is saved to their profile."
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
        
        # Continuous Learning: Inject Caller Semantic Memory (Preferences & Context - Memory RAG)
        memory_prompt = ""
        if caller_memory:
            if isinstance(caller_memory, list):
                # Vector Memory RAG chunks
                formatted_mem = MemoryManager.format_memory_for_prompt(retrieved_memories=caller_memory)
            else:
                # Full profile dictionary
                profile_data = caller_memory.get("profile_data", caller_memory)
                formatted_mem = MemoryManager.format_memory_for_prompt(profile_data=profile_data)
            
            if formatted_mem:
                memory_prompt = f"\n{formatted_mem}"

        # Continuous Learning: Inject Learned Procedural Rules
        rules_prompt = ""
        if learned_rules and isinstance(learned_rules, list):
            valid_rules = [
                f"- {r.get('instruction') or r.get('trigger_condition')}"
                for r in learned_rules
                if isinstance(r, dict) and (r.get('instruction') or r.get('trigger_condition'))
            ]
            if valid_rules:
                rules_prompt = "\n\n<domain_learned_rules>\n# ACTIVE LEARNED GUIDELINES (FROM PAST INTERACTIONS)\n" + "\n".join(valid_rules) + "\n</domain_learned_rules>"

        final_prompt = f"{base_prompt}\n{domain_prompt}\n{context_prompt}{memory_prompt}{rules_prompt}"
        return final_prompt
