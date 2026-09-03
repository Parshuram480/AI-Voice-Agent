import pytest
import json
from fastapi.testclient import TestClient
from app.main import app

def test_retell_websocket_protocol():
    client = TestClient(app)
    call_id = "test_call_12345"

    with client.websocket_connect(f"/retell-llm-websocket/{call_id}") as websocket:
        # 1. Check initial config event from server
        config_msg = websocket.receive_text()
        config_data = json.loads(config_msg)
        assert config_data.get("response_type") == "config"
        assert config_data.get("config", {}).get("auto_reconnect") is True

        # 2. Test ping_pong event
        websocket.send_text(json.dumps({
            "interaction_type": "ping_pong",
            "timestamp": 1700000000
        }))
        pong_msg = websocket.receive_text()
        pong_data = json.loads(pong_msg)
        assert pong_data.get("response_type") == "ping_pong"
        assert pong_data.get("timestamp") == 1700000000

        # 3. Test response_required event
        websocket.send_text(json.dumps({
            "interaction_type": "response_required",
            "response_id": 1,
            "transcript": [
                {"role": "user", "content": "Hello, is this working?"}
            ]
        }))

        # Collect response stream chunks until content_complete is true
        received_tokens = []
        is_complete = False

        for _ in range(50):
            resp_text = websocket.receive_text()
            resp_json = json.loads(resp_text)
            assert resp_json.get("response_type") == "response"
            assert resp_json.get("response_id") == 1

            if resp_json.get("content"):
                received_tokens.append(resp_json.get("content"))

            if resp_json.get("content_complete") is True:
                is_complete = True
                break

        assert is_complete is True
        print(f"\n[TEST PASS] Full streamed text: {''.join(received_tokens)}")
