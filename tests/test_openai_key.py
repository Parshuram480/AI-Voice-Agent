import os
import requests
from dotenv import load_dotenv

def test_openai_key():
    # Load environment variables from .env file
    load_dotenv()
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ OPENAI_API_KEY not found in .env file.")
        return
        
    # Mask the key for security when printing
    masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "****"
    print(f"Testing OpenAI API Key: {masked_key}")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        # Hit the /v1/models endpoint which just lists models (good for verifying auth)
        response = requests.get("https://api.openai.com/v1/models", headers=headers)
        
        if response.status_code == 200:
            print("✅ Success! The OpenAI API key is valid and working.")
        else:
            print(f"❌ Failed! API returned status code {response.status_code}.")
            print(f"Error details: {response.text}")
            
    except Exception as e:
        print(f"❌ An error occurred while testing the key: {e}")

if __name__ == "__main__":
    test_openai_key()
