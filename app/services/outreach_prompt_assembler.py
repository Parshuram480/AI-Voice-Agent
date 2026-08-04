"""Assembler for combining dynamic context into an outreach system prompt."""

import logging
from typing import Dict, Any, List
from app.utils.prompt_loader import get_prompts

logger = logging.getLogger(__name__)

class OutreachPromptAssembler:
    """Combines base rules, outreach prompts, and DB catalog context."""

    @staticmethod
    def assemble(config: Dict[str, Any], schema: Dict[str, Any], tools: List[Dict[str, Any]]) -> str:
        prompts_yaml = get_prompts()
        multimodal_prompts = prompts_yaml.get("multimodal", {})
        
        base_prompt = multimodal_prompts.get("base_prompt", "You are a helpful assistant.")
        
        domain_prompts = multimodal_prompts.get("domains", {})
        campaign_type = config.get("campaign_type", "outreach")
        base_campaign_prompt = domain_prompts.get(campaign_type, domain_prompts.get("outreach", ""))
        
        company_name = config.get("company_name", "our company")
        closing_goal = config.get("closing_goal", "make a sale")
        
        # If the prompt happens to be the old template with format strings, try formatting it
        try:
            outreach_prompt = base_campaign_prompt.format(company_name=company_name, closing_goal=closing_goal)
        except Exception:
            outreach_prompt = base_campaign_prompt
            
        # Ensure company and goal are explicitly injected if not using the exact template
        if "{company_name}" not in base_campaign_prompt:
            outreach_prompt = f"You are calling on behalf of {company_name}. Your primary objective is to {closing_goal}.\n\n{outreach_prompt}"
        
        context_lines = [
            "\n--- PRODUCT CATALOG CONTEXT ---",
            "You have tools to search and recommend products from the database.",
            "Do NOT hallucinate products. Only pitch what is returned by your tool calls."
        ]
        
        product_table = config.get("product_table")
        if product_table and product_table in schema.get("tables", {}):
            table_schema = schema["tables"][product_table]
            selected_cols = config.get("selected_columns", [])
            
            context_lines.append(f"\nThe product table is '{product_table}'. Available information includes:")
            for col in selected_cols:
                if col in table_schema["columns"]:
                    col_type = table_schema["columns"][col]["type"]
                    context_lines.append(f"- {col} ({col_type})")
                    
        context_prompt = "\n".join(context_lines)
        
        final_prompt = f"{base_prompt}\n{outreach_prompt}\n{context_prompt}"
        return final_prompt
