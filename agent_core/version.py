"""Depo sürümünün TEK KAYNAĞI: kök dizindeki ``VERSION`` dosyası.

[AUDIT 2026-10-07 · Madde 2] Sürüm kimliği depoya dağılmıştı: FastAPI
başlığında ``v3.0.0-rc.1`` yazarken ``VERSION`` dosyası ``3.0.0-rc.2``
diyordu; Cargo manifestoları ``5.0.0`` ve ``0.1.0``, Tauri yapılandırması
``5.0.0``, kök npm manifestosu ise ``3.0.0`` idi. Yani ürünün "kaçıncı
sürüm" olduğu sorusunun beş farklı (ve birbiriyle çelişen) cevabı vardı.
Ayrıntılı sapma tablosu ve kilit sözleşmesi:
``tests/unit/test_version_identity.py``.

Karar: ``VERSION`` dosyası otoritedir. Çalışma zamanında sürüm gösteren her
yüzey (FastAPI başlığı, MCP ``server_version``) bu değeri **okuyarak**
üretir; kopyalayarak değil. Kopyalanamayan yerler (npm/Cargo/tauri
manifestoları) ise ``tests/unit/test_version_identity.py`` tarafından
``VERSION`` ile aynı olmaya ZORLANIR — yani sapma derhâl kırmızı alarm üretir.

Bu modülün bilinçli kısıtları:
* Ağ yok, önbellek yok: dosya her çağrıda okunur (sürüm, süreç yaşamı
  boyunca değişmez; isteyen ``VERSION`` sabitini kullanır).
* İçe aktarımda patlamaz: dosya yoksa/boşsa ``"unknown"`` döner, çünkü
  sürüm okunamadı diye uygulamanın açılmaması hatanın kendisinden beterdir.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["VERSION", "read_version", "version_file_path"]

#: Kök ``VERSION`` dosyasının yolu.
#: agent_core/version.py -> agent_core/ -> depo kökü
version_file_path: Path = Path(__file__).resolve().parents[1] / "VERSION"


def read_version() -> str:
    """Kök ``VERSION`` dosyasını oku ve sürümü döndür.

    Returns:
        Dosya içeriğinin temizlenmiş hâli. Okunamazsa ya da boşsa
        ``"unknown"`` — asla istisna fırlatmaz.
    """
    try:
        text = version_file_path.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return text or "unknown"


#: Süreç başında bir kez okunan sürüm. Çoğu çağrı yeri bunu kullanır.
VERSION: str = read_version()
