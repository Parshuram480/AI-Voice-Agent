import os
from twilio.rest import Client
from dotenv import load_dotenv

# Load credentials from your .env file
load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# The ngrok URL where your AI is running
NGROK_URL = os.getenv("NGROK_URL")  # Update this if your ngrok URL changes!

# YOUR verified Indian mobile number (include +91)
# IMPORTANT: Replace this with your actual cell phone number
MY_CELL_PHONE = os.getenv("MY_CELL_PHONE")     

if MY_CELL_PHONE == "+919999999999":
    print("ERROR: Please open call_me.py and replace +919999999999 with your actual cell phone number!")
    exit(1)

print(f"Connecting to Twilio...")
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

print(f"Calling {MY_CELL_PHONE}...")
call = client.calls.create(
    to=MY_CELL_PHONE,
    from_=TWILIO_NUMBER,
    url=NGROK_URL,
    method="POST"
)

print(f"Call initiated! Call SID: {call.sid}")
print("Your phone should be ringing in 3 seconds!")
