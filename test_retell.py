import os
from dotenv import load_dotenv
from retell import Retell

load_dotenv()

client = Retell(api_key=os.getenv("RETELL_API_KEY"))
print("Agent methods:", [m for m in dir(client.agent) if not m.startswith("_")])
print("Call methods:", [m for m in dir(client.call) if not m.startswith("_")])

# In v5.x, agent retrieval might be client.agent.retrieve(agent_id) or client.agents.retrieve
try:
    if hasattr(client.agent, "retrieve"):
        agent = client.agent.retrieve(os.getenv("RETELL_AGENT_ID"))
        print("\nAgent retrieved successfully:", agent.agent_name, "| Voice:", agent.voice_id)
except Exception as e:
    print("Agent retrieve error:", e)

try:
    web_call = client.call.create_web_call(agent_id=os.getenv("RETELL_AGENT_ID"))
    print("\n--- [SUCCESS] Test Web Call Created! ---")
    print(f"Call ID: {web_call.call_id}")
    print(f"Access Token: {web_call.access_token}")
except Exception as e:
    print("Web call create error:", e)
