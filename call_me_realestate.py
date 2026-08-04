"""
call_me_realestate.py — Trigger an outbound real estate agent call via Twilio.

Usage:
    python call_me_realestate.py

This script:
1. Calls your phone via Twilio
2. The AI real estate agent (Pinnacle Realty) pitches properties and books viewings.

Prerequisites:
- Server running: uvicorn app.main:app --reload --port 8000
- REALESTATE_AGENT_CONFIG=client_configs/realestate_listings.json in your .env
- Ngrok tunnel active and NGROK_URL set in .env
"""

import os
import sys
from twilio.rest import Client
from dotenv import load_dotenv

# Load credentials from your .env file
load_dotenv(override=True)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
NGROK_URL = os.getenv("NGROK_URL")
MY_CELL_PHONE = os.getenv("MY_CELL_PHONE")
CUSTOMER_NAME = os.getenv("CUSTOMER_NAME", "Alex")
LANGUAGE = os.getenv("LANGUAGE", "en")

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

# Ensure NGROK_URL points to /voice endpoint and includes client_id=realestate
voice_url = NGROK_URL.strip().rstrip("/")
if not voice_url.endswith("/voice"):
    voice_url = voice_url + "/voice"

import urllib.parse
encoded_name = urllib.parse.quote(CUSTOMER_NAME)
encoded_lang = urllib.parse.quote(LANGUAGE)

if "?" in voice_url:
    voice_url += f"&client_id=realestate&customer_name={encoded_name}&language={encoded_lang}"
else:
    voice_url += f"?client_id=realestate&customer_name={encoded_name}&language={encoded_lang}"

print("=" * 50)
print("  Pinnacle Realty Voice Agent -- Outbound Call")
print("=" * 50)
print(f"  Calling: {MY_CELL_PHONE}")
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
print("The real estate agent will pitch Pinnacle Realty listings to you!")
print("\nProperties in catalog:")
print("  - The Metro Lofts - Unit 4B ($215,000)")
print("  - Riverview Condos - Unit 12C ($310,000)")
print("  - Maplewood Terraces ($385,000)")
print("  - The Greenwood Classic ($475,000)")
print("  - Sunnyvale Ranch ($525,000)")
print("  - The Summit Estate ($1,150,000)")
