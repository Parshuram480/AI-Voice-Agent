import os
from dotenv import load_dotenv
from retell import Retell

load_dotenv()

RETELL_API_KEY = os.getenv("RETELL_API_KEY")
RETELL_AGENT_ID = os.getenv("RETELL_AGENT_ID")
RETELL_PHONE_NUMBER = os.getenv("RETELL_PHONE_NUMBER") or os.getenv("TWILIO_PHONE_NUMBER")
MY_CELL_PHONE = os.getenv("MY_CELL_PHONE")

if not RETELL_API_KEY:
    print("ERROR: RETELL_API_KEY is not set in .env")
    exit(1)

if not RETELL_AGENT_ID:
    print("ERROR: RETELL_AGENT_ID is not set in .env")
    exit(1)

client = Retell(api_key=RETELL_API_KEY)

print(f"Connecting to Retell AI...")
print(f"Agent ID: {RETELL_AGENT_ID}")
print(f"To: {MY_CELL_PHONE}")
print(f"From: {RETELL_PHONE_NUMBER}")

try:
    if not RETELL_PHONE_NUMBER:
        print("\nNote: No RETELL_PHONE_NUMBER or TWILIO_PHONE_NUMBER set in .env.")
        print("Creating a browser Web Call instead for instant testing...")
        web_call = client.call.create_web_call(agent_id=RETELL_AGENT_ID)
        print(f"\n✓ Web Call Created! Call ID: {web_call.call_id}")
        print(f"Access Token: {web_call.access_token}")
        print("You can test your agent immediately in the Retell dashboard web tester!")
    else:
        call = client.call.create_phone_call(
            from_number=RETELL_PHONE_NUMBER,
            to_number=MY_CELL_PHONE,
            override_agent_id=RETELL_AGENT_ID
        )
        print(f"\n✓ Outbound phone call initiated! Call ID: {call.call_id}")
        print(f"Calling {MY_CELL_PHONE} now...")
except Exception as e:
    print(f"\n[ERROR] Failed to initiate call: {e}")
