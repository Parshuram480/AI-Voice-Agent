import asyncio
import json
import logging
from pprint import pprint

from app.services.schema_service import SchemaService
from app.services.dynamic_tool_factory import DynamicToolFactory
from app.services.dynamic_prompt_assembler import DynamicPromptAssembler

logging.basicConfig(level=logging.INFO)

async def main():
    config_path = "client_configs/healthcare_manual_test.json"
    
    with open(config_path, "r") as f:
        config = json.load(f)
        
    print("=== Testing Schema Introspection ===")
    schema_service = SchemaService(config["database"])
    schema_metadata = await schema_service.get_schema_metadata()
    print("Discovered Tables:", list(schema_metadata["tables"].keys()))
    print("Discovered Relationships:")
    for rel in schema_metadata["relationships"]:
        print(f"  {rel['from_table']}.{rel['from_column']} -> {rel['to_table']}.{rel['to_column']}")
        
    print("\n=== Testing Dynamic Tool Factory ===")
    tool_factory = DynamicToolFactory(config, schema_metadata)
    tools, exec_map = tool_factory.generate_tools()
    
    print("\nGenerated Tools for Gemini:")
    for t in tools:
        print(f"- {t['name']}: {t['description']}")
        
    print("\nGenerated SQL Execution Map:")
    for name, tool_data in exec_map.items():
        print(f"- {name}:\n    {tool_data['sql']}")
        
    print("\n=== Testing Dynamic Prompt Assembler ===")
    prompt = DynamicPromptAssembler.assemble(config, schema_metadata, tools)
    print("\nGenerated System Prompt:")
    print("-" * 40)
    print(prompt)
    print("-" * 40)

if __name__ == "__main__":
    asyncio.run(main())
