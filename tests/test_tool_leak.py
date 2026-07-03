import asyncio
import os
import sys

# Ensure the app module can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.agent_service import AgentService
from app.session.manager import SessionManager
from app.session.store import InMemorySessionStore
from app.services.order_service import OrderService
from app.services.verification_service import VerificationService

class MockGroqClient:
    def __init__(self, leaked_chunks):
        self.leaked_chunks = leaked_chunks

    async def chat_completion_stream_with_tools(self, **kwargs):
        # Yield fake stream tokens
        for chunk in self.leaked_chunks:
            yield "content", chunk
            await asyncio.sleep(0.01)

async def run_leak_test(test_name, chunks, expect_tokens_emitted):
    print(f"\n=== Running Test: {test_name} ===")
    
    mock_groq = MockGroqClient(chunks)
    
    # Initialize the AgentService with mocked Groq
    session_manager = SessionManager(InMemorySessionStore())
    class MockOrderSvc: pass
    class MockVerifySvc: pass
    
    agent = AgentService(
        session_manager=session_manager,
        groq_client=mock_groq,
        verification_service=MockVerifySvc(),
        order_service=MockOrderSvc()
    )
    
    emitted_tokens = []
    def _on_token(token):
        emitted_tokens.append(token)
        print(f"  -> TTS Engine Received Token: {repr(token)}")
        
    state = {
        "messages": [{"role": "user", "content": "What is my order?"}],
        "verified": False
    }
    
    config = {"configurable": {"on_llm_token": _on_token, "thread_id": "test-session"}}
    
    # Call the node directly
    result = await agent._agent_node(state, config)
    
    rescued_tools = result["messages"][0].get("tool_calls", [])
    print(f"Rescued Tool Calls: {rescued_tools}")
    
    if emitted_tokens:
        print(f"Stream output: {''.join(emitted_tokens)}")
    else:
        print("Stream output: <MUTED>")
        
    if expect_tokens_emitted and not emitted_tokens:
        print("[FAIL] Expected tokens to be emitted, but got none.")
        return False
    elif not expect_tokens_emitted and emitted_tokens:
        print("[FAIL] Stream was supposed to be muted, but TTS engine received tokens!")
        return False
        
    print("[PASS]")
    return True

async def main():
    # Test 1: Llama 3 leaking function syntax (should be MUTED)
    leak_chunks = ["<", "function=", "verify_user>{\"name\": \"Rohit\"}"]
    await run_leak_test("Tool Leak (Llama 3 syntax)", leak_chunks, expect_tokens_emitted=False)
    
    # Test 2: Standard JSON hallucination leak (should be MUTED)
    leak_chunks = ["{\"", "name\":", "\"verify_user\", \"arguments\": {}"]
    await run_leak_test("Tool Leak (JSON syntax)", leak_chunks, expect_tokens_emitted=False)
    
    # Test 3: Standard normal response (should be EMITTED)
    normal_chunks = ["Hello", "!", " Let", " me", " check", " that."]
    await run_leak_test("Normal Chat", normal_chunks, expect_tokens_emitted=True)

if __name__ == "__main__":
    asyncio.run(main())
