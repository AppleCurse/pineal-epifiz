//! PINEAL-HERETIC v4.0 - Uncertainty Engine
//!
//! Tip-güvenli belirsizlik yönetimi ve Fail-Fast mekanizması.
//! LLM halüsinasyonlarını ve eksik veri durumlarını derleme zamanında yakalar.

use serde::{Deserialize, Serialize};
use thiserror::Error;

/// Güven skoru enum'u - asla çıplak float değil!
/// Eksik veri durumunda zincir güvenle durur.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum ConfidenceLevel {
    /// Kanıt yetersiz, işlem durdurulmalı
    Halt(InsufficientEvidence),
    /// Kanıt yeterli, işleme devam edilebilir
    Pass(Evidence),
}

/// Yetersiz kanıt durumu - neden durduğunu açıklar
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct InsufficientEvidence {
    pub reason: String,
    pub missing_fields: Vec<String>,
    pub severity: Severity,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum Severity {
    Low,
    Medium,
    Critical,
}

/// Başarılı kanıt - eldeki veriyi taşır
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Evidence {
    /// 0-100 tip-güvenli ÖLÇÜLMÜŞ kanıt kalitesi (`UncertaintyEngine::data_score`).
    /// [§8.5] Eskiden PASS durumunda SABİT 100 yazılıyordu: "zorunlu alanlar var"
    /// = "payload tamamen kanıt" varsayımı. Artık oran ölçülür; metadata skoru
    /// şişiremez, placeholder yükseltemez, aday alan yoksa 0'dır.
    pub score: u8,
    pub data_points: Vec<String>,
    pub verified_at: chrono::DateTime<chrono::Utc>,
}

/// Uncertainty Engine hataları
#[derive(Error, Debug)]
pub enum UncertaintyError {
    #[error("Veri eksik: {0}")]
    MissingData(String),

    #[error("Doğrulama başarısız: {0}")]
    ValidationFailed(String),

    #[error("LLM yanıtı format hatası: {0}")]
    LLMFormatError(String),
}

/// Belirsizlik Motoru - ana işleyici
pub struct UncertaintyEngine {
    _task_id: uuid::Uuid,
    required_fields: Vec<String>,
}

impl UncertaintyEngine {
    pub fn new(task_id: uuid::Uuid, required_fields: Vec<String>) -> Self {
        Self {
            _task_id: task_id,
            required_fields,
        }
    }

    /// Veriyi doğrula ve ConfidenceLevel döndür.
    /// Asla sahte skor üretmez - Fail-Fast prensibi.
    ///
    /// [006] fix: eski sözleşme yalnızca "alan var mı"na bakıyordu; {} / boş
    /// dizi / placeholder metin / null değerler PASS olup score=100 alıyordu.
    /// Yeni sözleşme: "alan var" != "kanıt var".
    ///   - alan yok veya null        -> HALT
    ///   - boş obje / boş dizi       -> HALT (kanıt taşımayan kap)
    ///   - NaN/sonsuz sayı           -> HALT
    ///   - boş/placeholder metin     -> HALT ("unknown", "n/a", "yok", ...)
    /// PASS yalnızca TÜM zorunlu alanlar gerçek kanıt taşıdığında verilir.
    pub fn evaluate<T: Serialize>(&self, data: &T) -> Result<ConfidenceLevel, UncertaintyError> {
        // JSON serialize ederek alan kontrolü yap
        let json_value = serde_json::to_value(data)
            .map_err(|e| UncertaintyError::ValidationFailed(e.to_string()))?;

        let obj = json_value
            .as_object()
            .ok_or_else(|| UncertaintyError::ValidationFailed("Veri obje değil".to_string()))?;

        // Eksik/kanıtsız alanları tespit et
        let mut missing: Vec<String> = Vec::new();
        for field in &self.required_fields {
            let bears_evidence = match obj.get(field) {
                None => false,
                Some(value) => Self::value_bears_evidence(value),
            };
            if !bears_evidence {
                missing.push(field.clone());
            }
        }

        if !missing.is_empty() {
            // FAIL-FAST: Eksik/kanıtsız alan varsa hemen HALT
            return Ok(ConfidenceLevel::Halt(InsufficientEvidence {
                reason: format!(
                    "Gerekli {} alandan {} eksik veya kanıt taşımıyor",
                    self.required_fields.len(),
                    missing.len()
                ),
                missing_fields: missing,
                severity: Severity::Critical,
            }));
        }

        // Tüm zorunlu alanlar gerçek kanıt taşıyor - PASS.
        // [RÖNTGEN 2026-09-23 / SAHİP KARARI §8.5] score SABİT 100 DEĞİL:
        // Python'daki `data_score`'un karşılığıyla ÖLÇÜLÜR (kanıt taşıyan alan /
        // aday alan, runtime metadata hariç). "Zorunlu alanlar geçti" demek
        // "payload'ın tamamı kanıt" demek değildir; eskisi bunu varsayıyordu.
        let data_points: Vec<String> = obj.keys().cloned().collect();
        let score = Self::data_score(obj);
        Ok(ConfidenceLevel::Pass(Evidence {
            score,
            data_points,
            verified_at: chrono::Utc::now(),
        }))
    }

    /// Skor üretimini ŞİŞİREN runtime metadata alanları (Python
    /// `UncertaintyEngine.RUNTIME_METADATA_FIELDS` ile aynı sözleşme + §8.7
    /// duvar saati alanları). Bunlar KANIT DEĞİLDİR: model adı, sağlayıcı,
    /// süre, token, ajan adı, iz kimliği, zaman damgası, sürüm.
    pub const RUNTIME_METADATA_FIELDS: &[&str] = &[
        "confidence",
        "data_confidence",
        "fallback_reason",
        "model",
        "model_name",
        "provider",
        "source_provider",
        "usage",
        "tokens",
        "token_usage",
        "metrics",
        "duration_ms",
        "elapsed_ms",
        "latency_ms",
        "elapsed",
        "agent",
        "agent_name",
        "request_id",
        "task_id",
        "trace_id",
        "version",
        // duvar saati: mühür/skor girdisi olamaz (§8.7)
        "created_at",
        "timestamp",
        "ts",
        "computed_at",
        "updated_at",
        "generated_at",
        "measured_at",
        "observed_at",
        "started_at",
        "completed_at",
    ];

    /// Kanıt KALİTESİ ölçüsü (0-100): kanıt taşıyan alan / aday alan.
    ///
    /// Python'daki `data_score` basit-oran yolunun Rust karşılığı. Metadata
    /// alanları aday kümesine GİRMEZ (skoru şişiremez); placeholder/boş/null
    /// değerler kanıt SAYILMAZ (skoru yükseltemez). Aday alan yoksa 0 döner —
    /// yani "ölçülecek kanıt yok" dürüstçe 0'dır, 100 değildir.
    pub fn data_score(obj: &serde_json::Map<String, serde_json::Value>) -> u8 {
        let candidates: Vec<&serde_json::Value> = obj
            .iter()
            .filter(|(k, _)| !Self::RUNTIME_METADATA_FIELDS.contains(&k.as_str()))
            .map(|(_, v)| v)
            .collect();

        if candidates.is_empty() {
            return 0;
        }

        let bearing = candidates
            .iter()
            .filter(|v| Self::value_bears_evidence(*v))
            .count();

        // Tam sayı yuvarlaması (en yakın yüzde), 0-100 aralığına kırpılır.
        let total = candidates.len();
        let pct = (bearing * 100 + total / 2) / total;
        pct.min(100) as u8
    }

    /// Bir JSON değeri gerçek kanıt taşıyor mu? ([006] sözleşmesi)
    pub fn value_bears_evidence(value: &serde_json::Value) -> bool {
        use serde_json::Value;
        match value {
            Value::Null => false,
            Value::Bool(_) => true,
            Value::Number(n) => n.as_f64().map(|f| f.is_finite()).unwrap_or(false),
            Value::String(s) => {
                let t = s.trim().to_lowercase();
                if t.is_empty() {
                    return false;
                }
                !matches!(
                    t.as_str(),
                    "unknown"
                        | "n/a"
                        | "na"
                        | "-"
                        | "yok"
                        | "yok."
                        | "bilinmiyor"
                        | "veri yok"
                        | "belirsiz"
                        | "not found"
                        | "no data"
                        | "no results"
                )
            }
            Value::Array(items) => {
                !items.is_empty() && items.iter().any(Self::value_bears_evidence)
            }
            Value::Object(map) => !map.is_empty() && map.values().any(Self::value_bears_evidence),
        }
    }

    /// LLM'den gelen JSON'u güvenli şekilde parse et
    pub fn parse_llm_response<T: for<'de> Deserialize<'de>>(
        &self,
        raw_response: &str,
    ) -> Result<T, UncertaintyError> {
        serde_json::from_str(raw_response)
            .map_err(|e| UncertaintyError::LLMFormatError(format!("JSON parse hatası: {}", e)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde::Serialize;

    #[derive(Serialize)]
    struct MockProfile {
        username: String,
        posts: Vec<String>,
        // bio eksik olacak
    }

    #[test]
    fn test_fail_fast_on_missing_field() {
        let engine = UncertaintyEngine::new(
            uuid::Uuid::new_v4(),
            vec![
                "username".to_string(),
                "posts".to_string(),
                "bio".to_string(),
            ],
        );

        let profile = MockProfile {
            username: "test_user".to_string(),
            posts: vec!["post1".to_string()],
        };

        let result = engine.evaluate(&profile).unwrap();

        match result {
            ConfidenceLevel::Halt(evidence) => {
                assert_eq!(evidence.missing_fields, vec!["bio"]);
                assert_eq!(evidence.severity, Severity::Critical);
            }
            ConfidenceLevel::Pass(_) => panic!("Beklenen HALT durumu gelmedi!"),
        }
    }

    #[test]
    fn test_empty_object_field_does_not_pass() {
        // [006]: {"user_authentic_vector": {}} artık PASS olamaz
        let engine = UncertaintyEngine::new(
            uuid::Uuid::new_v4(),
            vec!["user_authentic_vector".to_string()],
        );
        let data = serde_json::json!({ "user_authentic_vector": {} });
        match engine.evaluate(&data).unwrap() {
            ConfidenceLevel::Halt(e) => assert_eq!(e.missing_fields, vec!["user_authentic_vector"]),
            ConfidenceLevel::Pass(_) => panic!("Boş obje PASS olamaz"),
        }
    }

    #[test]
    fn test_non_numeric_dimension_does_not_pass() {
        // [006]: {"depth": "x"} -> obje dolu ama değer kanıt değil; vektör
        // ajanları tip kontrolünü kendi parse'ında yapar, motor string'e izin
        // verir ANCAK placeholder ise HALT eder:
        let engine = UncertaintyEngine::new(uuid::Uuid::new_v4(), vec!["vec".to_string()]);
        let data = serde_json::json!({ "vec": { "depth": "unknown" } });
        match engine.evaluate(&data).unwrap() {
            ConfidenceLevel::Halt(e) => assert_eq!(e.missing_fields, vec!["vec"]),
            ConfidenceLevel::Pass(_) => panic!("placeholder değer PASS olamaz"),
        }
    }

    #[test]
    fn test_null_and_empty_array_do_not_pass() {
        let engine = UncertaintyEngine::new(
            uuid::Uuid::new_v4(),
            vec!["verifications".to_string(), "score".to_string()],
        );
        let data = serde_json::json!({ "verifications": [], "score": null });
        match engine.evaluate(&data).unwrap() {
            ConfidenceLevel::Halt(e) => assert_eq!(e.missing_fields.len(), 2),
            ConfidenceLevel::Pass(_) => panic!("boş dizi/null PASS olamaz"),
        }
    }

    // --------------------------------------------------------------------- //
    // [RÖNTGEN §8.5] score ÖLÇÜLÜR, sabit 100 değil
    // --------------------------------------------------------------------- //
    #[test]
    fn score_is_measured_ratio_not_constant_100() {
        let engine = UncertaintyEngine::new(
            uuid::Uuid::new_v4(),
            vec!["vec".to_string(), "anchors".to_string()],
        );
        // Zorunlu iki alan kanıt taşıyor, ama payload'da placeholder bir alan
        // daha var: 2/3 -> 67. Eski davranış: 100.
        let data = serde_json::json!({
            "vec": { "depth": 0.9 },
            "anchors": ["ritüel uyumu"],
            "note": "bilinmiyor"
        });
        match engine.evaluate(&data).unwrap() {
            ConfidenceLevel::Pass(e) => {
                assert_eq!(e.score, 67);
                assert!(e.score < 100, "placeholder alan skoru 100 yapamaz");
            }
            ConfidenceLevel::Halt(_) => panic!("zorunlu alanlar kanıt taşıyor"),
        }
    }

    #[test]
    fn metadata_fields_cannot_inflate_score() {
        let engine = UncertaintyEngine::new(uuid::Uuid::new_v4(), vec!["vec".to_string()]);
        // Metadata + duvar saati alanları ADAY kümesine girmez: skor yalnız
        // gerçek kanıt alanından ölçülür (1/1 -> 100), metadata şişirmez.
        let data = serde_json::json!({
            "vec": { "depth": 0.9 },
            "model": "gpt-x", "provider": "openrouter", "duration_ms": 12,
            "task_id": "t-1", "computed_at": "2026-09-23T12:00:00Z", "version": "v1"
        });
        match engine.evaluate(&data).unwrap() {
            ConfidenceLevel::Pass(e) => assert_eq!(e.score, 100),
            ConfidenceLevel::Halt(_) => panic!("kanıt var"),
        }

        // Aynı payload'a placeholder eklenirse skor DÜŞER (metadata korumaz):
        let data2 = serde_json::json!({
            "vec": { "depth": 0.9 },
            "model": "gpt-x",
            "note": "veri yok"
        });
        match engine.evaluate(&data2).unwrap() {
            ConfidenceLevel::Pass(e) => assert_eq!(e.score, 50),
            ConfidenceLevel::Halt(_) => panic!("zorunlu alan kanıt taşıyor"),
        }
    }

    #[test]
    fn no_candidate_field_scores_zero_not_hundred() {
        // Zorunlu alan yoksa gate PASS der ama ÖLÇÜLECEK kanıt da yoktur:
        // dürüst skor 0'dır (eski hâlde 100 olurdu).
        let engine = UncertaintyEngine::new(uuid::Uuid::new_v4(), vec![]);
        let data = serde_json::json!({ "model": "gpt-x", "duration_ms": 5 });
        match engine.evaluate(&data).unwrap() {
            ConfidenceLevel::Pass(e) => assert_eq!(e.score, 0),
            ConfidenceLevel::Halt(_) => panic!("zorunlu alan yok -> HALT olmamalı"),
        }
    }

    #[test]
    fn data_score_is_a_pure_measured_ratio() {
        let mut map = serde_json::Map::new();
        map.insert("a".to_string(), serde_json::json!("somut kanıt"));
        map.insert("b".to_string(), serde_json::json!("unknown"));
        map.insert("c".to_string(), serde_json::json!(null));
        map.insert("d".to_string(), serde_json::json!(0.42));
        // aday: a,b,c,d (4); kanıt: a,d (2) -> 50
        assert_eq!(UncertaintyEngine::data_score(&map), 50);

        let empty = serde_json::Map::new();
        assert_eq!(UncertaintyEngine::data_score(&empty), 0);
    }

    #[test]
    fn test_valid_evidence_passes() {
        let engine = UncertaintyEngine::new(
            uuid::Uuid::new_v4(),
            vec!["vector".to_string(), "anchors".to_string()],
        );
        let data = serde_json::json!({
            "vector": { "depth": 0.9, "energy": 0.4 },
            "anchors": ["ritüel uyumu"]
        });
        match engine.evaluate(&data).unwrap() {
            ConfidenceLevel::Pass(e) => assert_eq!(e.score, 100),
            ConfidenceLevel::Halt(_) => panic!("geçerli kanıt HALT olamaz"),
        }
    }
}
