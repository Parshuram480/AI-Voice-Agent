"""
call_me_sales.py — Trigger an outbound sales agent call via Twilio.

Usage:
    python call_me_sales.py

This script:
1. Sets the SALES_AGENT_CONFIG env var so the server loads the sales tools
2. Calls your phone via Twilio
3. The AI sales agent pitches Nova Telecom Wi-Fi plans to you

Prerequisites:
- Server running: uvicorn app.main:app --reload --port 8000
- SALES_AGENT_CONFIG=client_configs/sales_products.json in your .env
- Ngrok tunnel active and NGROK_URL set in .env
"""

import os
import sys
from twilio.rest import Client
from dotenv import load_dotenv

# Load credentials from your .env file
load_dotenv()

# # Verify sales config is set
# sales_config = os.getenv("SALES_AGENT_CONFIG")
# if not sales_config:
#     print("⚠️  SALES_AGENT_CONFIG is not set in your .env file!")
#     print("   Add this line to your .env:")
#     print("   SALES_AGENT_CONFIG=client_configs/sales_products.json")
#     print()
#     print("   Then restart your server (uvicorn app.main:app --reload --port 8000)")
#     sys.exit(1)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
NGROK_URL = os.getenv("NGROK_URL")
MY_CELL_PHONE = os.getenv("MY_CELL_PHONE")
CUSTOMER_NAME = os.getenv("CUSTOMER_NAME", "Ajit Yadav")

# Validate required vars
missing = []
if not TWILIO_ACCOUNT_SID:
    missing.append("TWILIO_ACCOUNT_SID")
if not TWILIO_AUTH_TOKEN:
    missing.append("TWILIO_AUTH_TOKEN")
if not TWILIO_NUMBER:
    missing.append("TWILIO_PHONE_NUMBER")
if not NGROK_URL:
    missing.append("NGROK_URL")
if not MY_CELL_PHONE:
    missing.append("MY_CELL_PHONE")

if missing:
    print(f"❌ Missing environment variables: {', '.join(missing)}")
    print("   Please set them in your .env file.")
    sys.exit(1)

if MY_CELL_PHONE == "+919999999999":
    print("❌ Please set MY_CELL_PHONE to your actual phone number in .env!")
    sys.exit(1)

# Ensure NGROK_URL points to /voice endpoint and includes client_id=sales
voice_url = NGROK_URL.strip().rstrip("/")
if not voice_url.endswith("/voice"):
    voice_url = voice_url + "/voice"

import urllib.parse
encoded_name = urllib.parse.quote(CUSTOMER_NAME)

if "?" in voice_url:
    voice_url += f"&client_id=sales&customer_name={encoded_name}"
else:
    voice_url += f"?client_id=sales&customer_name={encoded_name}"

print("=" * 50)
print("  Nova Telecom Sales Agent -- Outbound Call")
print("=" * 50)
print(f"  Calling: {MY_CELL_PHONE}")
# print(f"  Catalog: {sales_config}")
print(f"  Webhook: {voice_url}")
print("=" * 50)

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

call = client.calls.create(
    to=MY_CELL_PHONE,
    from_=TWILIO_NUMBER,
    url=voice_url,
    method="POST"
)

print(f"\n[SUCCESS] Call initiated! Call SID: {call.sid}")
print("Your phone should ring in a few seconds...")
print("The sales agent will pitch Nova Telecom Wi-Fi plans to you!")
print("\nProducts in catalog:")
print("  - Nova Basic 100Mbps -- $39.99/month (Internet Plans)")
print("  - Nova Stream 500Mbps -- $59.99/month (Internet Plans)")
print("  - Nova Gamer Pro 1Gbps Fiber -- $89.99/month (Internet Plans)")
print("  - Nova Whole-Home Mesh System -- $9.99/month (Hardware Add-ons)")
print("  - Nova Range Extender -- $4.99/month (Hardware Add-ons)")
print("  - The Family Entertainment Bundle -- $79.99/month (Bundles)")
print("  - The Ultimate Home Bundle -- $89.99/month (Bundles)")
