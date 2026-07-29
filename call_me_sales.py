"""
call_me_sales.py — Trigger an outbound sales agent call via Twilio.

Usage:
    python call_me_sales.py

This script:
1. Sets the SALES_AGENT_CONFIG env var so the server loads the sales tools
2. Calls your phone via Twilio
3. The AI sales agent pitches TechNova Solutions products to you

Prerequisites:
- Server running: uvicorn app.main:app --reload --port 8000
- SALES_AGENT_CONFIG=data/sales_products.json in your .env
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
#     print("   SALES_AGENT_CONFIG=data/sales_products.json")
#     print()
#     print("   Then restart your server (uvicorn app.main:app --reload --port 8000)")
#     sys.exit(1)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
NGROK_URL = os.getenv("NGROK_URL")
MY_CELL_PHONE = os.getenv("MY_CELL_PHONE")

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
voice_url = NGROK_URL.rstrip("/")
if not voice_url.endswith("/voice"):
    if not voice_url.endswith("/voice"):
        voice_url = voice_url.rstrip("/") + "/voice"

voice_url += "?client_id=sales"

print("=" * 50)
print("  TechNova Sales Agent -- Outbound Call")
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
print("The sales agent will pitch TechNova products to you!")
print("\nProducts in catalog:")
print("  - Nova Smart Hub Pro -- $129.99 (Smart Home)")
print("  - Nova Wireless Earbuds X1 -- $79.99 (Audio)")
print("  - Nova FitBand Ultra -- $149.99 (Wearables)")
print("  - Nova Portable Charger 20K -- $39.99 (Accessories)")
print("  - Nova Smart Bulb Kit -- $49.99 (Smart Home)")
print("  - Nova Bluetooth Speaker Max -- $99.99 (Audio)")
print("  - Nova Smartwatch Series 5 -- $249.99 (Wearables)")
print("  - Nova USB-C Hub 8-in-1 -- $59.99 (Accessories)")
