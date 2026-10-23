"""Kapı arkasındaki yeteneklerin PAKETLERİ gerçekten imaja giriyor mu?

[Neden bu test var — 2026-10-23 ölçümü]
`requirements.lock` yalnız `requirements.txt` + `requirements-osint.txt`
ağacından üretilmişti. `requirements-retina.txt` içindeki trafilatura,
scrapling, browserforge, twscrape ve instagrapi HİÇBİR yerde kurulmuyordu.
Sonuç: operatör `ENABLE_SCRAPLING=true` (ya da `ENABLE_X_SENSOR=true`,
`ENABLE_IG_SECONDARY=true`) yaptığında yetenek `available=false` +
`dependency_missing:<paket>` dönüyordu — kapı açık, motor yok. Bu test
"kapı açık ama paket yok" durumunun sessizce geri gelmesini engeller.

Sınıflandırma (uydurma yok — her satır koddan okunur):
  * ``LOCK``     → gereksinim `requirements.lock` içinde (Dockerfile kurar)
  * ``EXTRAS``   → ayrı gereksinim dosyasında (Dockerfile AYNI adımda kurmalı)
  * ``EXTERNAL`` → Python paketi değil (harici CLI): imaj içinde kurulmaz,
                   operatör `PINEAL_*_CMD` ile yol verir → kabul.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: Kodun gerçekten aradığı modüller (`_module_available(...)`) →
#: onları sağlayan dağıtım adı ve kaynağı.
DEPENDENCIES = {
    # capabilities/adapters_web.py
    "trafilatura": ("trafilatura", "EXTRAS"),
    "scrapling": ("scrapling", "EXTRAS"),
    "crawl4ai": ("crawl4ai", "LOCK"),
    # capabilities/adapters_sensors.py
    "twscrape": ("twscrape", "EXTRAS"),
    "instagrapi": ("instagrapi", "EXTRAS"),
    # capabilities/adapters_osint.py
    "socid_extractor": ("socid-extractor", "LOCK"),
    "maigret": ("maigret", "LOCK"),
    "holehe": ("holehe", "LOCK"),
    # harici CLI (Python paketi değil)
    "agent-reach": ("agent-reach", "EXTERNAL"),
    "piper": ("piper", "EXTERNAL"),
}

_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9_.-]+)")


def _requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    if not path.exists():
        return names
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = _REQ_NAME.match(line)
        if m:
            names.add(m.group(1).lower().replace("_", "-"))
    return names


@pytest.fixture(scope="module")
def dockerfile() -> str:
    return (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_dependency_scan_covers_every_capability_module():
    """Bu tablo koddaki her `_module_available(...)` çağrısını kapsar.

    Yeni bir yetenek eklendiğinde test sessizce eski kalmasın.
    """
    found: set[str] = set()
    for path in (ROOT / "agent_core" / "capabilities").glob("*.py"):
        for mod in re.findall(r'_module_available\("([A-Za-z0-9_.]+)"\)', path.read_text(encoding="utf-8")):
            # Alt modül kontrolü (`crawl4ai.markdown_generation_strategy`)
            # kök dağıtımın (`crawl4ai`) varlığını sınar.
            found.add(mod.split(".")[0])
    known = set(DEPENDENCIES)
    unknown = {m for m in found if m not in known}
    assert not unknown, f"Sınıflandırılmamış yetenek bağımlılığı: {sorted(unknown)}"


#: Harici bir CLI'ın operatör tarafından işaretlendiği env değişkeni.
EXTERNAL_ENV = {
    "agent-reach": "PINEAL_AGENT_REACH_CMD",
    "piper": "PINEAL_PIPER_MODEL",
}


@pytest.mark.parametrize(
    "module,dist,kind",
    [(m, d, k) for m, (d, k) in sorted(DEPENDENCIES.items())],
    ids=sorted(DEPENDENCIES),
)
def test_dependency_is_installable_in_the_image(module, dist, kind, dockerfile):
    if kind == "EXTERNAL":
        # Harici CLI imaja gömülmez; kapı makine-okunur sebep bildirir ve
        # operatör yolu env ile verir. Env adı kodda GERÇEKTEN geçmeli.
        env_name = EXTERNAL_ENV[module]
        sources = "\n".join(
            p.read_text(encoding="utf-8")
            for p in (ROOT / "agent_core" / "capabilities").glob("*.py")
        )
        assert env_name in sources, f"{module} için operatör env'i ({env_name}) kodda yok"
        return

    if kind == "LOCK":
        assert dist.lower() in _requirement_names(ROOT / "requirements.lock"), (
            f"{dist} requirements.lock içinde değil — imajda kurulmaz"
        )
        assert "-r requirements.lock" in dockerfile
        return

    # EXTRAS: paket ayrı dosyada; Dockerfile o dosyayı KURMALI.
    extras_files = ["requirements-osint.txt", "requirements-retina.txt"]
    owner = next(
        (f for f in extras_files if dist.lower() in _requirement_names(ROOT / f)),
        None,
    )
    assert owner, f"{dist} hiçbir requirements dosyasında tanımlı değil"
    assert f"-r {owner}" in dockerfile, (
        f"{dist} {owner} içinde ama Dockerfile bu dosyayı kurmuyor "
        "(kapı açık, motor yok)"
    )


def test_browserforge_is_declared_with_scrapling():
    """scrapling 0.4.x browserforge'u zorunlu kullanır ama metadata'da yazmaz."""
    retina = _requirement_names(ROOT / "requirements-retina.txt")
    assert "scrapling" in retina
    assert "browserforge" in retina, "scrapling kurulup browserforge kurulmazsa extract_error"
