"""E-posta (dossier) hattı — IMAP dinle, görevi çalıştır, PDF'li yanıt gönder.

Sözleşme (kaynaktan doğrulandı):
  POST /api/initiate            {client_id, url, scraper_type:"cross", ...}
  GET  /api/tasks/{id}/graph    ?client_id=...   -> available/reason/nodes/edges
  POST /api/tasks/{id}/cancel   ?client_id=...&reason=...
  Kimlik: X-API-Key

Dürüstlük kuralları:
  - Görev başlamazsa yanıt sunucunun mesajını AYNEN taşır (423 kasa, 451 çocuk
    kilidi, 429 hız). "İşleme alındı" maskesi yok.
  - Kanıt yoksa PDF'e düğüm basılmaz; sebep yazılır.
  - reportlab yoksa PDF ÜRETİLMEZ; yanıt eki olmaz ve sebebi yazılır.
  - Parola/posta/token loglanmaz.
"""
from __future__ import annotations

import asyncio
import imaplib
import json
import logging
import os
import re
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from email import message_from_bytes
from email.utils import parseaddr
from typing import Any

import httpx

log = logging.getLogger("pineal.email_dossier")

_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_HANDLE_RE = re.compile(r"(?<![\w@])@([A-Za-z0-9._]{2,40})")
_SEEN_LIMIT = 5000


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class EmailConfig:
    api_base: str = field(default_factory=lambda: _env("PINEAL_API_BASE", "http://127.0.0.1:8000").rstrip("/"))
    token: str = field(default_factory=lambda: _env("PINEAL_TOKEN"))
    client_id: str = field(default_factory=lambda: _env("PINEAL_EMAIL_CLIENT_ID", "mail_operator"))
    imap_host: str = field(default_factory=lambda: _env("PINEAL_EMAIL_IMAP_HOST"))
    imap_port: int = field(default_factory=lambda: int(_env("PINEAL_EMAIL_IMAP_PORT", "993")))
    imap_user: str = field(default_factory=lambda: _env("PINEAL_EMAIL_IMAP_USER"))
    imap_password: str = field(default_factory=lambda: _env("PINEAL_EMAIL_IMAP_PASSWORD"))
    imap_folder: str = field(default_factory=lambda: _env("PINEAL_EMAIL_IMAP_FOLDER", "INBOX"))
    smtp_host: str = field(default_factory=lambda: _env("PINEAL_EMAIL_SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(_env("PINEAL_EMAIL_SMTP_PORT", "465")))
    smtp_user: str = field(default_factory=lambda: _env("PINEAL_EMAIL_SMTP_USER"))
    smtp_password: str = field(default_factory=lambda: _env("PINEAL_EMAIL_SMTP_PASSWORD"))
    sender: str = field(default_factory=lambda: _env("PINEAL_EMAIL_FROM"))
    allowed: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            s.strip().lower() for s in _env("PINEAL_EMAIL_ALLOWED_SENDERS").split(",") if s.strip()
        )
    )
    poll_seconds: int = field(default_factory=lambda: int(_env("PINEAL_EMAIL_POLL_SECONDS", "30")))
    max_wait_seconds: int = field(default_factory=lambda: int(_env("PINEAL_EMAIL_MAX_WAIT_SECONDS", "600")))
    seen_path: str = field(default_factory=lambda: _env("PINEAL_EMAIL_SEEN_PATH", "memory/email_dossier_seen.json"))

    def missing(self) -> list[str]:
        need = {
            "PINEAL_TOKEN": self.token,
            "PINEAL_EMAIL_IMAP_HOST": self.imap_host,
            "PINEAL_EMAIL_IMAP_USER": self.imap_user,
            "PINEAL_EMAIL_IMAP_PASSWORD": self.imap_password,
            "PINEAL_EMAIL_SMTP_HOST": self.smtp_host,
            "PINEAL_EMAIL_FROM": self.sender,
        }
        return [k for k, v in need.items() if not v]


def extract_target(text: str) -> str | None:
    """Gövdeden hedef çıkarır: ilk URL, yoksa @kullanıcı adı. Uydurmaz."""
    body = (text or "").strip()
    if not body:
        return None
    url = _URL_RE.search(body)
    if url:
        return url.group(0).rstrip(").,;")
    handle = _HANDLE_RE.search(body)
    return f"@{handle.group(1)}" if handle else None


def _plain_body(msg) -> str:
    """HTML gövdeyi kabaca metne indirir; en fazla 4000 karakter."""
    part = msg.get_body(preferencelist=("plain", "html")) if msg.is_multipart() else msg
    if part is None:
        return ""
    try:
        raw = part.get_content()
    except (LookupError, KeyError):
        raw = str(part.get_payload(decode=True) or b"", "utf-8", "replace")
    text = re.sub(r"<[^>]+>", " ", raw) if "<" in raw and ">" in raw else raw
    return re.sub(r"[ \t]+", " ", text).strip()[:4000]


def _seen_load(path: str) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [str(x) for x in data] if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _seen_save(path: str, seen: list[str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seen[-_SEEN_LIMIT:], f)


def build_pdf(task_id: str, graph: dict, target: str) -> tuple[bytes | None, str]:
    """Kanıttan PDF üretir. reportlab yoksa (None, sebep) döner — sahte eki yok."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        return None, "reportlab kurulu değil (requirements-osint/opsiyonel)"

    import io

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _, h = A4
    y = h - 60
    c.setFont("Helvetica-Bold", 15)
    c.drawString(50, y, "ATLAS EPIFIZ - GIZLI DOSYA")
    y -= 22
    c.setFont("Helvetica", 9)
    for line in (
        f"Gorev: {task_id}",
        f"Hedef: {target}",
        f"Dugum: {graph.get('node_count', 0)} / Kenar: {graph.get('edge_count', 0)}",
        f"Not: {graph.get('machine_note', '')}",
        "",
    ):
        c.drawString(50, y, line[:110])
        y -= 13
    for node in graph.get("nodes", [])[:40]:
        if y < 60:
            c.showPage()
            c.setFont("Helvetica", 9)
            y = h - 60
        c.drawString(50, y, f"[{node.get('kind')}] {node.get('label')} (kanit={node.get('evidence_count')})"[:110])
        y -= 12
    c.save()
    return buf.getvalue(), ""


class EmailDossierService:
    def __init__(self, cfg: EmailConfig | None = None) -> None:
        self.cfg = cfg or EmailConfig()
        self._seen = _seen_load(self.cfg.seen_path)
        self._stop = asyncio.Event()

    # ── taşıma (test için enjekte edilebilir) ─────────────────────
    def _imap(self):
        conn = imaplib.IMAP4_SSL(self.cfg.imap_host, self.cfg.imap_port)
        conn.login(self.cfg.imap_user, self.cfg.imap_password)
        return conn

    def _send(self, msg: EmailMessage) -> None:
        if self.cfg.smtp_port == 465:
            with smtplib.SMTP_SSL(self.cfg.smtp_host, self.cfg.smtp_port) as s:
                if self.cfg.smtp_user:
                    s.login(self.cfg.smtp_user, self.cfg.smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.cfg.smtp_host, self.cfg.smtp_port) as s:
                s.starttls()
                if self.cfg.smtp_user:
                    s.login(self.cfg.smtp_user, self.cfg.smtp_password)
                s.send_message(msg)

    # ── API ───────────────────────────────────────────────────────
    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "X-API-Key": self.cfg.token}

    async def _initiate(self, target: str) -> tuple[str | None, str]:
        payload = {
            "client_id": self.cfg.client_id,
            "url": target if target.startswith("http") else "",
            "rituals": "" if target.startswith("http") else target,
            "playlist": "",
            "envies": "",
            "scraper_type": "cross",
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                res = await client.post(f"{self.cfg.api_base}/api/initiate", json=payload, headers=self._headers())
        except httpx.HTTPError as exc:
            return None, f"API erisilemedi: {type(exc).__name__}"
        body: dict[str, Any] = {}
        try:
            body = res.json()
        except ValueError:
            pass
        if res.status_code >= 400:
            code = (body.get("error") or {}).get("code", "")
            msg = (body.get("error") or {}).get("message") or body.get("detail") or res.text[:200]
            return None, f"HTTP {res.status_code} {code} {msg}".strip()
        task_id = body.get("task_id")
        return (str(task_id), "") if task_id else (None, "yanitta task_id yok")

    async def _graph(self, task_id: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.get(
                f"{self.cfg.api_base}/api/tasks/{task_id}/graph",
                params={"client_id": self.cfg.client_id},
                headers=self._headers(),
            )
        if res.status_code >= 400:
            raise RuntimeError(f"graf HTTP {res.status_code}")
        return res.json()

    async def _cancel(self, task_id: str, reason: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(
                    f"{self.cfg.api_base}/api/tasks/{task_id}/cancel",
                    params={"client_id": self.cfg.client_id, "reason": reason},
                    headers=self._headers(),
                )
        except httpx.HTTPError:
            pass

    async def _run_task(self, target: str) -> tuple[str, dict | None, str]:
        """Görevi başlatır, grafı bekler. (durum, graf, mesaj) döner."""
        task_id, err = await self._initiate(target)
        if not task_id:
            return "error", None, err

        waited = 0
        while waited < self.cfg.max_wait_seconds:
            await asyncio.sleep(3)
            waited += 3
            try:
                graph = await self._graph(task_id)
            except RuntimeError as exc:
                return "error", None, f"{exc} (gorev {task_id})"
            if graph.get("available") and graph.get("nodes"):
                return "ok", graph, task_id
        await self._cancel(task_id, "email_timeout")
        return "timeout", None, task_id

    # ── yanıt ─────────────────────────────────────────────────────
    def _reply(self, to_addr: str, subject: str, lines: list[str], attachment: bytes | None) -> None:
        msg = EmailMessage()
        msg["From"] = self.cfg.sender
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content("\n".join(lines))
        if attachment:
            msg.add_attachment(attachment, maintype="application", subtype="pdf", filename="dossier.pdf")
        self._send(msg)

    async def handle_message(self, sender: str, body: str) -> None:
        target = extract_target(body)
        if not target:
            self._reply(sender, "ATLAS EPIFIZ - hedef bulunamadi",
                        ["Gövdede URL veya @kullanici yok.", "Örnek: https://instagram.com/kullanici/"], None)
            return

        status, graph, info = await self._run_task(target)

        if status == "error":
            self._reply(sender, "ATLAS EPIFIZ - gorev baslatilamadi",
                        [f"Hedef: {target}", f"Sunucu: {info}",
                         "", "Kasa kilitliyse (423) konsoldan açıp tekrar gönderin."], None)
            return
        if status == "timeout":
            self._reply(sender, "ATLAS EPIFIZ - kanit gelmedi",
                        [f"Hedef: {target}", f"Gorev: {info}", "Süre doldu; görev iptal edildi."], None)
            return

        pdf, pdf_err = build_pdf(info, graph or {}, target)
        lines = [f"Hedef: {target}", f"Gorev: {info}",
                 f"Dugum: {graph.get('node_count')} / Kenar: {graph.get('edge_count')}",
                 graph.get("machine_note") or ""]
        if pdf_err:
            lines += ["", f"PDF URETILEMEDI: {pdf_err}"]
        self._reply(sender, f"ATLAS EPIFIZ - dosya {info}", lines, pdf)

    # ── döngü ─────────────────────────────────────────────────────
    async def poll_once(self) -> int:
        """Bir tur: UNSEEN tara, izinli+görülmemiş olanları işle. İşlenen sayısı."""
        done = 0
        conn = await asyncio.to_thread(self._imap)
        try:
            await asyncio.to_thread(conn.select, self.cfg.imap_folder)
            typ, data = await asyncio.to_thread(conn.search, None, "UNSEEN")
            if typ != "OK":
                return 0
            for uid in (data[0] or b"").split():
                key = uid.decode()
                if key in self._seen:
                    continue
                typ, raw = await asyncio.to_thread(conn.fetch, uid, "(RFC822)")
                if typ != "OK" or not raw or not raw[0]:
                    continue
                msg = message_from_bytes(raw[0][1])
                sender = parseaddr(msg.get("From", ""))[1].lower()
                if self.cfg.allowed and sender not in self.cfg.allowed:
                    log.info("gonderen izinli degil: %s", sender)
                    self._seen.append(key)
                    continue
                await self.handle_message(sender, _plain_body(msg))
                self._seen.append(key)
                done += 1
                _seen_save(self.cfg.seen_path, self._seen)
        finally:
            try:
                await asyncio.to_thread(conn.logout)
            except Exception:  # noqa: BLE001 - kapanış hatası turu öldürmesin
                pass
        return done

    async def run(self) -> None:
        missing = self.cfg.missing()
        if missing:
            log.warning("e-posta hatti kapali, eksik: %s", ", ".join(missing))
            return
        log.info("e-posta dossier hatti acildi (client_id=%s)", self.cfg.client_id)
        while not self._stop.is_set():
            try:
                await self.poll_once()
            except Exception as exc:  # noqa: BLE001 - döngü tek hatada ölmez
                log.warning("tur hatasi: %s", type(exc).__name__)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.cfg.poll_seconds)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()


def start_email_dossier() -> asyncio.Task | None:
    """`PINEAL_EMAIL_ENABLED=1` ise arka plan görevini başlatır."""
    if _env("PINEAL_EMAIL_ENABLED") not in {"1", "true", "True"}:
        return None
    return asyncio.create_task(EmailDossierService().run(), name="email_dossier")
