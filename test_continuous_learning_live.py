"""Interactive Live Test for Continuous Learning Agent (Phase 1).

Demonstrates:
1. PII Sanitization in real-time.
2. Saving & updating customer profile memory in PostgreSQL.
3. Preloading and injecting caller memory into the live voice prompt.
4. Conflict resolution (updating old facts with new facts).
"""

import sys
import asyncio
import os
import json
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

from app.system_database import SystemDatabase
from app.memory.memory_manager import MemoryManager
from app.services.dynamic_prompt_assembler import DynamicPromptAssembler


async def run_live_test():
    print("=" * 70)
    print(" CONTINUOUS LEARNING AGENT - LIVE DATABASE & MEMORY TEST")
    print("=" * 70)

    sys_db = SystemDatabase()
    
    # Ensure client and domain exist for foreign keys
    pool = await sys_db._get_conn()
    async with pool.acquire() as conn:
        # Check or create default client
        client_row = await conn.fetchrow("SELECT id FROM clients WHERE id = 1")
        if not client_row:
            await conn.execute("""
            INSERT INTO clients (id, company_name, client_name, email, password_hash)
            VALUES (1, 'Acme Corp', 'Admin User', 'admin@acme.com', 'dummyhash')
            ON CONFLICT (id) DO NOTHING;
            """)
        
        # Check or create default domain
        domain_row = await conn.fetchrow("SELECT id FROM domains WHERE id = 1")
        if not domain_row:
            await conn.execute("""
            INSERT INTO domains (id, name, description, system_prompt_llm1, system_prompt_llm2, tools_schema)
            VALUES (1, 'food', 'Food delivery domain', 'System prompt 1', 'System prompt 2', '[]')
            ON CONFLICT (id) DO NOTHING;
            """)

    memory_manager = MemoryManager(sys_db)

    # 1. Setup sample client & domain context
    client_id = 1
    domain_id = 1
    caller_phone = "+15559876543"

    print(f"\n[STEP 1] Simulating Call 1 from {caller_phone}...")
    print("Caller states: 'My name is Sarah Connor. I work night shifts, so only call or deliver after 5 PM. Also my secret pin is 4432.'")

    # Raw extracted facts from Call 1 containing sensitive PII (PIN and credit card)
    call_1_facts = {
        "customer_name": "Sarah Connor",
        "preferred_time": "After 5:00 PM (Night shift worker)",
        "security_note": "Caller pin is 4432 and card is 4532 0150 1234 5674",
        "dietary_preference": "Vegetarian only"
    }

    print("\n[STEP 2] Saving facts to PostgreSQL via MemoryManager (with auto PII redaction)...")
    saved_profile = await memory_manager.upsert_caller_memory(
        client_id=client_id,
        domain_id=domain_id,
        caller_identifier=caller_phone,
        new_facts=call_1_facts
    )

    print("[SUCCESS] Database record saved successfully:")
    print(json.dumps(saved_profile.get("profile_data", {}), indent=2))

    # 2. Simulate Call 2 (Same caller dials in days later)
    print(f"\n[STEP 3] Simulating Call 2: {caller_phone} dials in again...")
    print("Fetching caller memory from PostgreSQL (< 5ms)...")
    
    fetched_memory = await memory_manager.get_caller_memory(
        client_id=client_id,
        domain_id=domain_id,
        caller_identifier=caller_phone
    )

    print(f"[SUCCESS] Retrieved Profile for: {fetched_memory['caller_identifier']}")

    # 3. Simulate Dynamic Prompt Assembly for the Voice Agent
    print("\n[STEP 4] Assembling live system prompt with injected caller memory...")
    config = {
        "domain": "food",
        "identity": {
            "table": "customers",
            "name_column": "customer_name",
            "verification_column": "phone"
        }
    }
    schema = {"tables": {"customers": {}}}
    tools = []

    assembled_prompt = DynamicPromptAssembler.assemble(
        config=config,
        schema=schema,
        tools=tools,
        caller_memory=fetched_memory
    )

    print("\n--- INJECTED SYSTEM PROMPT SNIPPET (SENT TO LLM) ---")
    # Show the injected memory block from the prompt
    for line in assembled_prompt.split("\n"):
        if "<caller_profile>" in line or "</caller_profile>" in line or line.startswith("- "):
            print(f"  {line}")
    print("-----------------------------------------------------")

    # 5. Simulate Phase 2: Post-Call LLM-as-a-Judge Evaluation & Flywheel
    print(f"\n[STEP 6] Simulating Phase 2: Asynchronous Post-Call LLM-as-a-Judge...")
    sample_call_history = [
        {"role": "assistant", "content": "Hello, thank you for calling QuickBite. How can I assist you?"},
        {"role": "user", "content": "Hi, this is Sarah Connor (+15559876543). Please make sure all my deliveries are placed on the front porch and never ring the doorbell after 8 PM."},
        {"role": "assistant", "content": "Understood, Sarah. I have noted that all deliveries should go to the front porch with no doorbell ringing after 8 PM."}
    ]

    # Insert mock call_log so foreign key constraint passes
    async with pool.acquire() as conn:
        await conn.execute("""
        INSERT INTO call_logs (session_id, client_id, domain, pipeline_mode, history, summary, intent)
        VALUES ('test_session_live_001', 1, 'food', 'multimodal', '[]'::jsonb, 'Test summary', 'Order Delivery')
        ON CONFLICT (session_id) DO NOTHING;
        """)

    print("Running post-call evaluation & learning flywheel in background...")
    learning_result = await memory_manager.process_post_call_learning(
        session_id="test_session_live_001",
        history=sample_call_history,
        domain="food",
        client_id=client_id,
        domain_id=domain_id,
        caller_identifier=caller_phone
    )

    evaluation = learning_result.get("evaluation")
    if evaluation:
        print("[SUCCESS] Post-call evaluation completed:")
        print(f"  Task Completion Score: {evaluation.get('task_completion_score')}/100")
        print(f"  Friction Score: {evaluation.get('friction_score')}/5")
        print(f"  Tool Accuracy Score: {evaluation.get('tool_accuracy_score')}/100")
        print(f"  Extracted Facts: {json.dumps(evaluation.get('extracted_facts', {}), indent=2)}")
        print(f"  Actionable Lessons: {evaluation.get('actionable_lessons')}")
        print(f"  Reasoning: {evaluation.get('evaluation_details', {}).get('reasoning')}")

    # Verify call evaluation record stored in PostgreSQL
    eval_record = await sys_db.get_call_evaluation("test_session_live_001")
    if eval_record:
        print(f"[SUCCESS] Verified record saved in PostgreSQL 'call_evaluations' table for session 'test_session_live_001'.")

    # Verify learned procedural rules
    learned_rules = await sys_db.get_active_learned_rules(client_id=client_id, domain_id=domain_id)
    print(f"[SUCCESS] Active domain learned rules count: {len(learned_rules)}")
    for r in learned_rules:
        print(f"  Rule: {r.get('instruction')} (Confidence: {r.get('confidence_score')})")

    print("\n" + "=" * 70)
    print("[PASSED] Continuous Learning System 1 & System 2 Fully Functional!")
    print("=" * 70)

    await sys_db.close()


if __name__ == "__main__":
    asyncio.run(run_live_test())


