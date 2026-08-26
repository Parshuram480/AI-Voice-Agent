"""Tests for DynamicPromptAssembler with Continuous Learning Memory."""

import pytest
from app.services.dynamic_prompt_assembler import DynamicPromptAssembler


def test_dynamic_prompt_assembler_with_memory():
    config = {
        "domain": "healthcare",
        "identity": {
            "table": "patients",
            "name_column": "full_name",
            "verification_column": "date_of_birth"
        }
    }
    schema = {
        "tables": {
            "patients": {},
            "appointments": {
                "foreign_keys": [{"references_table": "patients"}]
            }
        }
    }
    tools = []
    
    caller_memory = {
        "profile_data": {
            "preferred_name": "Sarah",
            "callback_time": "After 4 PM",
            "doctor_preference": "Dr. Smith"
        }
    }

    learned_rules = [
        {"instruction": "Always confirm patient date of birth before reading lab results."},
        {"trigger_condition": "If patient asks for appointments, check past 30 days first."}
    ]

    prompt = DynamicPromptAssembler.assemble(
        config=config,
        schema=schema,
        tools=tools,
        caller_memory=caller_memory,
        learned_rules=learned_rules
    )

    # Verify standard prompt assembly
    assert "--- DATABASE SCHEMA CONTEXT ---" in prompt
    assert "Table 'appointments' is linked to the verified user" in prompt

    # Verify Continuous Learning Caller Memory injection
    assert "<caller_profile>" in prompt
    assert "- Preferred Name: Sarah" in prompt
    assert "- Callback Time: After 4 PM" in prompt
    assert "- Doctor Preference: Dr. Smith" in prompt
    assert "</caller_profile>" in prompt

    # Verify Continuous Learning Learned Rules injection
    assert "<domain_learned_rules>" in prompt
    assert "- Always confirm patient date of birth before reading lab results." in prompt
    assert "- If patient asks for appointments, check past 30 days first." in prompt
    assert "</domain_learned_rules>" in prompt


def test_dynamic_prompt_assembler_without_memory():
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

    prompt = DynamicPromptAssembler.assemble(config, schema, tools)
    assert "<caller_profile>" not in prompt
    assert "<domain_learned_rules>" not in prompt
    assert "The 'customers' table is the central identity table." in prompt
