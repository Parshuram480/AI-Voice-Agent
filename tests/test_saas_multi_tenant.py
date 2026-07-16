import pytest
import os
import sqlite3
import asyncio
from app.system_database import SystemDatabase, hash_password, verify_password
from app.dynamic_db_client import DynamicDbClient

def test_password_hashing():
    pw = "SuperSecurePassword123"
    hashed = hash_password(pw)
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False

@pytest.mark.asyncio
async def test_domains_seeding():
    db = SystemDatabase()
    try:
        domains = await db.get_domains()
        assert len(domains) >= 2
        domain_names = [d["name"] for d in domains]
        assert "Healthcare" in domain_names
        assert "Order Tracking" in domain_names
    finally:
        await db.close()

@pytest.mark.asyncio
async def test_client_registration_and_login():
    db = SystemDatabase()
    client_id = None
    try:
        client_data = {
            "company_name": "Test Company",
            "client_name": "Test Contact",
            "email": "test@company.com",
            "password": "my_secure_password",
            "phone": "+123456789"
        }
        
        db_config = {
            "db_type": "sqlite",
            "db_name": "test_healthcare_client.db"
        }
        
        # Select Healthcare domain (usually ID 1 or we can find it)
        domains = await db.get_domains()
        hc_domain = next(d for d in domains if d["name"] == "Healthcare")
        
        # Register
        client_id = await db.register_client(client_data, db_config, hc_domain["id"])
        assert client_id > 0
        
        # Verify login
        client = await db.get_client_by_email("test@company.com")
        assert client is not None
        assert client["company_name"] == "Test Company"
        assert verify_password("my_secure_password", client["password_hash"]) is True
        
        # Get config and mapping
        cfg = await db.get_client_db_config(client_id)
        assert cfg is not None
        assert cfg["db_name"] == "test_healthcare_client.db"
        
        mapping = await db.get_client_domain_mapping(client_id)
        assert mapping is not None
        assert mapping["domain_name"] == "Healthcare"
        assert "patients" in mapping["verification_query"]
    finally:
        # Cleanup registered test client
        pool = await db._get_conn()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM clients WHERE email = $1", "test@company.com")
        await db.close()

@pytest.mark.asyncio
async def test_dynamic_db_client():
    # Setup temporary healthcare database
    temp_db_name = "test_healthcare_temp.db"
    if os.path.exists(temp_db_name):
        os.remove(temp_db_name)
        
    conn = sqlite3.connect(temp_db_name)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            date_of_birth TEXT
        )
    """)
    cursor.execute("INSERT INTO patients (full_name, date_of_birth) VALUES ('Alice Smith', '1990-05-15')")
    conn.commit()
    conn.close()
    
    # Test connection
    config = {
        "db_type": "sqlite",
        "db_name": temp_db_name
    }
    client = DynamicDbClient(config)
    
    success, msg = await client.test_connection()
    assert success is True
    
    # Test execute query
    rows = await client.execute_query(
        "SELECT id, full_name FROM patients WHERE LOWER(full_name) = ? AND date_of_birth = ?",
        ("alice smith", "1990-05-15")
    )
    assert len(rows) == 1
    assert rows[0]["full_name"] == "Alice Smith"
    
    # Cleanup
    if os.path.exists(temp_db_name):
        os.remove(temp_db_name)
