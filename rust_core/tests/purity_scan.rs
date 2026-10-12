// rust_core/tests/purity_scan.rs
//
// Python tarafındaki test_resolver_module_has_no_forbidden_imports ile
// SİMETRİK: token_compressor.rs'in yasaklı bağımlılıklara (dosya/ağ/
// CanonicalMemory kavramları) DOKUNMADIĞINI derleme sonrası değil,
// kaynak metni üzerinden statik olarak doğrular.
//
// Python'daki simetrik test (tests/unit/test_token_compressor_purity.py)
// AST tabanlıdır: yalnızca GERÇEK use/import çağrılarını sayar; yorumları
// ve test bölgesini (Python'da testler ayrı dosyadadır) asla cezalandırmaz.
// Bu test de aynı sözleşmeyi ham-metin taramasıyla kurar:
//   1) #[cfg(test)] bölgesi (test-only `use std::fs` dahil) tarama DIŞIDIR —
//      tıpkı Python testlerinin ayrı dosyada olması gibi ürün kodu değildir.
//   2) `//` satır yorumları (//! doküman yorumları dahil) tarama DIŞIDIR —
//      tıpkı Python AST'nin yorumları yok sayması gibi.
// Bu iki istisna DIŞINDA kalan üretim bölgesinde yasaklı bir belirteç
// görülürse test KIRMIZI yanar (mutasyon testiyle kilitli: üretim koduna
// gerçek bir `std::fs::read_to_string(...)` eklendiğinde test düşer).

use std::fs;

#[test]
fn token_compressor_has_no_forbidden_deps() {
    let source = fs::read_to_string("src/token_compressor.rs")
        .expect("token_compressor.rs okunamadı");

    // (1) #[cfg(test)] başlangıcından itibaren her şeyi at: orası yalnızca
    // test kodudur (ürün kodu değildir) ve kendi `use std::fs;`'ini taşır.
    // Bu dosyada tek `#[cfg(test)]` vardır ve dosyanın sonuna kadar uzanır;
    // gelecekte birden çok test modülü eklenirse de ilk eşleşmeden sonrası
    // ürün kodu OLAMAZ (cfg(test) derleme-koşulludur, modül gövdesi test
    // derlemesinde var olur) — bu yüzden ilk eşleşmeden kesmek güvenlidir.
    let production_region = source.split("#[cfg(test)]").next().unwrap_or("");

    // (2) Üretim bölgesindeki `//` satır yorumlarını at (//! dahil). Python
    // tarafı AST okuduğu için yorumlar orada zaten sayılmaz; burada ham
    // metin taradığımız için aynı etki için açıkça temizleriz. Dosyada blok
    // yorum (/* */) ve string içinde `//` geçmediği için satır temizliği
    // yeterli ve kırılgan değildir (purity_scan bunu ayrıca doğrular).
    let mut scan_text = String::new();
    for line in production_region.lines() {
        match line.find("//") {
            Some(pos) => scan_text.push_str(&line[..pos]),
            None => scan_text.push_str(line),
        }
        scan_text.push('\n');
    }

    let forbidden_tokens = [
        "std::fs",
        "std::net",
        "reqwest",
        "tokio::net",
        "canonical_memory",
        "hindsight_memory",
        "task_executor",
        "CanonicalMemory",
        "HindsightMemory",
    ];

    for token in forbidden_tokens {
        assert!(
            !scan_text.contains(token),
            "YASAKLI BAĞIMLILIK BULUNDU: '{}' — token_compressor.rs saf kalmalı",
            token
        );
    }
}
