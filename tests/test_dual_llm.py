import asyncio
import os
import sys

# Add project root to path if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.agent_service import AgentService
from app.session.manager import SessionManager
from app.services.verification_service import VerificationService
from app.services.order_service import OrderService
from app.groq_client import GroqClient

class MockCustomerRepo:
    async def get_by_name_dob(self, name, dob):
        if name.lower() == "john doe" and dob == "1990-01-01":
            return {"id": 1, "full_name": "John Doe", "phone": "123"}
        return None

class MockOrderRepo:
    async def get_all_for_customer(self, customer_id):
        if customer_id == 1:
            return [{"id": 100, "status": "Shipped", "total": "$20"}]
        return []

async def run_tests():
    from dotenv import load_dotenv
    load_dotenv()
    from app.session.store import InMemorySessionStore
    session_manager = SessionManager(InMemorySessionStore())
    groq1 = GroqClient(
        api_key=os.getenv("GROQ_LLM1_API_KEY") or os.getenv("GROQ_API_KEY"),
        default_model=os.getenv("LLM1_MODEL")
    )
    groq2 = GroqClient(
        api_key=os.getenv("GROQ_LLM2_API_KEY") or os.getenv("GROQ_API_KEY"),
        default_model=os.getenv("LLM2_MODEL")
    )
    verification = VerificationService(MockCustomerRepo())
    orders = OrderService(MockOrderRepo())
    
    agent = AgentService(
        session_manager=session_manager,
        groq_client_1=groq1,
        groq_client_2=groq2,
        verification_service=verification,
        order_service=orders
    )
    
    print("=== TEST 1: NO TOOL CALL (Greeting) ===")
    res1 = await agent.handle_user_text("test_session_1", "Hello there!")
    print(f"Reply: {res1.reply_text}")
    print("Metrics snapshot:")
    for k, v in res1.turn_metrics.items():
        if "time" in k or "ttft" in k or "tool" in k:
            print(f"  {k}: {v}")
            
    print("\n=== TEST 2: VERIFICATION (Partial info) ===")
    # First turn: Just say name
    res2a = await agent.handle_user_text("test_session_2", "Hi, my name is John Doe.")
    print(f"Reply: {res2a.reply_text}")
    
    print("\n=== TEST 3: VERIFICATION (Tool Call) ===")
    res2b = await agent.handle_user_text("test_session_2", "My date of birth is 1990-01-01.")
    print(f"Reply: {res2b.reply_text}")

    res2c = await agent.handle_user_text("test_session_2", "Yes, that is correct.")
    print(f"Reply: {res2c.reply_text}")
    print("Metrics snapshot:")
    for k, v in res2c.turn_metrics.items():
        if "time" in k or "ttft" in k or "tool" in k:
            print(f"  {k}: {v}")

    print("\n=== TEST 4: TOOL CALL (Order Status after Verification) ===")
    res3 = await agent.handle_user_text("test_session_2", "What is my order status?")
    print(f"Reply: {res3.reply_text}")
    print("Metrics snapshot:")
    for k, v in res3.turn_metrics.items():
        if "time" in k or "ttft" in k or "tool" in k:
            print(f"  {k}: {v}")
            
    print("\n=== VERIFYING LOGGER EXPORTS ===")
    from app.logging.logger import _calculate_total_ttft
    print(f"Test 1 Calculated E2E TTFT: {_calculate_total_ttft(res1.turn_metrics)}s")
    print(f"Test 3 Calculated E2E TTFT: {_calculate_total_ttft(res2c.turn_metrics)}s")
    print(f"Test 4 Calculated E2E TTFT: {_calculate_total_ttft(res3.turn_metrics)}s")

if __name__ == "__main__":
    asyncio.run(run_tests())
