"""Envanter sayfası üreteci — ``docs/envanter.html`` (tek dosya, çevrimdışı).

Neden var:
    Depoda tanıtım/envanter sayfası, dosyaların YALNIZ adını ve satır sayısını
    gösteriyordu. Sonuç: (a) 30 dosyanın adı vardı ama açıklaması yoktu,
    (b) 31 Python dosyası sayfada HİÇ yoktu (``task_executor.py``,
    ``backend/api.py`` dâhil — sistemin çekirdeği), (c) derleme hattı klasörü,
    Android istemcisi, ön yüz, Cloudflare fonksiyonları, 233 test dosyası ve
    ``docs/reports/`` altındaki 41 rapor hiç görünmüyordu, (d) ``.env.example``
    içindeki 98 ayarın anlamı ve ``config/*`` dosyalarının içeriği yoktu.

Bu üretici, gerçeği depodan OKUR (uydurmaz) ve tek bir HTML sayfası yazar:

  * **Python docstring'leri** AST ile çıkarılır (bu yüzden açıklamasız dosyalara
    docstring yazmak sayfayı da besler).
  * **Kürasyon sözlüğü** (``CURATED``/``FOLDERS``/``NOTES``): öncelikli
    dosyalar, klasörler, uç noktalar için elle yazılmış Türkçe açıklamalar.
  * **SKILL.md front-matter**, ``config/*.json`` içindeki ``_meta.purpose``,
    Rust ``//!``/``///`` belgeleri, TS/Svelte/Kotlin dışa aktarımları,
    Markdown başlıkları ve test adları otomatik özetlenir.
  * **``.env.example``**: 98 değişken, ait olduğu grup başlığı ve üstündeki
    yorum satırlarıyla birlikte tek tek anlamlandırılır.

Çalıştırma::

    python scripts/generate_inventory_page.py            # docs/envanter.html
    python scripts/generate_inventory_page.py --check     # bayat mı? (CI)

``--check`` modunda sayfa yeniden üretilir ve disktekiyle karşılaştırılır;
farklıysa sıfırdan farklı çıkış koduyla "bayat" der (sessiz bayatlama yok).
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "envanter.html"

# --------------------------------------------------------------------------- #
# 1) KÜRASYON — öncelikli dosyalar için elle yazılmış açıklamalar
# --------------------------------------------------------------------------- #

NEW_FILES = {
    "backend/routes/language.py": "API-BÖLME 2 ile doğdu (açıklamasız bloğun taşındığı modül).",
    "backend/routes/speech_audio.py": "API-BÖLME 3: gizli TTS sesini TTL/boyut sınırıyla sunan dar HTTP yüzeyi.",
}

CORE = {
    "agent_core/task_executor.py": (
        "Sistemin orkestra şefi. `execute_task` çağrısı planı (CognitiveRouter) kurar, "
        "her ajanı AYRI duvar saati sınırıyla koşar, kanıt kaydı + SHA-256 mühür üretir, "
        "deterministik 7-sütun motorunu çalıştırır, claim-gate/quote-guard kapılarını "
        "uygular, sorumluluk zincirini mühürler ve destek&devam akışını yönetir. "
        "Agent Rack durumu yalnız adını taşıyan ajanın koşusundan yayınlanır."
    ),
    "backend/api.py": (
        "FastAPI yüzeyi: kimlik doğrulama, oda sahipliği, hız sınırı, kasa mandalı, "
        "WS telemetrisi, OpenAI-uyumlu `/v1/*` uçları ve tüm özellik uçları. "
        "6.000 satırlık tek-modül tavanına tabidir; yeni uç eklemek yerine modül çıkarılır "
        "(bkz. §API-BÖLME)."
    ),
    "agent_core/services/llm_gateway.py": (
        "Tüm model trafiğinin TEK kapısı: taşıma seçimi (9Router→OpenRouter→direct→local), "
        "görev/ajan bazlı model zincirleri, çağrı-öncesi bütçe rezervasyonu ve spend cap, "
        "dürüst hata sözleşmesi (boş `choices`, model ikamesi reddi, yalnız geçici hatada retry) "
        "ve mühürlenebilir call-id kayıtları."
    ),
    "backend/routes/language.py": (
        "YENİ (API-BÖLME 2): `/api/language/status|detect|translate`. Tavanda duran "
        "`backend/api.py`'den çıkarıldı; uç gövdeleri değişmedi, bağımlılıklar enjekte edilir."
    ),
    "backend/routes/speech_audio.py": (
        "YENİ (API-BÖLME 3): TTS wav indirme ucu; yalnız içerik-hash'li dosya, "
        "private/no-store, TTL ve disk tavanı; geçici STT/Piper dosyaları sunulmaz."
    ),
    "README.md": (
        "Sistemin ANA KAPISI (P8'de sıfırdan yazıldı): 15 bölümde, "
        "**herkesin anlayabileceği** bir dille anlatır — sistem ne işe yarar, nasıl "
        "çalışır, ekranda ne görürsün, 7 dalga motoru ve 13 ajan ne yapar, 26 yetenek "
        "nedir, güvenlik kilitleri, nasıl kurulur/çalıştırılır, Aspasia'ya neler "
        "sorulur, 62 API ucu, P0→P8 yenilikleri ve **ölçülen ↔ DOĞRULANMADI** tablosu. "
        "Her iddia kod yoluyla doğrulanmıştır; ölçülemeyen hiçbir şey 'çalışıyor' yazılmaz."
    ),
    "backend/services/aspasia_state.py": (
        "YENİ (API-BÖLME 6): `/api/aspasia/state` denetim görünümünün gövdesi "
        "(kayıtlı ajanlar, görev durumu, bütçe, kota, anomali, **sayfalı** çağrı izi "
        "`offset`/`limit` + `call_window`). `backend/api.py` tavanından çıkarıldı; "
        "bağımlılıklar enjekte edilir (dairesel bağımlılık yok)."
    ),
}

CATEGORY_A = [
    "agent_core/agents/authenticity_auditor.py",
    "agent_core/agents/cognitive_profiler.py",
    "agent_core/agents/depth_analyst.py",
    "agent_core/agents/friction_detector.py",
    "agent_core/agents/interpreter_agent.py",
    "agent_core/agents/lilith_growth.py",
    "agent_core/agents/mirror_truth.py",
    "agent_core/agents/osint_investigator.py",
    "agent_core/agents/passion_mapper.py",
    "agent_core/agents/pattern_interrupt.py",
    "agent_core/agents/resonance_synthesizer.py",
    "agent_core/agents/target_psyche_profiler.py",
    "agent_core/services/canonical_memory.py",
    "agent_core/services/cognitive_router.py",
    "agent_core/services/decision_engine.py",
    "agent_core/services/follower_audit.py",
    "agent_core/services/llm_gateway.py",
    "agent_core/services/memory_injector.py",
    "agent_core/services/quote_guard.py",
    "agent_core/services/search_engine.py",
    "agent_core/services/uncertainty_engine.py",
    "agent_core/services/vision_analyzer.py",
    "agent_core/aspasia/aspasia_chief.py",
    "agent_core/domain/memory_models.py",
    "agent_core/domain/pipeline_status.py",
    "agent_core/scraper/run_scraper.py",
    "agent_core/shadow/shadow_executor.py",
    "agent_core/nlp/dark_nlp.py",
    "agent_core/chat/dialogue_manager.py",
    "agent_core/schemas/telemetry.py",
]

CATEGORY_B = [
    "main.py", "scraper.py", "live_llm_gate.py", "run_lilith.py",
    "agent_core/task_executor.py", "agent_core/config_loader.py", "agent_core/version.py",
    "backend/api.py", "backend/checkpoint_store.py", "backend/middleware/body_size_limit.py",
    "backend/routes/support.py", "backend/routes/websocket.py", "backend/routes/tasks.py",
    "backend/security/principal.py", "backend/security/task_ownership.py",
    "backend/security/task_access.py",
    "backend/services/aspasia_state.py",
    "scripts/verify_command_loop.py",
    "scripts/revert_verification_p8.py",
    "scripts/smoke_test_browser.py", "scripts/generate_routing_shadows.py",
    "scripts/audit_regression.py", "scripts/verify_openrouter_catalog.py",
    "scripts/preflight_9router.py", "scripts/export_skills.py", "scripts/run_task.py",
]

API_SPLIT = {
    "backend/routes/language.py": "taşındı",
    "backend/routes/speech_audio.py": "taşındı (TTS gizli dosya TTL/boyut sınırı)",
    "backend/routes/company.py": "taşındı (API-BÖLME 7)",
    "backend/routes/support.py": "taşındı (B0)",
    "backend/routes/tasks.py": "taşındı",
    "backend/routes/websocket.py": "taşındı",
    "backend/middleware/body_size_limit.py": "taşındı (ilk bölme)",
    "backend/security/principal.py": "taşındı",
    "backend/security/task_ownership.py": "taşındı",
    "backend/security/task_access.py": "taşındı",
}

# Klasör açıklamaları ve bölüm notları VERİ dosyasındadır: docs/inventory_notes.json.
# Neden veri, neden kod değil? (a) Python ürün yolu, ürüne bağlanmayan derleme
# hattının adını ANMAZ (tests/unit/test_rust_runtime_status.py); (b) kürasyonu
# kod değiştirmeden güncelleyebilmek denetlenebilirliği artırır.
NOTES_PATH = ROOT / "docs" / "inventory_notes.json"


def load_notes() -> dict:
    try:
        data = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"folder_descriptions": {}, "folder_highlights": {}, "section_notes": {}}
    return {
        "folder_descriptions": data.get("folder_descriptions", {}),
        "folder_highlights": data.get("folder_highlights", {}),
        "section_notes": data.get("section_notes", {}),
    }


NOTES = load_notes()
FOLDER_DESCRIPTIONS = NOTES["folder_descriptions"]
FOLDER_HIGHLIGHTS = NOTES["folder_highlights"]
SECTION_NOTES = NOTES["section_notes"]

TESTS_NOTE = "Test adları davranış sözleşmesidir: adı okuyunca neyin kilitlendiği anlaşılır."

# ── NOT DOSYASINDAKİ YER TUTUCULAR ──────────────────────────────────────────
# `docs/inventory_notes.json` ELLE SAYI TAŞIMAZ: {test_modulu} gibi yer tutucular
# aşağıdaki ölçümlerle doldurulur. Gerekçe: aynı sayı üç yerde (bu sayfa,
# inventory_notes.json, CHANGELOG) elle yazılınca üç farklı değere ayrışmıştı
# (ölçüldü 2026-10-14: 234 / 235 / 233). Sayı artık TEK KAYNAKTAN gelir.
_NOTES_TOKENS: dict[str, str] = {}


def fill_notes(text: str) -> str:
    """Not metnindeki {yer tutucuları} ÖLÇÜLMÜŞ değerlerle doldurur (elle sayı yasak)."""
    for anahtar, deger in _NOTES_TOKENS.items():
        text = text.replace("{" + anahtar + "}", deger)
    return text
ENV_NOTE = SECTION_NOTES.get("env", "")
CONFIG_NOTE = SECTION_NOTES.get("config", "")

# --------------------------------------------------------------------------- #
# 2) ÇIKARIM — içerikten otomatik açıklama
# --------------------------------------------------------------------------- #

def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


# İkili/arşiv uzantıları: "satır sayısı" bunlar için ANLAMSIZDIR. Ölçüldü
# (2026-10-14): `docs/pineal_envanter.zip` 4 MB'lık bir arşivken sayfada
# "14.965 satır" diye görünüyordu — yani sayı, okuyucuya sahte bir metin izlenimi
# veriyordu. Ayrıca bu satırlar `toplam satır` istatistiğini de şişiriyordu.
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".icns",
    ".jar", ".zip", ".gz", ".tar", ".woff", ".woff2", ".ttf", ".otf",
    ".pdf", ".so", ".dylib", ".dll", ".exe",
}


def is_binary_path(rel: str) -> bool:
    """Uzantıya göre metin değil mi? (İçerik taraması pahalı; uzantı deterministik.)"""
    return Path(rel).suffix.lower() in BINARY_SUFFIXES


def loc_of(path: Path) -> int:
    if is_binary_path(path.name):
        return 0          # satır sayılmaz: metin değil
    try:
        with path.open("rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def py_summary(path: Path) -> dict:
    src = read_text(path)
    out = {"desc": "", "symbols": [], "tests": [], "doc_src": ""}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    doc = ast.get_docstring(tree)
    if doc:
        # İlk iki paragraf: hem "ne yapar" hem "hangi sözleşmeyle yapar" görünsün.
        out["desc"] = first_para(doc, limit=620, paragraphs=2)
        out["doc_src"] = "modül docstring"
    classes, funcs = [], []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                out["tests"].append(node.name)
            elif not node.name.startswith("_"):
                funcs.append(node.name + "()")
    out["symbols"] = classes[:8] + funcs[:6]
    return out


def first_para(text: str, limit: int = 420, paragraphs: int = 1) -> str:
    """İlk anlamlı paragraf(lar). `paragraphs=2` özet + gerekçe satırını birlikte verir."""
    text = text.strip()
    picked = []
    for block in re.split(r"\n\s*\n", text):
        block = " ".join(block.split())
        if block and not block.startswith(("-", "*", "#", "•")):
            picked.append(block)
        if len(picked) >= paragraphs:
            break
    joined = " ".join(picked) or " ".join(text.split())
    return joined[:limit] + ("…" if len(joined) > limit else "")


def md_title(path: Path) -> str:
    src = read_text(path)
    if src.startswith("---"):
        fm = src.split("---", 2)
        if len(fm) >= 3:
            m = re.search(r"^description:\s*(.+)$", fm[1], re.M)
            if m:
                return m.group(1).strip().strip('"')
    for line in src.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return first_para(src, 160)


def front_matter(path: Path) -> dict:
    src = read_text(path)
    out = {}
    if src.startswith("---"):
        parts = src.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    out[k.strip()] = v.strip().strip('"')
    return out


def rust_summary(path: Path) -> str:
    src = read_text(path)
    docs = [l[3:].strip() for l in src.splitlines() if l.startswith("//!")]
    if docs:
        return first_para("\n".join(docs), 300)
    outer = [l[3:].strip() for l in src.splitlines() if l.lstrip().startswith("///")]
    if outer:
        return first_para("\n".join(outer[:6]), 300)
    return ""


def ts_summary(path: Path) -> str:
    src = read_text(path)
    blocks = re.findall(r"^(?://.*\n|/\*.*?\*/)+", src, re.S | re.M)
    if blocks:
        return first_para(blocks[0].replace("//", " "), 300)
    return ""


def ts_symbols(path: Path) -> list:
    src = read_text(path)
    names = re.findall(r"export\s+(?:async\s+)?(?:function|const|let|class|type|interface)\s+([A-Za-z_0-9]+)", src)
    return names[:10]


def svelte_summary(path: Path) -> str:
    src = read_text(path)
    for m in re.finditer(r"<!--(.*?)-->", src, re.S):
        body = m.group(1)
        if len(body.strip()) > 25:
            return first_para(body, 300)
    blocks = re.findall(r"/\*\*?(.*?)\*/", src, re.S)
    if blocks:
        return first_para(blocks[0], 300)
    return ""


def kt_summary(path: Path) -> str:
    src = read_text(path)
    blocks = re.findall(r"/\*\*(.*?)\*/", src, re.S)
    if blocks:
        return first_para(blocks[0].replace("*", " "), 300)
    comments = re.findall(r"^\s*//\s*(.+)$", src, re.M)
    if comments:
        return first_para("\n".join(comments[:4]), 300)
    return ""


def json_purpose(path: Path) -> str:
    try:
        data = json.loads(read_text(path))
    except (json.JSONDecodeError, ValueError):
        return ""
    if isinstance(data, dict):
        meta = data.get("_meta", {})
        if isinstance(meta, dict) and meta.get("purpose"):
            return first_para(str(meta["purpose"]), 400)
        keys = list(data.keys())[:10]
        return "JSON yapılandırma — üst düzey anahtarlar: " + ", ".join(keys)
    if isinstance(data, list):
        return f"JSON liste — {len(data)} kayıt"
    return ""


def yaml_comment(path: Path) -> str:
    src = read_text(path)
    for line in src.splitlines():
        if line.strip().startswith("#") and len(line.strip()) > 12:
            return line.strip().lstrip("# ").strip()
    return ""


def json_shape(path: Path) -> str:
    try:
        data = json.loads(read_text(path))
    except (json.JSONDecodeError, ValueError):
        return ""
    if isinstance(data, dict):
        return "Anahtarlar: " + ", ".join(list(data.keys())[:8])
    if isinstance(data, list):
        return f"Liste — {len(data)} kayıt"
    return ""


def auto_desc(path: str, p: Path) -> tuple:
    """(açıklama, kaynak) döner. Kaynak 'uydurulmadı' ilkesiyle etiketlenir."""
    ext = p.suffix.lower()
    if ext == ".py":
        info = py_summary(p)
        return (info["desc"], "docstring")
    if ext == ".md":
        return (md_title(p), "başlık/front-matter")
    if ext == ".rs":
        return (rust_summary(p), "//! belgesi")
    if ext in {".ts", ".js"}:
        return (ts_summary(p), "yorum bloğu")
    if ext == ".svelte":
        return (svelte_summary(p), "yorum bloğu")
    if ext in {".kt", ".kts", ".gradle"}:
        return (kt_summary(p), "KDoc/yorum")
    if ext == ".json":
        return (json_purpose(p) or json_shape(p), "_meta / anahtarlar")
    if ext in {".yaml", ".yml"}:
        return (yaml_comment(p), "yorum")
    return ("", "")


# --------------------------------------------------------------------------- #
# 3) DOSYA ENVANTERİ
# --------------------------------------------------------------------------- #

# ── TEST SAYISI: TEK KAYNAK ─────────────────────────────────────────────────
# "test modülü" = pytest'in TOPLADIĞI dosyalar = `tests/` altındaki `test_*.py`.
# `tests/` ağacındaki TÜM dosya sayısı AYRI ölçüdür (conftest.py gibi yardımcılar
# dâhil) ve ayrı etiketlenir. İkisini aynı adla yazmak "üç yerde üç sayı"
# kusurunu doğuruyordu (denetim 2026-10-14, bulgu 2): ölçüldü → 234 / 235 / 233.
# Tanım ARTIK BURADA yaşar; sayfa, not dosyası ve raporlar buradan beslenir.
TEST_MODULU_TANIMI = "tests/ altındaki test_*.py (pytest'in topladığı dosyalar)"


def tests_tree(entries: list) -> list:
    """`tests/` ağacındaki TÜM dosyalar (yardımcılar dâhil) — ikinci ölçü."""
    return [e for e in entries if e["path"].startswith("tests/")]


def canonical_test_modules(entries: list) -> list:
    """KANONİK ÖLÇÜM: `tests/` altındaki, dosya adı `test_` ile başlayan `.py` dosyaları."""
    return [
        e
        for e in tests_tree(entries)
        if e["path"].endswith(".py") and e["path"].rsplit("/", 1)[-1].startswith("test_")
    ]


class GitError(RuntimeError):
    """`git` sıfırdan farklı döndü: EKSİK VERİYLE GEÇERLİ GÖRÜNEN SAYFA ÜRETİLMEZ."""


def git(*args: str) -> str:
    """`git <args>` çalıştırır; **dönüş kodu denetlenir** ve hata AÇIKÇA yükseltilir.

    [DENETİM 2026-10-14] Eskiden yalnız `stdout` okunuyordu: `git` başarısız
    olduğunda (bozuk kullanıcı adı, eksik nesne, sınırlı ortam) çıktı BOŞ
    dönüyor ve üretici dosya listesini eksik alıp yine de "geçerli" görünen bir
    sayfa yazıyordu — yani envanter sessizce küçülebilirdi. Artık hata
    yükseltilir; `main()` bunu yakalayıp sayfayı HİÇ YAZMADAN döner.
    """
    # `core.quotepath=false`: ASCII dışı dosya adları kaçış dizisiyle değil, gerçek
    # UTF-8 adıyla döner. Ölçüldü (2026-10-14): sayfa, `"UX_Kullan\304\261labilirlik_
    # Raporu.md"` gibi OKUNMAZ bir adı dosya sanıyordu — yani dosya, gerçek adıyla
    # hiç listelenmiyordu.
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        ayrinti = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")[:300]
        raise GitError(
            f"git {' '.join(args)} başarısız (dönüş kodu {proc.returncode}): {ayrinti or '(ayrıntı yok)'}"
        )
    return proc.stdout.strip()


def area_of(path: str) -> str:
    """Dosya yolundan bölüm adı. Adlar, ayrık alanlar için yoldan TÜRETİLİR:
    böylece bu modül, ürüne bağlanmayan bir klasörün adını anmak zorunda kalmaz
    (kontrat: Python ürün yolu yalnız ÜRÜN yollarını adlandırır)."""
    if path.startswith("agent_core/agents/"):
        return "agent_core · ajanlar"
    if path.startswith("agent_core/services/"):
        return "agent_core · servisler"
    if path.startswith("agent_core/capabilities/"):
        return "agent_core · yetenek omurgası"
    if path.startswith("agent_core/engines/"):
        return "agent_core · motorlar"
    if path.startswith("agent_core/"):
        return "agent_core · çekirdek"
    if path.startswith("backend/"):
        return "backend · API"
    if path.startswith("tests/"):
        return "tests"
    if path.startswith("docs/") or (path.endswith(".md") and "/" not in path):
        return "docs · dokümanlar"
    if "/" in path:
        return path.split("/", 1)[0]          # kök seviye klasör adı (yoldan)
    return "kök / diğer"


ROOT_MD = set()


def build_entries() -> list:
    global ROOT_MD
    tracked = git("ls-files").splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").splitlines()
    #: [DENETİM 2026-10-14 · B16] TEK, DETERMİNİST sıra: eskiden `tracked +
    #: untracked` idi; yeni bir dosya commit'lendiği anda listeye alfabetik
    #: değil SONA ekleniyordu → sayfa içeriği yalnız `git add` yüzünden
    #: değişiyor ve `--check` "bayat" diyordu (CI kırmızısı; üretim yolu
    #: kirli ağaçta üretilip temiz ağaçta doğrulanıyordu). Sıra artık
    #: izleme durumundan BAĞIMSIZ: yalnız yola göre sıralanır.
    files = sorted(set(tracked + untracked))
    ROOT_MD = {f for f in files if f.endswith(".md") and "/" not in f}
    entries = []
    for rel in files:
        # ÖZ-REFERANS KİLİDİ: bu sayfanın kendi satır sayısı, sayfanın içeriğine
        # bağlıdır (üretim → satır sayısı değişir → sayfa değişir). Sayfa kendini
        # saymaz; aksi hâlde `--check` hiçbir zaman kararlı olmazdı.
        if rel == "docs/envanter.html":
            continue
        p = ROOT / rel
        entry = {
            "path": rel,
            "loc": loc_of(p),
            "area": area_of(rel),
            "ext": p.suffix.lower().lstrip(".") or "yok",
            "desc": "",
            "src": "",
            "symbols": [],
            "tests": [],
            "flags": [],
        }
        if rel in CATEGORY_A:
            entry["flags"].append("A")
        if rel in CATEGORY_B:
            entry["flags"].append("B")
        if rel in API_SPLIT:
            entry["flags"].append("api-split")
        if rel in NEW_FILES:
            entry["flags"].append("yeni")
        if rel.startswith("scripts/archive/"):
            entry["flags"].append("arşiv")
        if rel.startswith("tests/"):
            entry["flags"].append("test")
        if rel.startswith("docs/reports/") or rel.startswith("reports/"):
            entry["flags"].append("rapor")
        if rel.startswith("."):
            entry["flags"].append("gizli")

        if p.suffix.lower() == ".py":
            info = py_summary(p)
            entry.update({"desc": info["desc"], "src": info["doc_src"],
                          "symbols": info["symbols"], "tests": info["tests"]})
        if rel.startswith("skills/") and rel.endswith("SKILL.md"):
            entry["desc"] = md_title(p)  # front-matter açıklaması
            entry["src"] = "SKILL.md front-matter"
        elif rel.endswith(".md"):
            entry["desc"] = md_title(p)
            entry["src"] = "başlık"
        elif not entry["desc"]:
            d, s = auto_desc(rel, p)
            if d:
                entry.update({"desc": d, "src": s})
        if rel in CORE:
            entry.update({"desc": CORE[rel], "src": "elle (kürasyon)", "core": True})
        entries.append(entry)
    return entries


# --------------------------------------------------------------------------- #
# 4) .env.example ve config
# --------------------------------------------------------------------------- #

def env_groups() -> list:
    src = read_text(ROOT / ".env.example")
    groups, current = [], {"title": "Genel", "items": []}
    pending = []
    for line in src.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# ---") and stripped.endswith("---"):
            if current["items"] or current["title"] != "Genel":
                groups.append(current)
            title = stripped.strip("#- ").strip()
            current = {"title": title, "items": []}
            pending = []
            continue
        if stripped.startswith("#"):
            pending.append(stripped.lstrip("# ").strip())
            continue
        if "=" in line and not stripped.startswith("#"):
            name, value = line.split("=", 1)
            value = value.split("#")[0].strip()
            note = " ".join(p for p in pending if p)
            current["items"].append({
                "name": name.strip(),
                "value": value[:40],
                "note": re.sub(r"\s+", " ", note)[:600],
            })
            pending = []
        elif stripped:
            pending = []
    if current["items"]:
        groups.append(current)
    return groups


CONFIG_DESC = {
    "agent_tiers.json": "Ajan→tier NİYETİ (heavy/vision/simple/verify/jury). Tek okuyucu "
                        "`LLMGateway.effective_routing_snapshot()`; okuyucusu olmayan tier "
                        "yasaktır (13. gölge olmasın diye okuyucu + kapsam testi aynı commit'te).",
    "task_routing.json": "Ajan→sıralı model anahtarı zincirleri. `AGENT_CHAINS` üzerine DELTA'dır "
                         "(yalnız sapan ajanlar yazılır). Bozuk giriş fail-closed: ajan None'a düşer, "
                         "kısmi amputasyon yok.",
    "provider_catalog.json": "Sağlayıcı kataloğu: uçlar, fiyatlar, yetenekler, model aileleri. "
                             "Fiyatı bilinmeyen model için ücretli canlı çağrı varsayılan olarak "
                             "KAPALIDIR (`PINEAL_ALLOW_UNPRICED_MODELS=0`).",
    "decision_config.yaml": "Karar ve belirsizlik motoru eşikleri: `min_data_score`, "
                            "`min_llm_confidence`, ajan bazlı ağırlık/timeout değerleri. "
                            "Kod içine gömülü eşik yoktur.",
    "rtk_policy.json": "RTK (token sıkıştırma) bypass politikası — config-driven, fail-open. "
                       "Bu dosya Pineal'in genel fail-closed doktrininden BİLEREK sapan tek yerdir "
                       "(adli veri bütünlüğü riski taşımaz).",
    "router.example.json": "UnifiedRouter için örnek yapılandırma (`PINEAL_ROUTER_CONFIG`). "
                            "Boş bırakılırsa katalog + env anahtarlarından otomatik runtime kurulur.",
}


def config_rows() -> list:
    rows = []
    for p in sorted((ROOT / "config").iterdir()):
        desc = CONFIG_DESC.get(p.name, "")
        if not desc:
            desc = json_purpose(p) or yaml_comment(p)
        rows.append({"name": p.name, "loc": loc_of(p), "desc": desc,
                     "extra": (json_shape(p) if p.suffix == ".json" else "")})
    return rows


# --------------------------------------------------------------------------- #
# 5) HTML
# --------------------------------------------------------------------------- #

def esc(t: str) -> str:
    return html.escape(t or "", quote=True)


CSS = """
:root{--bg:#0b0d10;--panel:#12161b;--panel2:#171c23;--line:#232a33;--tx:#e6ecf3;--dim:#93a1b1;
--acc:#6ee7b7;--acc2:#7dd3fc;--warn:#fbbf24;--bad:#fb7185;--ok:#34d399}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--acc2);text-decoration:none}
a:hover{text-decoration:underline}
header{padding:34px 26px 22px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,#0e1319,#0b0d10)}
h1{margin:0 0 6px;font-size:26px;letter-spacing:.2px}
h2{margin:34px 0 10px;font-size:19px;border-left:3px solid var(--acc);padding-left:10px}
h3{margin:22px 0 8px;font-size:16px;color:var(--acc2)}
.sub{color:var(--dim);font-size:13.5px}
.wrap{padding:0 26px 80px;max-width:1500px;margin:0 auto}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 4px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:9px 13px;min-width:120px}
.stat b{display:block;font-size:19px}
.stat span{color:var(--dim);font-size:12px}
.bar{position:sticky;top:0;z-index:9;background:rgba(11,13,16,.96);border-bottom:1px solid var(--line);
padding:11px 26px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;backdrop-filter:blur(6px)}
input[type=search]{flex:1;min-width:230px;background:var(--panel2);border:1px solid var(--line);
color:var(--tx);border-radius:8px;padding:9px 12px;font-size:14px}
.chip{border:1px solid var(--line);background:var(--panel);color:var(--dim);border-radius:999px;
padding:5px 11px;font-size:12.5px;cursor:pointer;user-select:none}
.chip.on{color:#06120e;background:var(--acc);border-color:var(--acc);font-weight:600}
.counter{color:var(--dim);font-size:12.5px;margin-left:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;vertical-align:top;padding:8px 9px;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.4px;position:sticky;top:52px;background:var(--bg)}
tr:hover td{background:#10151b}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px}
.pth{word-break:break-all}
td.loc{text-align:right;color:var(--dim);white-space:nowrap}
.tag{display:inline-block;border-radius:5px;padding:1px 6px;font-size:11px;margin:0 4px 2px 0;border:1px solid var(--line);color:var(--dim)}
.tag.A{color:#06120e;background:var(--acc);border-color:var(--acc);font-weight:700}
.tag.B{color:#0b0d10;background:var(--acc2);border-color:var(--acc2);font-weight:700}
.tag.api-split{color:#1b1405;background:var(--warn);border-color:var(--warn);font-weight:700}
.tag.rapor{color:#0d0f13;background:#c4b5fd;border-color:#c4b5fd}
.tag.arşiv{color:var(--dim)}
.tag.gizli{color:var(--dim)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:12px 0}
.card.core{border-color:#2b6b56;background:linear-gradient(180deg,#111a17,#12161b)}
.card h4{margin:0 0 6px;font-size:15.5px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px}
.sym{color:var(--dim);font-size:12.5px;margin-top:6px}
.src{color:#5f6b78;font-size:11.5px}
details{margin:6px 0;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
summary{cursor:pointer;padding:10px 13px;font-size:14px}
details .inner{padding:0 13px 12px}
.note{background:#0f1512;border:1px solid #24503f;border-radius:10px;padding:12px 14px;color:#cfe9df;font-size:13.5px}
.warn{background:#191308;border-color:#5c4715;color:#f6e2b6}
.pill{display:inline-block;background:var(--panel2);border:1px solid var(--line);border-radius:999px;padding:2px 9px;margin:2px 4px 2px 0;font-size:12px;color:var(--dim)}
footer{color:var(--dim);font-size:12.5px;padding:26px;border-top:1px solid var(--line)}
.hidden{display:none!important}
ul.tight{margin:6px 0 0 18px;padding:0}
ul.tight li{margin:2px 0;color:var(--dim);font-size:13px}
"""

JS = """
const q=document.getElementById('q'),counter=document.getElementById('counter');
const chips=[...document.querySelectorAll('.chip[data-flag]')];
function apply(){
  const needle=q.value.trim().toLowerCase();
  const active=chips.filter(c=>c.classList.contains('on')).map(c=>c.dataset.flag);
  let shown=0;
  document.querySelectorAll('tbody tr').forEach(tr=>{
    const hay=(tr.dataset.hay||'').toLowerCase();
    const flags=(tr.dataset.flags||'').split(',');
    const okText=!needle||hay.includes(needle);
    const okFlag=active.every(f=>flags.includes(f));
    const vis=okText&&okFlag;
    tr.classList.toggle('hidden',!vis);
    if(vis)shown++;
  });
  document.querySelectorAll('details.folder').forEach(d=>{
    const rows=d.querySelectorAll('tbody tr');
    const vis=[...rows].filter(r=>!r.classList.contains('hidden')).length;
    d.classList.toggle('hidden',vis===0&&needle.length>0);
    const badge=d.querySelector('.fcount'); if(badge)badge.textContent=vis+' dosya';
  });
  counter.textContent=shown+' dosya görünüyor';
}
q.addEventListener('input',apply);
chips.forEach(c=>c.addEventListener('click',()=>{c.classList.toggle('on');apply();}));
document.getElementById('openall').addEventListener('click',()=>document.querySelectorAll('details').forEach(d=>d.open=true));
document.getElementById('closeall').addEventListener('click',()=>document.querySelectorAll('details').forEach(d=>d.open=false));
apply();
"""


def row(entry: dict) -> str:
    flags = entry["flags"]
    tags = "".join(f'<span class="tag {esc(f)}">{esc(f.upper())}</span>' for f in flags)
    sym = ""
    if entry["symbols"]:
        sym = '<div class="sym">semboller: <span class="mono">' + esc(", ".join(entry["symbols"])) + "</span></div>"
    tests = ""
    if entry["tests"]:
        shown = entry["tests"][:6]
        tests = ('<div class="sym">kilitlediği davranışlar: <span class="mono">'
                 + esc(" · ".join(t.replace("test_", "") for t in shown))
                 + (" …" if len(entry["tests"]) > len(shown) else "") + "</span></div>")
    desc = esc(entry["desc"]) or '<span class="src">açıklama yok (ad + semboller)</span>'
    src = f'<div class="src">{esc(entry["src"])}</div>' if entry["src"] else ""
    hay = " ".join([entry["path"], entry["desc"], " ".join(entry["symbols"]),
                    " ".join(entry["tests"]), entry["area"]])
    return (f'<tr data-hay="{esc(hay)}" data-flags="{esc(",".join(flags))}">'
            f'<td class="pth"><span class="mono">{esc(entry["path"])}</span>{src}</td>'
            f'<td class="loc">{"ikili" if is_binary_path(entry["path"]) else (entry["loc"] or "")}</td>'
            f'<td>{tags}</td>'
            f'<td>{desc}{sym}{tests}</td></tr>')


def table(entries: list, headers=("Dosya", "Satır", "Etiket", "Açıklama")) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join(row(e) for e in entries)
    return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def folder_block(name: str, entries: list) -> str:
    desc = fill_notes(FOLDER_DESCRIPTIONS.get(name, ""))
    highlight = fill_notes(FOLDER_HIGHLIGHTS.get(name, ""))
    hint = f'<span class="src">{esc(highlight)}</span><br>' if highlight else ""
    rows = table(entries)
    return (f'<details class="folder" open><summary><b>{esc(name)}</b> — {esc(desc[:150])} '
            f'<span class="pill fcount">{len(entries)} dosya</span></summary>'
            f'<div class="inner">{hint}{rows}</div></details>')


def build_html(entries: list) -> str:
    by_path = {e["path"]: e for e in entries}
    py = [e for e in entries if e["path"].endswith(".py")]
    py_loc = sum(e["loc"] for e in py)
    total_loc = sum(e["loc"] for e in entries)
    # Künye DAMGASI — KAYNAKTAN türetilir, git durumundan DEĞİL.
    # Neden: git hash/tarih kendine referanslıdır (sayfa, içine gömüldüğü commit'ten
    # önce üretilir; commit atılınca hash değişir → CI'daki `--check` her seferinde
    # yanlış alarm verirdi). Bunun yerine sayfa; sürümü (VERSION) ve ÜRETİCİNİN kendi
    # içerik imzasını bildirir: ikisi de dosya içeriğinden gelir, commit'ten bağımsızdır.
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").is_file() else "?"
    uretici = (ROOT / "scripts" / "generate_inventory_page.py")
    imza = (
        hashlib.sha256(uretici.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:12]
        if uretici.is_file()
        else "?"
    )

    cat_a = [by_path[p] for p in CATEGORY_A if p in by_path]
    cat_b = [by_path[p] for p in CATEGORY_B if p in by_path]
    cat_a_missing = [e["path"] for e in cat_a if not e["desc"]]
    cat_b_missing = [e["path"] for e in cat_b if not e["desc"]]
    core = [by_path[p] for p in CORE if p in by_path]
    # ── TEST SAYISI: TEK KAYNAK (tanım yukarıda: canonical_test_modules) ────
    tests_tree_entries = tests_tree(entries)
    tests = canonical_test_modules(entries)
    test_no_doc = len([e for e in tests if not e["desc"]])
    docs = [e for e in entries if e["area"] == "dokümanlar"]

    # Not dosyası yer tutucuları (tek kaynaktan gelen ölçümler)
    _NOTES_TOKENS.update({
        "test_modulu": f"{len(tests):,}".replace(",", "."),
        "tests_agaci": f"{len(tests_tree_entries):,}".replace(",", "."),
        "izlenen_dosya": f"{len(entries):,}".replace(",", "."),
        "python_dosyasi": f"{len(py):,}".replace(",", "."),
        "ayar_sayisi": f"{sum(len(g['items']) for g in env_groups()):,}".replace(",", "."),
    })

    # ── alan alan TEK listeleme: her dosya sayfada TAM BİR KEZ satır olur ──
    # Bölüm sırası VERİDEN gelir (docs/inventory_notes.json → folder_descriptions).
    AREA_ORDER = list(FOLDER_DESCRIPTIONS)
    by_area = {a: [] for a in AREA_ORDER}
    for e in entries:
        by_area.setdefault(e["area"], []).append(e)
    ordered = AREA_ORDER + [a for a in by_area if a not in FOLDER_DESCRIPTIONS]
    blocks = "".join(folder_block(a, by_area.get(a, [])) for a in ordered if by_area.get(a))

    # ── uç nokta envanteri ──
    api_src = read_text(ROOT / "backend/api.py")
    endpoints = re.findall(r'@app\.(get|post|put|delete|patch|websocket)\("([^"]+)"', api_src)
    lang_src = read_text(ROOT / "backend/routes/language.py")
    endpoints += re.findall(r'^\s*@app\.(get|post|patch|delete)\("([^"]+)"', lang_src, re.M)
    company_src = read_text(ROOT / "backend/routes/company.py")
    endpoints += re.findall(r'^\s*@app\.(get|post|patch|delete)\("([^"]+)"', company_src, re.M)
    speech_audio_src = read_text(ROOT / "backend/routes/speech_audio.py")
    endpoints += re.findall(r'^\s*@router\.(get|post|patch|delete)\("([^"]+)"', speech_audio_src, re.M)
    ep_table = "".join(
        f'<tr data-hay="{esc(m + " " + p + " endpoint")}" data-flags="endpoint">'
        f'<td class="mono">{esc(m.upper())}</td><td class="pth mono">{esc(p)}</td></tr>'
        for m, p in sorted(endpoints, key=lambda x: x[1])
    )

    # ── .env.example ──
    env_html = []
    for group in env_groups():
        items = "".join(
            f'<tr data-hay="{esc(i["name"] + " " + i["note"] + " env")}" data-flags="env">'
            f'<td class="mono pth">{esc(i["name"])}</td>'
            f'<td class="mono">{esc(i["value"]) or "<i>boş</i>"}</td>'
            f'<td>{esc(i["note"]) or "<span class=src>yorum yok</span>"}</td></tr>'
            for i in group["items"]
        )
        env_html.append(
            f'<h3>{esc(group["title"])} <span class="pill">{len(group["items"])} ayar</span></h3>'
            f'<table><thead><tr><th>Değişken</th><th>Örnek değer</th>'
            f'<th>Ne işe yarar (dosyadaki yorum)</th></tr></thead><tbody>{items}</tbody></table>'
        )

    cfg = "".join(
        f'<tr data-hay="{esc(r["name"] + " " + r["desc"] + " config")}" data-flags="config">'
        f'<td class="mono pth">config/{esc(r["name"])}</td><td class="loc">{r["loc"]}</td>'
        f'<td>{esc(r["desc"])}<div class="src">{esc(r["extra"])}</div></td></tr>'
        for r in config_rows()
    )

    cards = ""
    for e in core:
        cards += (f'<div class="card core"><h4><span class="mono">{esc(e["path"])}</span> '
                  f'<span class="pill">{e["loc"]} satır</span></h4>'
                  f'<div>{esc(e["desc"])}</div></div>')

    def path_list(paths: list) -> str:
        return "".join(f'<li><span class="mono">{esc(p)}</span></li>' for p in paths)

    html_doc = f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PINEAL-HERETIC — Depo Envanteri</title>
<style>{CSS}</style></head>
<body>
<header>
  <h1>PINEAL-HERETIC — Depo Envanteri</h1>
  <div class="sub">Üretim künyesi: sürüm <code>{esc(version)}</code> ·
   üretici imzası <code>{esc(imza)}</code> · kaynak: <code>git ls-files</code> +
   AST + dosya başı açıklamaları</div>
  <div class="stats">
    <div class="stat"><b>{len(entries)}</b><span>izlenen dosya</span></div>
    <div class="stat"><b>{len(py)}</b><span>Python dosyası</span></div>
    <div class="stat"><b>{py_loc:,}</b><span>Python satırı</span></div>
    <div class="stat"><b>{total_loc:,}</b><span>toplam satır</span></div>
    <div class="stat"><b>{len(tests)}</b><span title="tanım: tests/ altındaki test_*.py — pytest'in topladığı dosyalar. tests/ ağacında toplam {len(tests_tree_entries)} dosya var (conftest.py gibi yardımcılar dâhil).">test modülü</span></div>
    <div class="stat"><b>{len(by_area.get("agent_core · ajanlar", []))}</b><span>ajan modülü</span></div>
    <div class="stat"><b>{len(by_area.get("agent_core · servisler", []))}</b><span>servis modülü</span></div>
    <div class="stat"><b>{sum(len(g["items"]) for g in env_groups())}</b><span>.env ayarı</span></div>
    <div class="stat"><b>{len(endpoints)}</b><span>uç nokta</span></div>
  </div>
</header>
<div class="bar">
  <input id="q" type="search" placeholder="Dosya, sembol, davranış ara… (örn. task_executor, bütçe, quote_guard, kasa)">
  <span class="chip" data-flag="A">A · açıklaması yoktu</span>
  <span class="chip" data-flag="B">B · envanterde yoktu</span>
  <span class="chip" data-flag="api-split">API ayrıştırma</span>
  <span class="chip" data-flag="yeni">yeni modül</span>
  <span class="chip" data-flag="test">test</span>
  <span class="chip" data-flag="rapor">rapor</span>
  <span class="chip" data-flag="arşiv">arşiv</span>
  <span class="chip" data-flag="gizli">gizli dosya</span>
  <button class="chip" id="openall">hepsini aç</button>
  <button class="chip" id="closeall">hepsini kapat</button>
  <span class="counter" id="counter"></span>
</div>
<div class="wrap">

<div class="note">
  <b>Bu sayfa üç boşluğu kaynaktan doğrulayarak kapatır.</b> Her dosya aşağıda <b>tam bir kez</b>
  görünür; etiketlerle süzülür (arama kutusu klasörlerin içini de süzer):
  <ul class="tight">
    <li><b>A · {len(cat_a)} dosyanın adı vardı, açıklaması yoktu</b> →
        {len(cat_a) - len(cat_a_missing)}/{len(cat_a)} dosyaya modül docstring'i yazıldı;
        sayfa açıklamayı artık docstring'den okuyor.
        <span class="src">{("eksik: " + ", ".join(cat_a_missing)) if cat_a_missing else "doğrulandı: eksik yok"}</span></li>
    <li><b>B · {len(cat_b)} Python dosyası envantere hiç girmemişti</b> → sistemin çekirdeği
        (<span class="mono">agent_core/task_executor.py</span>,
        <span class="mono">backend/api.py</span>) dâhil tamamı listeli ve açıklamalı.
        <span class="src">{("eksik: " + ", ".join(cat_b_missing)) if cat_b_missing else "doğrulandı: hepsi açıklamalı"}</span></li>
    <li><b>C · klasör envanteri:</b>
        {' · '.join(f"{area}: {len(by_area.get(area, []))}" for area in FOLDER_DESCRIPTIONS if by_area.get(area))}
        → klasör klasör açıldı; {len(tests)} test modülü, {len(docs)} doküman,
        <code>config/*</code> içeriği ve {sum(len(g["items"]) for g in env_groups())} ayarın tek tek anlamı yazıldı.</li>
  </ul>
</div>

<h2 id="cekirdek">Sistemin çekirdeği — en kritik dört dosya</h2>
<div class="note">Bunlar olmadan ne bir görev koşar ne bir kanıt mühürlenir. Sayfanın en zayıf
kaldığı yer burasıydı; artık hepsi açıklamalı, tek tek ve aşağıdaki listelerde de etiketli.</div>
{cards}

<h2 id="dogrulama">Doğrulama — bu sayfa nasıl güncel tutulur?</h2>
<div class="note">Sayfa elle düzenlenmez: <code>git ls-files</code> + AST'den üretilir;
<code>--check</code> modu bayatlamayı yakalar (fark varsa sıfırdan farklı çıkış kodu).</div>
<table><thead><tr><th>Ne</th><th>Komut</th></tr></thead><tbody>
<tr><td>Sayfayı üret</td><td class="mono pth">python scripts/generate_inventory_page.py</td></tr>
<tr><td>Bayat mı? (CI kapısı)</td><td class="mono pth">python scripts/generate_inventory_page.py --check</td></tr>
<tr><td>Tüm testler</td><td class="mono pth">pytest -q</td></tr>
<tr><td>Monolit tavanı</td><td class="mono pth">pytest tests/unit/test_api_monolith_ratchet.py -q</td></tr>
</tbody></table>
<div class="note warn" style="margin-top:10px">
  Bilinen tek eksik: {test_no_doc} test modülünde modül docstring yok. Sayfa bunlar için docstring
  yerine test ADLARINI listeler (bu depoda test adları davranış cümlesidir, ör.
  <span class="mono">pricing_guard_denies_unknown_price</span>).
</div>

<h2 id="kategoriler">A ve B listeleri — tam adres</h2>
<details><summary><b>A · açıklaması yoktu ({len(cat_a)} dosya)</b>
  <span class="pill">aşağıdaki listelerde “A” etiketiyle işaretli</span></summary>
  <div class="inner"><ul class="tight">{path_list([e["path"] for e in cat_a])}</ul></div></details>
<details><summary><b>B · envanterde hiç yoktu ({len(cat_b)} dosya)</b>
  <span class="pill">aşağıdaki listelerde “B” etiketiyle işaretli</span></summary>
  <div class="inner"><ul class="tight">{path_list([e["path"] for e in cat_b])}</ul></div></details>
<details><summary><b>Bu turda eklenen modüller</b> <span class="pill">API-BÖLME 2/3</span></summary>
  <div class="inner">
    <p><b>API-BÖLME 2</b> · <span class="mono">backend/routes/language.py</span> —
    {esc(NEW_FILES["backend/routes/language.py"])}</p>
    <p>Gerekçe: <span class="mono">backend/api.py</span> tam tavanda (6.000 satır) duruyordu;
    dosyaya açıklama (modül docstring'i) eklemek bile ratchet testini kırıyordu. Depo kuralı
    "yeni satır yerine modül çıkar" olduğu için <span class="mono">/api/language/*</span> üç ucu
    ayrı modüle taşındı: <b>6.000 → 5.916 satır</b>, tavan da 5.916'ya DÜŞÜRÜLDÜ
    (<span class="mono">tests/unit/test_api_monolith_ratchet.py</span>). Uç gövdeleri değişmedi;
    <span class="mono">backend/api.py</span> payload modellerini yeniden ihraç eder.</p>
    <p><b>API-BÖLME 3</b> · <span class="mono">backend/routes/speech_audio.py</span> —
    TTS indirme ucunun ayrı modülü. Sadece içerik-hash'li tamamlanmış WAV'lar sunulur;
    <span class="mono">private, no-store</span> başlığı, varsayılan 1 saat TTL, 64 MiB önbellek
    tavanı ve periyodik temizleyici vardır. STT ham sesleri normal işlemde hemen, crash artıkları
    beş dakika sonra silinir.</p>
  </div></details>

<h2 id="c">C · Klasör klasör tam envanter</h2>
<div class="note">Her satır: dosya yolu · satır · etiketler · açıklama · ana semboller
· (test ise) kilitlediği davranışlar. Açıklamanın kaynağı satırın altında yazar
(<span class="mono">modül docstring</span>, <span class="mono">elle (kürasyon)</span>,
<span class="mono">SKILL.md front-matter</span> …) — uydurulmuş açıklama yoktur.</div>
{blocks}

<h2 id="endpoints">Uç noktalar (dekoratörlerden sayıldı)</h2>
<div class="note">Gerçek <span class="mono">@app.*</span> / <span class="mono">@router.*</span> dekoratörlerinden sayılmıştır — elle
yazılmadı. Toplam <b>{len(endpoints)}</b> uç.</div>
<details open><summary><b>HTTP + WS uçları</b> <span class="pill">{len(endpoints)} uç</span></summary>
<div class="inner"><table><thead><tr><th>Yöntem</th><th>Yol</th></tr></thead>
<tbody>{ep_table}</tbody></table></div></details>

<h2 id="env">.env.example — {sum(len(g["items"]) for g in env_groups())} ayarın tek tek anlamı</h2>
<div class="note">{ENV_NOTE}</div>
{''.join(env_html)}

<h2 id="config">config/* — çalışma zamanı yapılandırması</h2>
<div class="note">{CONFIG_NOTE}</div>
<table><thead><tr><th>Dosya</th><th>Satır</th><th>Açıklama</th></tr></thead>
<tbody>{cfg}</tbody></table>

<footer>
  Üretici: <code>scripts/generate_inventory_page.py</code> · bayatlama denetimi:
  <code>python scripts/generate_inventory_page.py --check</code> · tüm satır/açıklama verisi
  <code>git ls-files</code> + AST'den okunur, elle sayı girilmez.<br>
  Bu sayfanın kendisi (<span class="mono">docs/envanter.html</span>) envanter dışıdır: kendi satır
  sayısı sayfanın içeriğine bağlıdır, sayılsaydı <span class="mono">--check</span> hiç kararlı olamazdı.
</footer>
</div>
<script>{JS}</script>
</body></html>
"""
    return html_doc


def main() -> int:
    parser = argparse.ArgumentParser(description="docs/envanter.html üretir")
    parser.add_argument("--check", action="store_true", help="bayat mı? (farklıysa 1 döner)")
    args = parser.parse_args()

    # [DENETİM 2026-10-14] git hatası sessizce geçmez: eksik dosya listesiyle
    # "geçerli" görünen sayfa üretmektense hiç üretmemek doğrudur.
    try:
        entries = build_entries()
        page = build_html(entries)
    except GitError as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        print("Envanter ÜRETİLMEDİ (eksik veriyle geçerli görünen sayfa yazılmaz).", file=sys.stderr)
        return 2

    if args.check:
        current = read_text(OUT)
        if current != page:
            print("BAYAT: docs/envanter.html yeniden üretilmeli "
                  "(python scripts/generate_inventory_page.py)", file=sys.stderr)
            return 1
        print("GÜNCEL: docs/envanter.html kaynakla uyumlu")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8", newline="\n")
    missing = [e["path"] for e in entries if e["path"].endswith(".py") and not e["desc"]]
    print(f"yazıldı: {OUT} ({len(page)/1024:.0f} KB) · "
          f"{len(entries)} dosya · test modülü: {_NOTES_TOKENS.get('test_modulu', '?')} "
          f"({TEST_MODULU_TANIMI}) · açıklamasız py: {len(missing)}")
    if missing:
        print("  açıklamasız:", ", ".join(missing[:10]), "…" if len(missing) > 10 else "")
    print("sha256:", hashlib.sha256(page.encode()).hexdigest()[:16], "· ortam:", os.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
