import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from app.logging.logger import log_llm_metrics, METRICS_DIR

def test_log_llm_metrics_creates_file_and_folder():
    """Test that log_llm_metrics creates the metrics folder and proper file formatting."""
    session_id = "test_metrics_session_123"
    metrics = {
        "llm1_prompt_tokens": 100,
        "llm1_completion_tokens": 50,
        "llm1_ttft": 0.45,
        "llm1_generation_time": 1.2,
        "llm1_total_time": 1.65,
        "llm2_prompt_tokens": 80,
        "llm2_completion_tokens": 40,
        "llm2_ttft": 0.3,
        "llm2_generation_time": 0.9,
        "llm2_total_time": 1.2,
        "streaming_started": "2026-07-06 13:16:02.123",
        "streaming_finished": "2026-07-06 13:16:03.773",
        "tool_called": "verify_user",
        "second_llm": "No",
        "history_tokens": 80,
        "summary_tokens": 10,
        "current_user_tokens": 10,
        "timing_user_finished": "13:45:41.100",
        "timing_prompt_assembly_start": "13:45:41.102",
        "timing_prompt_assembly_end": "13:45:41.145",
        "timing_langgraph_invoke": "13:45:41.146",
        "timing_http_sent": "13:45:41.150",
        "timing_first_byte": "13:45:41.390",
        "timing_first_token": "13:45:41.392",
        "timing_tool_start": "13:45:41.520",
        "timing_tool_end": "13:45:41.560",
        "timing_second_llm_send": "13:45:41.561",
        "timing_second_first_token": "13:45:41.730",
        "timing_first_text_to_cartesia": "13:45:41.732",
        "timing_first_audio_from_cartesia": "13:45:41.860",
        "timing_first_packet_to_twilio": "13:45:41.862"
    }
    
    # Ensure directory is clean if it existed
    filepath = os.path.join(METRICS_DIR, f"{session_id}.txt")
    if os.path.exists(filepath):
        os.remove(filepath)
        
    # Call the function
    log_llm_metrics(session_id, metrics)
    
    # Assert folder exists
    assert os.path.exists(METRICS_DIR)
    
    # Assert file exists
    assert os.path.exists(filepath)
    
    # Verify contents
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "=========================" in content
    assert "APPLICATION OVERHEAD" in content
    assert "User Finished Speaking:      13:45:41.100" in content
    assert "STT Final Transcript:        N/A" in content
    assert "Queue Wait End:              N/A" in content
    assert "Memory Retrieval Start:      N/A" in content
    assert "Memory Retrieval End:        N/A" in content
    assert "State Update Start:          N/A" in content
    assert "State Update End:            N/A" in content
    assert "Serialization Start:         N/A" in content
    assert "Serialization End:           N/A" in content
    assert "LLM 1 (ROUTING)" in content
    assert "Prompt Tokens: 100" in content
    assert "Completion Tokens: 50" in content
    assert "TTFT: 0.45s" in content
    assert "Generation Time: 1.2s" in content
    assert "Total Time: 1.65s" in content
    assert "Tool Called: verify_user" in content
    assert "LLM 2 (SYNTHESIS)" in content
    assert "Prompt Tokens: 80" in content
    assert "Completion Tokens: 40" in content
    assert "TTFT: 0.3s" in content
    assert "Generation Time: 0.9s" in content
    assert "Total Time: 1.2s" in content
    
    # Check new micro-timings
    assert "User finished:               13:45:41.100" in content
    assert "Prompt assembly start:       13:45:41.102" in content
    assert "Prompt assembly end:         13:45:41.145" in content
    assert "LangGraph invoke:            13:45:41.146" in content
    assert "HTTP request sent:           13:45:41.150" in content
    assert "First byte from Groq:        13:45:41.390" in content
    assert "First token:                 13:45:41.392" in content
    assert "Tool start:                  13:45:41.520" in content
    assert "Tool end:                    13:45:41.560" in content
    assert "Second LLM send:             13:45:41.561" in content
    assert "Second first token:          13:45:41.730" in content
    assert "First text to Cartesia:      13:45:41.732" in content
    assert "First audio from Cartesia:   13:45:41.860" in content
    assert "First packet to Twilio:      13:45:41.862" in content

    # Cleanup
    if os.path.exists(filepath):
        os.remove(filepath)

if __name__ == "__main__":
    print("Running test_log_llm_metrics_creates_file_and_folder...")
    test_log_llm_metrics_creates_file_and_folder()
    print("Test passed successfully!")
