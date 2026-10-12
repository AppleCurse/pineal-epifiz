import pytest
from agent_core.services.canonical_memory import CanonicalMemory
from agent_core.services.hindsight_memory import HindsightMemory
from agent_core.utils.security import is_safe_url
from backend.api import app
from fastapi.testclient import TestClient
import os

client = TestClient(app)

def test_canonical_memory_path_traversal():
    mem = CanonicalMemory(storage_path="./test_mem")
    with pytest.raises(ValueError, match="Geçersiz task_id formatı"):
        mem.get_task_memory("../../../etc/passwd")

def test_hindsight_memory_path_traversal():
    mem = HindsightMemory(storage_path="./test_mem")
    with pytest.raises(ValueError, match="Geçersiz task_id formatı"):
        mem.get_task_memory("../../../etc/passwd")

def test_is_safe_url():
    assert not is_safe_url("http://localhost:8000")
    assert not is_safe_url("http://127.0.0.1/admin")
    assert not is_safe_url("http://169.254.169.254/latest/meta-data")
    assert not is_safe_url("http://[::1]/")
    assert not is_safe_url("http://10.0.0.1/internal")
    assert not is_safe_url("http://192.168.1.1/router")
    assert not is_safe_url("http://172.16.0.1/private")
    assert not is_safe_url("http://metadata.google.internal")
    
    assert is_safe_url("http://example.com")
    assert is_safe_url("https://google.com")

def test_interpreter_endpoint_secure_by_default():
    # When ENABLE_INTERPRETER is not set or false, should return 403
    os.environ["ENABLE_INTERPRETER"] = "false"
    payload = {"client_id": "test", "prompt": "print('hi')"}
    resp = client.post("/api/experimental/interpreter/execute", json=payload)
    assert resp.status_code == 403
    assert "disabled by default for security" in resp.text
