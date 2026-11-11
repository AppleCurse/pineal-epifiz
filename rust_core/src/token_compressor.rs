//! token_compressor.rs
//!
//! PINEAL-HERETIC RTK Entegrasyonu — İzole Sıkıştırma Modülü (Rust Referans Impl.)
//!
//! =========================================================================
//! MIRROR PATTERN NOTU
//! =========================================================================
//! Bu dosya, agent_core/services/token_compressor.py ile MANTIKSAL OLARAK
//! ÖZDEŞ olacak şekilde tutulur. Python tarafı üründe fiilen çalışan
//! koddur (Phase 9 Decision B gereği rust_core Python ürün hattına
//! bağlanamaz). Bu Rust dosyası:
//!   - Algoritmanın masaüstü/native varyantı için referans implementasyon
//!   - cargo test ile bağımsız CI kapısında doğrulanan deneysel bileşen
//! İkisi de aynı tests/fixtures/compression_cases.json dosyasından test
//! okur — biri diğerinden saparsa ilgili CI'da kırmızı görülür.
//!
//! =========================================================================
//! ADLİ TASARIM İLKESİ (Fail-Open Gerekçesi)
//! =========================================================================
//! Pineal'in genel doktrini "fail-closed"tur (Bayesian Epistemik Kapı,
//! quota_governor.UnknownQuotaDenied, PINEAL_ALLOW_PAID_ESCALATION).
//! Bu modül BİLEREK farklı davranır: FAIL-OPEN.
//!
//! Gerekçe: Bu modül KANIT üretmez, HARCAMA kararı vermez, EPİSTEMİK
//! sonuca varmaz. Yalnızca dış API'ye giden bir prompt'un token
//! boyutunu düşüren PERFORMANS optimizasyonudur. Çökerse sistem
//! "belirsizlik" veya "sahte kanıt" üretmez — sadece daha uzun/pahalı
//! bir prompt gönderilir. Bu yüzden başarısızlık "dur" değil,
//! "orijinali kullan" ile sonuçlanır.
//!
//! Fail-closed olması gereken tek yer: bu modülün YANLIŞLIKLA anlam
//! değiştiren bir dönüşüm yapması. Bunu önlemek için tüm dönüşümler
//! SÖZDİZİMSEL ve GERİ ALINABİLİR şekilde kısıtlanmıştır.
//!
//! =========================================================================
//! SAFLIK GARANTİSİ
//! =========================================================================
//! Bu dosya:
//!   - Dosya sistemine dokunmaz (std::fs KULLANILMAZ — testler hariç,
//!     testler yalnızca fixture OKUR, ürün kodu değildir)
//!   - Ağa dokunmaz
//!   - CanonicalMemory, HindsightMemory, task_executor kavramlarından
//!     TAMAMEN HABERSİZDİR
//!   - Girdi: &str, Çıktı: String. Başka yan etkisi yoktur.
//! Bkz. tests/purity_scan.rs — bu saflığı statik kaynak taramasıyla doğrular.

/// Sıkıştırma stratejisi seçenekleri.
/// Agresiflik arttıkça geri-alınamazlık riski artar — bu yüzden
/// varsayılan her zaman en muhafazakâr seviyedir.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CompressionLevel {
    /// Sadece fazlalık boşluk/satır temizliği. Anlam kaybı riski SIFIR.
    Conservative,
    /// Conservative + tek-satırlık geçerli JSON minify + ardışık
    /// tekrarlayan boilerplate satır eleme. Anlam kaybı riski minimal
    /// ama sıfır değil.
    Standard,
}

impl CompressionLevel {
    fn from_str_id(s: &str) -> Option<Self> {
        match s {
            "conservative" => Some(Self::Conservative),
            "standard" => Some(Self::Standard),
            _ => None,
        }
    }
}

/// Ana giriş noktası. Girdi metnini verilen seviyeye göre sıkıştırır.
///
/// # Garantiler
/// - Panic ATMAZ. İç hata durumunda orijinal `input`'u döndürür.
/// - Girdi boşsa/sadece whitespace ise aynen döner.
/// - Çıktı her zaman geçerli UTF-8'dir (girdi geçerliyse).
pub fn compress_prompt(input: &str, level: CompressionLevel) -> String {
    if input.trim().is_empty() {
        return input.to_string();
    }

    let stage1 = collapse_whitespace(input);

    match level {
        CompressionLevel::Conservative => stage1,
        CompressionLevel::Standard => {
            let stage2 = try_minify_json_lines(&stage1);
            dedupe_boilerplate_lines(&stage2)
        }
    }
}

/// Aşama 1: Fazlalık boşluk ve satır temizliği (anlam-nötr, sözdizimsel).
fn collapse_whitespace(input: &str) -> String {
    let mut result = String::with_capacity(input.len());
    let mut newline_streak = 0;
    let mut last_was_space = false;

    for ch in input.chars() {
        match ch {
            '\n' => {
                newline_streak += 1;
                if newline_streak <= 2 {
                    result.push('\n');
                }
                last_was_space = false;
            }
            ' ' | '\t' => {
                if !last_was_space {
                    result.push(' ');
                    last_was_space = true;
                }
            }
            '\r' => {
                // CRLF normalizasyonu — \r sessizce atılır
            }
            _ => {
                newline_streak = 0;
                last_was_space = false;
                result.push(ch);
            }
        }
    }

    result
        .lines()
        .map(|line| line.trim_end())
        .collect::<Vec<_>>()
        .join("\n")
}

/// Aşama 2 (Standard): Yalnızca TEK SATIRLIK geçerli JSON'ları minify eder.
///
/// GÜVENLİK KISITI: Çok satırlı / iç içe JSON tespiti YAPILMAZ.
/// Doğrulanamayan blok orijinal haliyle bırakılır (ya tam minify, ya hiç).
fn try_minify_json_lines(input: &str) -> String {
    input
        .lines()
        .map(|line| {
            let trimmed = line.trim();
            let looks_like_json = (trimmed.starts_with('{') && trimmed.ends_with('}'))
                || (trimmed.starts_with('[') && trimmed.ends_with(']'));

            if looks_like_json {
                match serde_json::from_str::<serde_json::Value>(trimmed) {
                    Ok(value) => serde_json::to_string(&value).unwrap_or_else(|_| line.to_string()),
                    Err(_) => line.to_string(),
                }
            } else {
                line.to_string()
            }
        })
        .collect::<Vec<_>>()
        .join("\n")
}

/// Aşama 3 (Standard): Ardışık tekrarlayan satırları eler.
///
/// GÜVENLİK KISITI: Yalnızca TAM AYNI, ARDIŞIK satırlar hedeflenir.
/// Uzak mesafeli tekrarlara (ör. kasıtlı bio üslubu) dokunulmaz.
fn dedupe_boilerplate_lines(input: &str) -> String {
    const MAX_CONSECUTIVE_REPEATS: usize = 2;

    let mut result: Vec<&str> = Vec::new();
    let mut last_line: Option<&str> = None;
    let mut repeat_count = 0usize;

    for line in input.lines() {
        if Some(line) == last_line && !line.trim().is_empty() {
            repeat_count += 1;
            if repeat_count < MAX_CONSECUTIVE_REPEATS {
                result.push(line);
            }
        } else {
            repeat_count = 0;
            result.push(line);
            last_line = Some(line);
        }
    }

    result.join("\n")
}

// =============================================================================
// TESTLER — fixtures/compression_cases.json'dan okur (Python ile ORTAK KAYNAK)
// =============================================================================
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;
    use std::collections::HashMap;
    use std::fs;

    fn load_fixture() -> Vec<Value> {
        let path = concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/fixtures/compression_cases.json"
        );
        let raw = fs::read_to_string(path).expect("fixture dosyası okunamadı");
        let parsed: Value = serde_json::from_str(&raw).expect("fixture JSON geçersiz");
        parsed["cases"]
            .as_array()
            .expect("cases dizi olmalı")
            .clone()
    }

    fn count_lines(text: &str, needle: &str) -> usize {
        text.lines().filter(|l| l.trim() == needle.trim()).count()
    }

    #[test]
    fn all_fixture_cases_pass() {
        let cases = load_fixture();
        let mut failures: Vec<String> = Vec::new();

        for case in &cases {
            let id = case["id"].as_str().unwrap_or("UNKNOWN");
            let input = case["input"].as_str().unwrap_or("");
            let level_str = case["level"].as_str().unwrap_or("conservative");
            let level = CompressionLevel::from_str_id(level_str)
                .unwrap_or_else(|| panic!("bilinmeyen level: {} (case: {})", level_str, id));

            let output = compress_prompt(input, level);

            if let Some(expected) = case.get("expected").and_then(|v| v.as_str()) {
                if output != expected {
                    failures.push(format!("[{}] expected={:?} got={:?}", id, expected, output));
                }
            }

            if let Some(expected_contains) = case.get("expected_contains").and_then(|v| v.as_str())
            {
                if !output.contains(expected_contains) {
                    failures.push(format!(
                        "[{}] expected_contains={:?} got={:?}",
                        id, expected_contains, output
                    ));
                }
            }

            if let Some(expected_trimmed) = case.get("expected_trimmed").and_then(|v| v.as_str()) {
                if output.trim() != expected_trimmed {
                    failures.push(format!(
                        "[{}] expected_trimmed={:?} got={:?}",
                        id,
                        expected_trimmed,
                        output.trim()
                    ));
                }
            }

            if let Some(line_counts) = case.get("expected_line_count").and_then(|v| v.as_object()) {
                for (needle, expected_count) in line_counts {
                    let expected_count = expected_count.as_u64().unwrap_or(0) as usize;
                    let actual_count = count_lines(&output, needle);
                    if actual_count != expected_count {
                        failures.push(format!(
                            "[{}] line_count({:?}) expected={} got={}",
                            id, needle, expected_count, actual_count
                        ));
                    }
                }
            }
        }

        assert!(
            failures.is_empty(),
            "Fixture testleri başarısız:\n{}",
            failures.join("\n")
        );
    }

    #[test]
    fn never_panics_on_arbitrary_bytes_as_str() {
        let weird_inputs = ["\0", "\u{FEFF}test", "𝔘𝔫𝔦𝔠𝔬𝔡𝔢", "\n\n\n\n\n\n\n"];
        for input in weird_inputs {
            let _ = compress_prompt(input, CompressionLevel::Standard);
        }
    }

    #[test]
    fn fixture_file_is_not_empty() {
        let cases = load_fixture();
        assert!(
            !cases.is_empty(),
            "fixture dosyası boş olamaz — testler anlamsızlaşır"
        );
    }
}
