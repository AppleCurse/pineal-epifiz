"""[DENETİM] Her HTTP ucunun çağrı yeri ölçülür — README tablosuyla aynı sayım.

README'nin kanıt tablosundaki "Ölü uç yok" satırı eskiden 68/30/38 diyordu ve
satırın kilitli olduğunu iddia ettiği test (`test_no_http_endpoint_is_orphaned`)
hiç var olmadı. Bu test o boşluğu kapatır:

  * benzersiz yol kümesi `backend.api.app.routes`'tan çıkarılır
    (`/api`, `/v1`, `/health` — `test_readme_claims.py` ile aynı filtre),
  * her yolun UI/edge kaynaklarında (`frontend/src`, `functions`) ve
    testlerde (`tests/`) geçip geçmediğine bakılır,
  * README'deki dört sayı (toplam / UI / test / çağrı yeri yok) kilitlenir;
    çağrı yeri olmayan uçların TAM LİSTESİ de dondurulur.

Yöntem: `{param}` yer tutucuları somut bir yol parçasıyla (`[^/]+`) ya da
JS şablonuyla (`${...}`) eşleşir; böylece `/api/memory/ada` çağrısı
`/api/memory/{target}` yoluna sayılır.

Bu testin kendisi tarama dışıdır — yoksa beklenen yetim listesi kendi
metninden "çağrı" sayılırdı.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"

#: README'deki uç çağrı yerleri satırının kilitli biçimi.
_ROW_RE = re.compile(
    r"(\d+) benzersiz HTTP yolu: \*\*(\d+)\*\*'ü UI/edge worker'dan, "
    r"\*\*(\d+)\*\*'si testlerden çağrılıyor; \*\*(\d+)\*\*'ünün çağrı yeri yok"
)

#: Bu dosya tarama dışıdır (bkz. modül docstring'i).
_SELF = Path(__file__).resolve()

_UI_GLOBS = (
    "frontend/src/**/*.svelte",
    "frontend/src/**/*.ts",
    "functions/**/*.ts",
    "worker.ts",
)
_TEST_GLOBS = ("tests/**/*.py",)


def _unique_paths() -> list[str]:
    """Uygulamanın gerçekten kayıtlı benzersiz HTTP yolları."""
    from backend.api import app

    paths = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api") or path.startswith("/v1") or path == "/health":
            paths.add(path)
    return sorted(paths)


def _read_many(globs: tuple[str, ...]) -> str:
    chunks = []
    for pattern in globs:
        for candidate in sorted(REPO_ROOT.glob(pattern)):
            if not candidate.is_file() or candidate.resolve() == _SELF:
                continue
            chunks.append(candidate.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def _is_referenced(path: str, blob: str) -> bool:
    """Yol, kaynaklarda somut çağrı olarak geçiyor mu?"""
    pattern = re.escape(path)
    pattern = re.sub(r"\\\{[^}]*\\\}", r"(?:[^/\"'?]+|\\$\\{[^}]+\\})", pattern)
    return re.search(pattern, blob) is not None


def _partition() -> tuple[list[str], set[str], set[str], list[str]]:
    paths = _unique_paths()
    ui_blob = _read_many(_UI_GLOBS)
    test_blob = _read_many(_TEST_GLOBS)
    ui_ref = {p for p in paths if _is_referenced(p, ui_blob)}
    test_ref = {p for p in paths if _is_referenced(p, test_blob)}
    orphans = sorted(set(paths) - ui_ref - test_ref)
    return paths, ui_ref, test_ref, orphans


def test_http_endpoint_call_sites_match_the_readme_table():
    """README'nin çağrı yeri tablosu = canlı ölçüm (toplam/UI/test/yetim)."""
    paths, ui_ref, test_ref, orphans = _partition()
    readme = README.read_text(encoding="utf-8")
    match = _ROW_RE.search(readme)
    assert match, "README'de uç çağrı yerleri satırı kilitli biçimde yok"
    claimed = tuple(int(g) for g in match.groups())
    measured = (len(paths), len(ui_ref), len(test_ref), len(orphans))
    assert claimed == measured, (
        f"README çağrı yeri tablosu {claimed} diyor, ölçüm {measured} — "
        "tablo ya da uç kümesi değişti; ikisini birlikte güncelle"
    )


def test_orphan_endpoints_are_exactly_the_documented_ones():
    """Çağrı yeri olmayan uçların listesi dondurulur — sessizce büyümez."""
    _, _, _, orphans = _partition()
    assert orphans == [
        "/api/tasks/{task_id}/changes",
        "/api/vault/lock",
        "/api/vault/unlock",
    ], f"çağrı yeri olmayan uçlar değişti: {orphans}"
