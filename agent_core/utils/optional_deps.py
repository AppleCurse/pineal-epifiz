"""İsteğe bağlı bağımlılık yoklaması — TEK KAYNAK.

Neden bu modül var? (2026-10-23 incelemesi)

``importlib.util.find_spec("crawl4ai.markdown_generation_strategy")`` ebeveyn
paket (``crawl4ai``) kurulu DEĞİLKEN ``None`` DÖNDÜRMEZ; ``ModuleNotFoundError``
FIRLATIR. Aynı şey ``__spec__`` değeri ``None`` olan (ör. test sahtesi ya da
bozuk kurulum) bir modül adı için ``ValueError`` olarak gelir.

Bu yüzden "kurulu mu?" sorusu tek bir yerde, tek bir sözleşmeyle cevaplanır:

    * kurulu ise ``True``
    * kurulu değilse ``False`` (nokta içeren ad, ebeveyni yok → ``False``)
    * bozuk/ölçülemez ad → ``False`` (asla istisna fırlatmaz)

Neden önemli: yetenek ``availability()`` çağrısı bir istisna fırlatırsa
koşucu bunu ``availability_error`` diye yakalar ve yetenek "kapalı" değil
"bozuk" görünür; operatör hangi paketi kuracağını öğrenemez. Üstelik bu
yoklama birden çok adaptörde kopyalanmıştı (adapters_osint, stealth_provider,
report_factory, crawl_enricher) — dördü de farklı davranıyordu.
"""

from __future__ import annotations

import importlib.util

__all__ = ["module_available"]


def module_available(name: str) -> bool:
    """``name`` içe aktarılabilir mi? (noktalı adlarda ebeveyn yoksa ``False``)"""
    if not name:
        return False
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
        # ModuleNotFoundError: noktalı adın ebeveyni yok (asıl hata buydu).
        # ValueError: modülün __spec__ değeri None (bozuk/yarım kurulum).
        return False
