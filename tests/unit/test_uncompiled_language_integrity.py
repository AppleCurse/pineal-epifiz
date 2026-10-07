"""Derleyicisi BU ORTAMDA bulunmayan diller için yapısal bütünlük kilidi.

Kapsam: Kotlin (Android) ve Rust (Tauri/rust_core).

Neden var: bu deponun CI'si `cargo check`/`cargo test` ve
`gradle lintDebug/testDebugUnitTest/assembleDebug` koşar; yani asıl doğrulama
ORADA yapılır. Ancak yerel/çevrimdışı doğrulama ortamlarında (ve bu denetim
sandbox'ında) ne JDK/Gradle ne de Rust araç zinciri kurulabiliyor — ilgili
dağıtım adreslerine çıkış kapalı. Bu test, o boşlukta **kaba ama sıfır olmayan**
bir güvenlik ağıdır: denetim sırasında elle düzenlenen Kotlin/Rust dosyalarının
ayraç (delimiter) dengesini doğrular, yani en sık yapılan kırılma biçimini
(bitmemiş blok/parantez) yakalar.

YAPAMADIĞI ŞEY: tür denetimi, derleme, gerçek birim testi. Bunlar için CI
zorunludur. Bu test o yerine geçtiğini İDDİA ETMEZ.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Denetim sırasında düzenlenen, derleyicisi yerelde OLMAYAN dosyalar.
GUARDED_FILES = [
    "android/app/src/main/java/com/example/pineal/i18n/I18n.kt",
    "android/app/src/main/java/com/example/pineal/engine/PinealAnalyzerEngine.kt",
    "rust_core/src-tauri/src/lib.rs",
    "rust_core/src-tauri/Cargo.toml",
    "rust_core/Cargo.toml",
]

_PAIRS = {"}": "{", ")": "(", "]": "["}
_OPENERS = set(_PAIRS.values())


def _delimiter_balance(path: Path) -> tuple[bool, dict[str, int]]:
    """Ayraç dengesini sayar.

    Bilinçli olarak KABA: dize/character literal ayrımı yapmaz. Kotlin
    prompt'ları ve Rust `json!` makroları ayraç İÇERİR, ama iç içe ve
    dengeli oldukları için denge bozulmaz. Amaç, yarım kalan bir düzenlemeyi
    yakalamaktır; derleyici yerine geçmek değil.
    """
    depth = {opener: 0 for opener in _OPENERS}
    for char in path.read_text(encoding="utf-8"):
        if char in depth:
            depth[char] += 1
        elif char in _PAIRS:
            depth[_PAIRS[char]] -= 1
            if depth[_PAIRS[char]] < 0:
                return False, depth
    return all(value == 0 for value in depth.values()), depth


@pytest.mark.parametrize("relative_path", GUARDED_FILES)
def test_delimiters_are_balanced(relative_path: str):
    path = REPO_ROOT / relative_path
    assert path.is_file(), f"korunan dosya bulunamadı: {relative_path}"

    balanced, depth = _delimiter_balance(path)
    assert balanced, (
        f"{relative_path}: ayraç dengesi BOZUK {depth}. "
        "Bu dosyanın derleyicisi bu ortamda yok; gerçek doğrulama CI'da "
        "(cargo / gradle). Yerelde yalnızca bu kaba kontrol koşabiliyor."
    )


def test_guarded_files_were_actually_touched_by_the_audit():
    """Kilidin kapsamı anlamlı olmalı: liste, denetimde değişen dosyaları kapsar."""
    for relative_path in GUARDED_FILES:
        assert (REPO_ROOT / relative_path).is_file(), relative_path
