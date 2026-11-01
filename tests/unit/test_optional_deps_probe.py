"""İsteğe bağlı bağımlılık yoklaması — noktalı adlar ve bozuk modüller.

[2026-10-23 incelemesi] Somut hata:

    importlib.util.find_spec("crawl4ai.markdown_generation_strategy")

`crawl4ai` KURULU DEĞİLKEN `None` döndürmez, `ModuleNotFoundError` fırlatır.
`agent_core/capabilities/adapters_osint.py::_module_available` bu istisnayı
yakalamıyordu: yeteneğin `availability()` çağrısı "kapalı" yerine İSTİSNAYA
düşüyor, koşucu bunu `availability_error` diye yazıyordu — yani operatör
"maigret kur" mesajını hiç görmüyordu.

Bu testler istisnanın değil SÖZLEŞMENİN testidir: kurulu olmayan ad → `False`.
"""

from __future__ import annotations

import importlib.util
import sys
import types

import pytest

from agent_core.utils.optional_deps import module_available

_MISSING = "pineal_missing_pkg_for_tests_9f2c"


def test_missing_top_level_module_is_false():
    assert module_available(_MISSING) is False


def test_missing_parent_of_dotted_name_is_false_not_an_exception():
    """İncelemedeki birebir vaka: ebeveyn yok → `find_spec` FIRLATIR."""
    with pytest.raises(ModuleNotFoundError):
        # Hatayı kanıtla: ham çağrı gerçekten patlıyor...
        importlib.util.find_spec(f"{_MISSING}.markdown_generation_strategy")
    # ...ama sözleşme `False`.
    assert module_available(f"{_MISSING}.markdown_generation_strategy") is False


def test_present_stdlib_module_is_true():
    assert module_available("json") is True
    assert module_available("os.path") is True


def test_empty_name_is_false():
    assert module_available("") is False


def test_module_with_none_spec_is_false(monkeypatch):
    """`__spec__ is None` → `find_spec` `ValueError` fırlatır; sözleşme yine `False`."""
    broken = types.ModuleType("pineal_broken_spec_pkg")
    broken.__spec__ = None
    monkeypatch.setitem(sys.modules, "pineal_broken_spec_pkg", broken)
    with pytest.raises(ValueError):
        importlib.util.find_spec("pineal_broken_spec_pkg")
    assert module_available("pineal_broken_spec_pkg") is False


def test_capability_availability_reports_dependency_missing_instead_of_raising(monkeypatch):
    """Gerçek yol: `MaigretCapability.availability()` istisna değil sebep döner."""
    from agent_core.capabilities.adapters_osint import MaigretCapability

    monkeypatch.setenv("ENABLE_MAIGRET", "true")

    def _boom(*_args, **_kwargs):
        raise ModuleNotFoundError("No module named 'maigret'")

    monkeypatch.setattr(importlib.util, "find_spec", _boom)
    availability = MaigretCapability().availability()
    assert availability.available is False
    assert availability.reason == "dependency_missing:maigret"


@pytest.mark.asyncio
async def test_crawl_enricher_returns_library_missing_without_crawl4ai(monkeypatch):
    """`crawl4ai.markdown_generation_strategy` yokken temiz ret, çökme yok."""
    from agent_core.services.crawl_enricher import fetch_readable

    monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
    monkeypatch.setattr(
        "agent_core.utils.optional_deps.module_available", lambda _name: False
    )
    result = await fetch_readable("https://example.com/haber")
    assert result.available is False
    assert result.reason == "library_missing"
