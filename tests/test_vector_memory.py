import pytest
from unittest.mock import AsyncMock, MagicMock
from app.memory.memory_manager import MemoryManager
from app.memory.embedding_service import EmbeddingService
from app.services.dynamic_prompt_assembler import DynamicPromptAssembler

@pytest.mark.asyncio
async def test_memory_manager_retrieve_relevant_memories():
    mock_db = MagicMock()
    mock_db.get_client_gemini_key = AsyncMock(return_value=None)
    mock_db.search_caller_memory_vectors = AsyncMock(return_value=[
        {
            "id": 1,
            "caller_identifier": "Disha Patel",
            "memory_key": "allergies",
            "content": "Allergies: severely allergic to Latex and Sulfa drugs",
            "similarity": 0.88
        }
    ])

    embedding_service = EmbeddingService()
    mm = MemoryManager(system_db=mock_db, embedding_service=embedding_service)

    results = await mm.retrieve_relevant_memories(
        client_id=1,
        domain_id=1,
        caller_identifier="Disha Patel",
        query_text="What are my allergies?",
        top_k=3,
        min_similarity=0.5
    )

    assert len(results) == 1
    assert results[0]["memory_key"] == "allergies"
    assert "severely allergic to Latex" in results[0]["content"]
    assert results[0]["similarity"] == 0.88

def test_prompt_assembler_with_vector_memories():
    config = {
        "domain": "healthcare",
        "identity": {
            "table": "patients",
            "name_column": "full_name",
            "verification_column": "id"
        }
    }
    schema = {"tables": {"patients": {"columns": []}, "appointments": {"foreign_keys": [{"references_table": "patients"}]}}}
    tools = []

    vector_memories = [
        {"content": "Allergies: severely allergic to Latex and Sulfa drugs", "similarity": 0.89},
        {"content": "Preferred Doctor: Dr. Emily Roberts", "similarity": 0.74}
    ]

    prompt = DynamicPromptAssembler.assemble(
        config=config,
        schema=schema,
        tools=tools,
        caller_memory=vector_memories
    )

    assert "<caller_profile>" in prompt
    assert "- Allergies: severely allergic to Latex and Sulfa drugs" in prompt
    assert "- Preferred Doctor: Dr. Emily Roberts" in prompt
