import pytest
from agent_core.services.canonical_memory import CanonicalMemory
from agent_core.services.hindsight_memory import HindsightMemory
from agent_core.utils.security import is_safe_url
from backend.api import app
from fastapi.testclient import TestClient

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

def test_interpreter_endpoint_secure_by_default(monkeypatch):
    """ENABLE_INTERPRETER kapalıyken uç 403 verir — ama kasa mandalı ÖNCE gelir.

    [KASA MANDALI] Sıra `PolicyKernel._GATE_ORDER` ile birebir: kasa kilidi,
    ENABLE_* bayrağından ÖNCE reddedilir (Tüzük Md.4.1 — kasa istisnasızdır).
    Aksi halde denetim izinde "gate_disabled" görünür ve kasa ihlali
    maskelenirdi. Keyfi kod icrası = keyfi ağ erişimi, dolayısıyla bu uç
    VAULT_EGRESS_ROUTES içindedir. İki hâl de ayrı ayrı ölçülür.

    (Eski sürüm `os.environ`'ı elle yazıp geri almıyordu; monkeypatch ile
    ortam artık test sonu temizleniyor.)
    """
    from backend import api

    monkeypatch.setenv("ENABLE_INTERPRETER", "false")
    payload = {"client_id": "test", "prompt": "print('hi')"}

    # 1) Kasa KİLİTLİ: dış-çıkış kapısı her şeyden önce 423 Locked verir.
    monkeypatch.setattr(api, "_check_vault_interlock", lambda _cid: False)
    locked = client.post("/api/experimental/interpreter/execute", json=payload)
    assert locked.status_code == 423
    assert locked.json()["error"]["code"] == "VAULT_LOCKED"

    # 2) Kasa AÇIK: interpreter yine de varsayılan KAPALI -> 403.
    monkeypatch.setattr(api, "_check_vault_interlock", lambda _cid: True)
    resp = client.post("/api/experimental/interpreter/execute", json=payload)
    assert resp.status_code == 403
    assert "disabled by default for security" in resp.text
