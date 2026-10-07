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

/// `//` satır yorumlarını (//! doküman yorumları dahil) metinden söker.
///
/// Python tarafındaki simetrik test AST okuduğu için yorumlar orada zaten
/// sayılmaz; burada ham metin taradığımız için aynı etkiyi açıkça kurarız.
/// Taranan dosyalarda blok yorum (/* */) ve string içinde `//` geçmediği
/// için satır bazlı temizlik yeterlidir ve kırılgan değildir.
fn strip_line_comments(source: &str) -> String {
    let mut scan_text = String::new();
    for line in source.lines() {
        match line.find("//") {
            Some(pos) => scan_text.push_str(&line[..pos]),
            None => scan_text.push_str(line),
        }
        scan_text.push('\n');
    }
    scan_text
}

/// Belirtecin yorumlardan arındırılmış metindeki tekrar sayısını sayar.
fn count_occurrences(haystack: &str, needle: &str) -> usize {
    if needle.is_empty() {
        return 0;
    }
    haystack.match_indices(needle).count()
}

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

    // (2) Üretim bölgesindeki `//` satır yorumlarını at (//! dahil).
    let scan_text = strip_line_comments(production_region);

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

/// [VAULT_PERSISTENCE_FIX 2026-10-07] TİYATRO KİLİDİ.
///
/// Geçmiş: `vault::tests::test_vault_roundtrip_store_reload_retrieve` testi
/// `#[ignore = "VAULT_PERSISTENCE_BUG: age file truncated on store->reload"]`
/// ile susturulmuştu. Kasa GERÇEKTEN veri kaybediyordu ama CI yeşildi —
/// yani "kusursuzuz, testler geçiyor" görüntüsü bir yanılsamaydı.
///
/// Kök neden bulundu ve onarıldı: `age::stream::StreamWriter::finish()`
/// hiç çağrılmıyordu. age 0.10.1 sözleşmesi açıkça söyler — "You **MUST**
/// call `finish` … Failing to call `finish` will result in a truncated file
/// that will fail to decrypt." `Drop` son chunk'ı YAZMAZ.
///
/// Bu test aynı kaçışın bir daha YAPILAMAYACAĞINI kaynak düzeyinde kilitler.
/// Bilinçli olarak derleme-sonrası değil kaynak-metni denetimidir: `#[ignore]`
/// etiketi derlemeyi ve diğer testleri ETKİLEMEZ, yani tek yakalama yolu
/// budur (tıpkı token_compressor saflık denetimi gibi).
#[test]
fn vault_has_no_ignored_tests_and_finalizes_age_streams() {
    let source = fs::read_to_string("src/vault.rs").expect("vault.rs okunamadı");
    // Kasa dosyasının TAMAMI taranır (üretim + #[cfg(test)] bölgesi):
    // `#[ignore]` kaçışı test bölgesinde yaşar, üretim bölgesinde değil.
    let scan_text = strip_line_comments(&source);

    // (1) Kasa testlerinde HİÇBİR test susturulamaz.
    assert!(
        !scan_text.contains("#[ignore"),
        "TİYATRO: vault.rs içinde #[ignore] özniteliği bulundu. \
         Kasanın bilinen bir hatası test susturularak CI'dan GİZLENEMEZ; \
         hata onarılır ve test koşar."
    );
    assert!(
        !scan_text.contains("VAULT_PERSISTENCE_BUG"),
        "VAULT_PERSISTENCE_BUG belirteci hâlâ kodda (yorum dışı) yaşıyor"
    );

    // (2) Her age akışı `finish()` ile KAPATILMAK zorunda.
    //     vault.rs'te iki şifreleme yolu vardır (veri + kimlik); her biri
    //     bir `wrap_output` ve tam olarak bir `finish` içerir. Eşitlik
    //     bozulursa ya kesik dosya yazılıyordur (finish eksik) ya da
    //     denetim anlamsızlaşmıştır (finish fazla).
    let wraps = count_occurrences(&scan_text, ".wrap_output(");
    let finishes = count_occurrences(&scan_text, ".finish()");
    assert!(
        wraps >= 2,
        "beklenenden az age şifreleme yolu bulundu: {} (veri + kimlik = 2)",
        wraps
    );
    assert_eq!(
        wraps, finishes,
        "KESİK AGE AKIŞI: {} `wrap_output` çağrısına karşılık {} `.finish()` var. \
         finish() çağrılmayan age akışı diske KESİK dosya yazar \
         (\"age file is truncated\") — bu, kasanın veri kaybı arızasının ta kendisidir.",
        wraps, finishes
    );

    // (3) Kasa yolunda panik YASAK: bir kasa arızası süreci çökertmek
    //     yerine `VaultError` olarak dönmelidir (sessiz çökme yok).
    assert_eq!(
        count_occurrences(&scan_text, ".expect("),
        0,
        "vault.rs `.expect(...)` ile panikliyor; kasa arızası VaultError döndürmeli"
    );

    // (4) Gizli anahtar diskte düz metin DURAMAZ. `identity` alanı eski
    //     (güvensiz) şemanın adıdır; yeni şema `identity_encrypted` yazar ve
    //     düz metin kimlik taşıyan dosyayı fail-closed reddeder.
    assert!(
        scan_text.contains("identity_encrypted"),
        "kasa şeması şifreli kimlik alanı içermiyor"
    );
    assert!(
        scan_text.contains("InsecureVaultFile"),
        "güvensiz (düz metin kimlikli) kasa dosyası için fail-closed hata tipi yok"
    );
    assert!(
        scan_text.contains("VaultLocked"),
        "mühürlenmiş kasa için fail-closed hata tipi yok (kilit kilit gibi davranmalı)"
    );
}
