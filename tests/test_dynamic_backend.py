import pytest
import json
import asyncio
from app.services.dynamic_tool_factory import DynamicToolFactory
from app.services.dynamic_prompt_assembler import DynamicPromptAssembler
from app.services.pg_schema_service import PgSchemaService
from app.services.dynamic_tool_executor import DynamicToolExecutor

@pytest.fixture
def sample_config():
    return {
        "domain": "healthcare",
        "database": {
            "db_type": "postgresql",
            "server_name": "localhost",
            "port": 5432,
            "db_name": "healthcare_demo",
            "username": "postgres",
            "password": "ips12345"
        },
        "identity": {
            "table": "patients",
            "name_column": "full_name",
            "verification_column": "date_of_birth",
            "display_columns": ["full_name", "date_of_birth", "phone", "insurance_id"]
        },
        "selected_tables": {
            "patients": ["id", "full_name", "date_of_birth", "phone", "insurance_id"],
            "appointments": ["id", "patient_id", "doctor_id", "appointment_date", "appointment_time", "status", "reason"],
            "prescriptions": ["id", "patient_id", "medication_name", "dosage", "refills_remaining"]
        }
    }

@pytest.fixture
def mock_schema_metadata():
    return {
        "tables": {
            "patients": {
                "columns": {
                    "id": {"type": "integer", "nullable": False},
                    "full_name": {"type": "character varying", "nullable": False},
                    "date_of_birth": {"type": "date", "nullable": False}
                },
                "primary_key": "id",
                "foreign_keys": []
            },
            "appointments": {
                "columns": {
                    "id": {"type": "integer", "nullable": False},
                    "patient_id": {"type": "integer", "nullable": False}
                },
                "primary_key": "id",
                "foreign_keys": [
                    {"column": "patient_id", "references_table": "patients", "references_column": "id"}
                ]
            },
            "prescriptions": {
                "columns": {
                    "id": {"type": "integer", "nullable": False},
                    "patient_id": {"type": "integer", "nullable": False}
                },
                "primary_key": "id",
                "foreign_keys": [
                    {"column": "patient_id", "references_table": "patients", "references_column": "id"}
                ]
            }
        },
        "relationships": [
            {"from_table": "appointments", "from_column": "patient_id", "to_table": "patients", "to_column": "id"},
            {"from_table": "prescriptions", "from_column": "patient_id", "to_table": "patients", "to_column": "id"}
        ]
    }

def test_dynamic_tool_factory(sample_config, mock_schema_metadata):
    factory = DynamicToolFactory(sample_config, mock_schema_metadata)
    tools, exec_map = factory.generate_tools()
    
    assert len(tools) == 3
    tool_names = [t["name"] for t in tools]
    assert "verify_patients" in tool_names
    assert "get_appointments" in tool_names
    assert "get_prescriptions" in tool_names
    
    # Test verify tool definition
    verify_tool = next(t for t in tools if t["name"] == "verify_patients")
    assert "full_name" in verify_tool["parameters"]["properties"]
    assert "date_of_birth" in verify_tool["parameters"]["properties"]
    
    # Test execution map
    assert "verify_patients" in exec_map
    assert "SELECT id, full_name, date_of_birth, phone, insurance_id" in exec_map["verify_patients"]
    assert "get_appointments" in exec_map
    assert "WHERE patient_id = $1" in exec_map["get_appointments"]

def test_dynamic_prompt_assembler(sample_config, mock_schema_metadata):
    factory = DynamicToolFactory(sample_config, mock_schema_metadata)
    tools, _ = factory.generate_tools()
    prompt = DynamicPromptAssembler.assemble(sample_config, mock_schema_metadata, tools)
    
    assert "You are an expert, empathetic, and professional healthcare patient assistant" in prompt
    assert "The 'patients' table is the central identity table." in prompt
    assert "Table 'appointments' is linked to the verified user." in prompt

@pytest.mark.asyncio
async def test_pg_schema_service_integration(sample_config):
    # This integration test assumes the database is running with the specified config.
    service = PgSchemaService(sample_config["database"])
    try:
        metadata = await service.get_schema_metadata()
        assert "patients" in metadata["tables"]
        assert "appointments" in metadata["tables"]
        assert metadata["tables"]["patients"]["primary_key"] == "id"
    except Exception as e:
        pytest.fail(f"Integration test failed: {e}")

@pytest.mark.asyncio
async def test_dynamic_executor_integration(sample_config, mock_schema_metadata):
    factory = DynamicToolFactory(sample_config, mock_schema_metadata)
    tools, exec_map = factory.generate_tools()
    
    executor = DynamicToolExecutor(sample_config["database"], exec_map, sample_config["identity"]["table"])
    
    # Test verify failure
    state = {}
    response = await executor.execute("tool_1", "verify_patients", {"full_name": "Non Existent", "date_of_birth": "1999-01-01"}, state)
    assert response.name == "verify_patients"
    assert response.response["verified"] == False
    
    # Test verify success
    response = await executor.execute("tool_2", "verify_patients", {"full_name": "Alice Smith", "date_of_birth": "1985-04-12"}, state)
    assert response.response["verified"] == True
    assert "identity_id" in state
    
    # Test get_appointments after verification
    response = await executor.execute("tool_3", "get_appointments", {}, state)
    assert "results" in response.response
    assert isinstance(response.response["results"], list)
