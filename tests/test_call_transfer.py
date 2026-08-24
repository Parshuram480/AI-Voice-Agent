import pytest
import os
import asyncio
from typing import Dict, Any, Optional

from app.system_database import SystemDatabase
from app.twilio_handler import TwilioHandler
from app.gemini_live_client import GeminiLiveClient
from google.genai import types

# Mock services for testing client
class MockVerificationService:
    pass

class MockOrderService:
    pass


async def is_db_reachable() -> bool:
    """Helper to check if system database is running and reachable."""
    try:
        db = SystemDatabase()
        pool = await db._get_conn()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception:
        return False


async def restore_database_executives(conn):
    """Helper to restore the default seeded executives."""
    await conn.execute("DELETE FROM executives")
    client_row = await conn.fetchrow("SELECT id FROM clients ORDER BY id ASC LIMIT 1")
    client_id = client_row["id"] if client_row else None
    
    # Resolve dynamic MY_CELL_PHONE if configured
    from dotenv import load_dotenv
    import os
    load_dotenv()
    my_cell_phone = os.getenv("MY_CELL_PHONE")
    
    avail_client_phone = my_cell_phone if my_cell_phone else "+15550001111"
    avail_system_phone = my_cell_phone if my_cell_phone else "+15559990001"
    
    if client_id:
        await conn.execute("""
        INSERT INTO executives (name, phone, is_available, client_id) VALUES
        ('Support Representative (Available)', $1, TRUE, $2),
        ('Support Representative (Busy)', '+15550002222', FALSE, $2)
        """, avail_client_phone, client_id)
    await conn.execute("""
    INSERT INTO executives (name, phone, is_available, client_id) VALUES
    ('System Support Representative (Available)', $1, TRUE, NULL),
    ('System Support Representative (Busy)', '+15559990002', FALSE, NULL)
    """, avail_system_phone)


def test_generate_transfer_twiml():
    """Verify TwilioHandler.generate_transfer_twiml returns correct TwiML syntax."""
    handler = TwilioHandler()
    twiml = handler.generate_transfer_twiml("+15551234567")
    
    assert "<Dial>" in twiml
    assert "+15551234567" in twiml
    assert "<Response>" in twiml

@pytest.mark.asyncio
async def test_database_executive_queries():
    """Verify SystemDatabase executive schema and available check query."""
    if not await is_db_reachable():
        pytest.skip("System database (Postgres) is not reachable. Skipping integration test.")
        
    db = SystemDatabase()
    pool = await db._get_conn()
    
    async with pool.acquire() as conn:
        # Verify schema
        table_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'executives')"
        )
        assert table_exists is True
        
        # Clear database for test purity
        await conn.execute("DELETE FROM executives")
        
        # Insert test representatives
        await conn.execute(
            "INSERT INTO executives (name, phone, is_available, client_id) VALUES "
            "('Test representative (Available)', '+15550009999', TRUE, NULL), "
            "('Test representative (Busy)', '+15550008888', FALSE, NULL)"
        )
        
        try:
            # Query default executive
            exec_info = await db.get_available_executive()
            assert exec_info is not None
            assert exec_info["phone"] == "+15550009999"
            
            # Update available to False
            await conn.execute("UPDATE executives SET is_available = FALSE WHERE name = 'Test representative (Available)'")
            
            # Query again: should return None since both are now unavailable
            exec_info_none = await db.get_available_executive()
            assert exec_info_none is None
            
        finally:
            await restore_database_executives(conn)


@pytest.mark.asyncio
async def test_gemini_client_transfer_tool_execution_success():
    """Verify GeminiLiveClient tool execution flags state when executive is available."""
    if not await is_db_reachable():
        pytest.skip("System database (Postgres) is not reachable. Skipping integration test.")
        
    db = SystemDatabase()
    pool = await db._get_conn()
    
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM executives")
        await conn.execute(
            "INSERT INTO executives (name, phone, is_available, client_id) VALUES "
            "('Test representative (Available)', '+15550009999', TRUE, NULL)"
        )
        
        try:
            # Set up client and state
            client = GeminiLiveClient(
                verification_service=MockVerificationService(),
                order_service=MockOrderService(),
                api_key="mock_key_for_test",
                client_id=None
            )
            
            state = {"verified": False, "should_end": False}
            
            # Execute tool call
            response = await client.execute_tool_call(
                tool_call_id="call_test_123",
                name="transfer_to_executive",
                args={},
                state=state
            )
            
            # Assertions
            assert state.get("should_end") is True
            assert state.get("transfer_to_number") == "+15550009999"
            assert response.name == "transfer_to_executive"
            assert response.id == "call_test_123"
            assert response.response["success"] is True
            
        finally:
             await restore_database_executives(conn)


@pytest.mark.asyncio
async def test_gemini_client_transfer_tool_execution_failure():
    """Verify GeminiLiveClient tool execution returns failure when no executives are available."""
    if not await is_db_reachable():
        pytest.skip("System database (Postgres) is not reachable. Skipping integration test.")
        
    db = SystemDatabase()
    pool = await db._get_conn()
    
    async with pool.acquire() as conn:
        # Delete all available executives
        await conn.execute("DELETE FROM executives")
        
        try:
            # Set up client and state
            client = GeminiLiveClient(
                verification_service=MockVerificationService(),
                order_service=MockOrderService(),
                api_key="mock_key_for_test",
                client_id=None
            )
            
            state = {"verified": False, "should_end": False}
            
            # Execute tool call
            response = await client.execute_tool_call(
                tool_call_id="call_test_456",
                name="transfer_to_executive",
                args={},
                state=state
            )
            
            # Assertions
            assert state.get("should_end") is False or state.get("should_end") is None
            assert "transfer_to_number" not in state
            assert response.name == "transfer_to_executive"
            assert response.id == "call_test_456"
            assert response.response["success"] is False
            assert response.response["reason"] == "no_executive_available"
            
        finally:
            await restore_database_executives(conn)
