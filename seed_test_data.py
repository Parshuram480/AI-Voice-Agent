import asyncio
import json
from app.system_database import SystemDatabase
from app.memory.memory_manager import MemoryManager

async def seed_data():
    sys_db = SystemDatabase()
    mm = MemoryManager(sys_db)

    client_id = 1
    domain_id = 1

    # 1. Add/Update Caller Profile for "Disha Patel" (Semantic Memory)
    caller_identifiers = ["101", "1", "Disha Patel", "disha", "+15551234567", "Disha", "disha patel"]
    
    disha_profile_facts = {
        "customer_name": "Disha Patel",
        "patient_id": "101",
        "id": "101",
        "account_id": "101",
        "phone_number": "+15551234567",
        "date_of_birth": "1995-04-12",
        "preferred_time": "Morning appointments after 10:00 AM",
        "medical_notes": "No penicillin allergies, prefers Dr. Emily Roberts",
        "communication_preference": "SMS confirmation reminders"
    }

    print("=" * 60)
    print(" SEEDING CALLER MEMORY & LEARNED RULES FOR DISHA PATEL (ID: 101)")
    print("=" * 60)

    for identifier in caller_identifiers:
        saved_profile = await mm.upsert_caller_memory(
            client_id=client_id,
            domain_id=domain_id,
            caller_identifier=identifier,
            new_facts=disha_profile_facts
        )
        print(f"\n[SUCCESS] Caller Profile saved for '{identifier}':")
        print(json.dumps(saved_profile.get("profile_data", {}), indent=2))


    # 2. Add Domain Learned Rule (Procedural Memory)
    print("\nAdding active learned rules to domain_learned_rules...")
    pool = await sys_db._get_conn()
    async with pool.acquire() as conn:
        await conn.execute("""
        INSERT INTO domain_learned_rules (client_id, domain_id, rule_category, trigger_condition, instruction, confidence_score, status)
        VALUES (
            $1, $2, 'appointment_scheduling',
            'When booking an appointment or checking schedule',
            'Always remind the patient to bring their photo ID and arrive 10 minutes early.',
            1.0, 'active'
        )
        ON CONFLICT DO NOTHING;
        """, client_id, domain_id)
    
    print("[SUCCESS] Active Domain Learned Rule inserted!")
    print("=" * 60)
    await sys_db.close()

if __name__ == "__main__":
    asyncio.run(seed_data())
