# tests/integration/test_email_dossier.py
import asyncio
from backend.email_dossier_service import EmailDossierService, EmailConfig, extract_target


class _FakeImap:
    def __init__(self, items):
        self.items = items

    def select(self, folder):
        return "OK", [b"1"]

    def search(self, charset, criteria):
        uids = b" ".join(k.encode() for k, _, _ in self.items)
        return "OK", [uids]

    def fetch(self, uid, message_parts):
        key = uid.decode() if isinstance(uid, bytes) else str(uid)
        for k, sender, body in self.items:
            if k == key:
                raw = f"From: {sender.decode() if isinstance(sender, bytes) else sender}\r\nSubject: Test\r\n\r\n{body}".encode("utf-8")
                return "OK", [(b"1 (RFC822 {100})", raw)]
        return "NO", []

    def logout(self):
        return "BYE", [b"Logged out"]


def test_extract_target():
    assert extract_target("bak: https://instagram.com/abc/ lutfen") == "https://instagram.com/abc/"
    assert extract_target("kullanici @deneme_1 incelensin") == "@deneme_1"
    assert extract_target("hedef yok") is None


def test_allowlist_disler_ve_yanit_yazar(monkeypatch):
    cfg = EmailConfig(allowed=("patron@sirket.com",))
    svc = EmailDossierService(cfg)
    sent = []
    svc._send = lambda m: sent.append(m)
    called = []

    async def fake_handle(sender, body):
        called.append(sender)

    svc.handle_message = fake_handle
    monkeypatch.setattr(svc, "_imap", lambda: _FakeImap([("1", b"patron@sirket.com", "https://x.com/a")]))
    asyncio.run(svc.poll_once())
    assert called == ["patron@sirket.com"]
