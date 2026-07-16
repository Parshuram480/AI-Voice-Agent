import asyncio
import os
import json
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
from app.database import DatabaseClient
from app.services.analytics_service import AnalyticsService

async def test_analytics():
    print("Testing DB Connection...")
    db = DatabaseClient()
    await db.connect()
    
    if not db._use_fallback:
        print("Initializing schema from init.sql...")
        with open('sql/init.sql', 'r') as f:
            schema_sql = f.read()
        async with db._pool.acquire() as conn:
            await conn.execute('DROP TABLE IF EXISTS call_logs;')
            await conn.execute(schema_sql)

    analytics = AnalyticsService(db)
    
    # Test data for cascade
    history_cascade = [
        {"role": "user", "content": "hello I want to check my order"},
        {"role": "assistant", "content": "I can help with that. What is your full name and date of birth?"}
    ]
    
    print("Testing AnalyticsService process_call_analytics (Cascade)...")
    await analytics.process_call_analytics(
        session_id="test-session-cascade-1",
        pipeline_mode="cascade",
        history=history_cascade,
        total_input_tokens=150,
        total_output_tokens=50,
        average_latency=1200.5,
        user_id=1
    )
    
    # Sleep briefly to avoid connection/rate limits with Groq
    await asyncio.sleep(2)

    # Test data for multimodal
    history_mm = [
        {"role": "user", "content": "what is my order status"},
        {"role": "assistant", "content": "Your order is shipped."}
    ]
    print("Testing AnalyticsService process_call_analytics (Multimodal)...")
    await analytics.process_call_analytics(
        session_id="test-session-mm-1",
        pipeline_mode="multimodal",
        history=history_mm,
        total_input_tokens=8,
        total_output_tokens=6,
        average_latency=850.2,
        user_id=2
    )

    # Check logs in DB if connected, else fallback logs
    if db._use_fallback:
        from app.database import _FALLBACK_CALL_LOGS
        print("\nUsing Fallback DB. Logs saved:")
        print(json.dumps(_FALLBACK_CALL_LOGS, indent=2))
        
        # Verify columns
        if len(_FALLBACK_CALL_LOGS) >= 2:
            log1 = _FALLBACK_CALL_LOGS[0]
            print(f"Log 1 Mode: {log1['pipeline_mode']}, Summary: {log1['summary']}, Intent: {log1['intent']}, Total Tokens: {log1['total_tokens']}, Latency: {log1['average_latency']}")
            log2 = _FALLBACK_CALL_LOGS[1]
            print(f"Log 2 Mode: {log2['pipeline_mode']}, Summary: {log2['summary']}, Intent: {log2['intent']}, Total Tokens: {log2['total_tokens']}, Latency: {log2['average_latency']}")
    else:
        print("\nUsing Postgres DB. Querying call_logs...")
        async with db._pool.acquire() as conn:
            records = await conn.fetch("SELECT * FROM call_logs WHERE session_id IN ('test-session-cascade-1', 'test-session-mm-1')")
            for r in records:
                print(f"Session: {r['session_id']}, Mode: {r['pipeline_mode']}, Summary: {r['summary']}, Intent: {r['intent']}, Total Tokens: {r['total_tokens']}, Latency: {r['average_latency']}")
    
    await db.close()

if __name__ == "__main__":
    asyncio.run(test_analytics())
