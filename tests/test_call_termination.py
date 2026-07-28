import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.agent_service import AgentService
from app.session.manager import SessionManager
from app.session.store import InMemorySessionStore

class DummySession:
    def __init__(self):
        self.session_id = "test-session"
        self.verified = False
        self.user_name = None
        self.dob = None
        self.customer_id = None
        self.customer_name = None

class DummySessionManager:
    async def get_or_create(self, session_id, **kwargs):
        return DummySession()

async def test_global_tools():
    session_store = InMemorySessionStore()
    session_manager = SessionManager(session_store)
    
    # Initialize AgentService (mocking out other services since we are only testing the node function directly)
    agent = AgentService(
        session_manager=session_manager,
        groq_client_1=None,
        groq_client_2=None,
        verification_service=None,
        order_service=None
    )
    
    # Manually overwrite the session manager
    agent._sessions = DummySessionManager()
    
    class DummyConfig:
        def get(self, *args, **kwargs):
            return {"thread_id": "test-session"}

    # Test end_call tool execution
    state = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "end_call",
                            "arguments": "{}"
                        }
                    }
                ]
            }
        ],
        "should_end": False,
        "out_of_scope_count": 0,
        "turn_metrics": {}
    }
    
    updates = await agent._verify_tool_node(state, DummyConfig())
    print("Updates for end_call:", updates)
    assert updates.get("should_end") is True
    assert len(updates["messages"]) == 1
    assert updates["messages"][0]["name"] == "end_call"
    
    # Test out_of_scope tool (first warning)
    state = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "out_of_scope",
                            "arguments": '{"reason": "Capital of France"}'
                        }
                    }
                ]
            }
        ],
        "should_end": False,
        "out_of_scope_count": 0,
        "turn_metrics": {}
    }
    updates = await agent._verify_tool_node(state, DummyConfig())
    print("Updates for first out_of_scope:", updates)
    assert updates.get("out_of_scope_count") == 1
    assert updates.get("should_end") is not True
    
    # Test out_of_scope tool (second warning -> terminate)
    state = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_3",
                        "type": "function",
                        "function": {
                            "name": "out_of_scope",
                            "arguments": '{"reason": "Capital of France"}'
                        }
                    }
                ]
            }
        ],
        "should_end": False,
        "out_of_scope_count": 1,
        "turn_metrics": {}
    }
    updates = await agent._verify_tool_node(state, DummyConfig())
    print("Updates for second out_of_scope:", updates)
    assert updates.get("out_of_scope_count") == 2
    assert updates.get("should_end") is True
    
    print("\nALL GLOBAL TOOL TRANSITION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(test_global_tools())
