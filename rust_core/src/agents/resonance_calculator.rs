//! ResonanceCalculator — iki GERÇEK profil vektörü arasındaki rezonans.
//!
//! [003]/[004]/[005] fix (Python [032] sözleşmesine eşitleme):
//! - Eski gövde input'taki vektörleri HİÇ kullanmıyor, kendi sabit
//!   depth=0.9/0.8 vektörlerini yaratıp cosine(0.9, 0.8) hesaplıyordu.
//! - recommended_approach literal "APPROACH", red_flags hep boş,
//!   hash literal "res_hash", süre literal 50ms, confidence literal 1.0 idi.
//! Yeni sözleşme: gerçek vektör -> doğrulama (boyut/tip/aralık) -> cosine ->
//! gerçek eşiklerden yaklaşım -> gerçek uyumsuzluk bayrakları -> SHA-256 +
//! gerçek süre + türetilmiş güven.

use crate::agent_pipeline::{AgentNode, AnalysisResult, HaltReason};
use crate::event_bus::{AgentEvent, EventBus, Severity};
use crate::uncertainty::{ConfidenceLevel, UncertaintyEngine};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;
use uuid::Uuid;

#[derive(Debug, Serialize, Deserialize)]
pub struct ResonanceProfile {
    pub compatibility_score: f32,
    pub frequency_match: HashMap<String, f32>,
    pub recommended_approach: String,
    pub red_flags: Vec<String>,
}

/// Vektör boyutlarının geçerli değer aralığı ([032] Python sözleşmesi: 0.1-1.0).
const DIM_MIN: f64 = 0.0;
const DIM_MAX: f64 = 1.0;

pub struct ResonanceCalculator {
    event_bus: Arc<EventBus>,
}

impl ResonanceCalculator {
    pub fn new(event_bus: Arc<EventBus>) -> Self {
        Self { event_bus }
    }

    /// Input JSON'dan sayısal vektör çıkarır; tip/aralık doğrulaması yapar.
    /// Uygun vektör yoksa None — asla nötr/sabit vektör ÜRETİLMEZ ([003]).
    fn extract_vector(value: &Value) -> Option<HashMap<String, f64>> {
        let obj = value.as_object()?;
        let mut out = HashMap::new();
        for (k, v) in obj {
            let num = v.as_f64()?;
            if !num.is_finite() || num < DIM_MIN || num > DIM_MAX {
                return None;
            }
            out.insert(k.clone(), num);
        }
        if out.is_empty() {
            return None;
        }
        // Zorunlu boyutlar ([032]): depth ve energy gerçek sayı olmalı.
        if !out.contains_key("depth") || !out.contains_key("energy") {
            return None;
        }
        Some(out)
    }

    fn cosine_similarity(vec1: &HashMap<String, f64>, vec2: &HashMap<String, f64>) -> Option<f64> {
        let mut dot_product = 0.0;
        let mut mag1 = 0.0;
        let mut mag2 = 0.0;
        let mut has_common = false;

        for (k, v1) in vec1 {
            mag1 += v1 * v1;
            if let Some(v2) = vec2.get(k) {
                dot_product += v1 * v2;
                has_common = true;
            }
        }

        for v2 in vec2.values() {
            mag2 += v2 * v2;
        }

        if !has_common {
            return None;
        }

        let mag1 = mag1.sqrt();
        let mag2 = mag2.sqrt();
        if mag1 == 0.0 || mag2 == 0.0 {
            // [032]: sıfır magnitude ölçüm değildir; hesap YAPILAMAZ.
            return None;
        }
        Some(dot_product / (mag1 * mag2))
    }

    /// [033 eşitleme]: bayraklar gerçek boyut farklarından üretilir.
    fn detect_red_flags(user: &HashMap<String, f64>, target: &HashMap<String, f64>) -> Vec<String> {
        let mut flags = Vec::new();
        if let (Some(u), Some(t)) = (user.get("depth"), target.get("depth")) {
            if (u - t).abs() > 0.35 {
                flags.push("DERINLIK_UYUSMAZLIGI".to_string());
            }
        }
        if let (Some(u), Some(t)) = (user.get("energy"), target.get("energy")) {
            if *u < 0.3 && *t > 0.8 {
                flags.push("ENERJI_UYUSMAZLIĞI".to_string());
            }
        }
        flags
    }

    /// [042/005 sınıfı]: SHA-256 telemetri hash'i.
    fn sha256_hex(text: &str) -> String {
        use sha2::Digest;
        let mut hasher = sha2::Sha256::new();
        hasher.update(text.as_bytes());
        format!("{:x}", hasher.finalize())
    }
}

#[async_trait]
impl AgentNode for ResonanceCalculator {
    fn name(&self) -> &'static str {
        "ResonanceCalculator"
    }

    async fn execute(&self, input: &str) -> Result<AnalysisResult, HaltReason> {
        let task_id = Uuid::new_v4();
        let started = std::time::Instant::now();

        let _ = self.event_bus.publish(AgentEvent::TaskStarted {
            task_id,
            agent_name: self.name().to_string(),
            input_summary: "Matematiksel rezonans başlatıldı (gerçek vektörler)".to_string(),
        });

        let input_data: Value = serde_json::from_str(input)
            .map_err(|e| HaltReason::LlmParseError(format!("Invalid input JSON: {}", e)))?;

        let required_fields = vec![
            "user_authentic_vector".to_string(),
            "target_analysis_vector".to_string(),
        ];

        let engine = UncertaintyEngine::new(task_id, required_fields);

        match engine.evaluate(&input_data) {
            Ok(ConfidenceLevel::Halt(evidence)) => {
                let error_msg = format!("Eksik veri: {:?}", evidence.missing_fields);
                let _ = self.event_bus.publish(AgentEvent::ErrorHalt {
                    task_id,
                    agent_name: self.name().to_string(),
                    error_code: "HALT_NO_VECTORS".to_string(),
                    error_message: error_msg.clone(),
                    severity: Severity::Critical,
                });
                return Err(HaltReason::UncertaintyHalt(error_msg));
            }
            Ok(ConfidenceLevel::Pass(_)) => {
                let _ = self.event_bus.publish(AgentEvent::StepCompleted {
                    task_id,
                    agent_name: self.name().to_string(),
                    step_name: "Uncertainty_Check_Passed".to_string(),
                    output_hash: Self::sha256_hex(input),
                });
            }
            Err(e) => {
                return Err(HaltReason::LlmParseError(e.to_string()));
            }
        }

        // [003] fix: GERÇEK input vektörleri; uygun değilse HALT (sabit üretme).
        let user_vec = match Self::extract_vector(&input_data["user_authentic_vector"]) {
            Some(v) => v,
            None => {
                let reason =
                    "Kullanıcı authentic vector'u geçersiz (boş/boyut eksik/aralık dışı); \
                              sabit vektör ÜRETİLMEZ"
                        .to_string();
                let _ = self.event_bus.publish(AgentEvent::ErrorHalt {
                    task_id,
                    agent_name: self.name().to_string(),
                    error_code: "HALT_INVALID_USER_VECTOR".to_string(),
                    error_message: reason.clone(),
                    severity: Severity::Critical,
                });
                return Err(HaltReason::UncertaintyHalt(reason));
            }
        };

        let target_vec = match Self::extract_vector(&input_data["target_analysis_vector"]) {
            Some(v) => v,
            None => {
                let reason = "Hedef authentic vector'u geçersiz (boş/boyut eksik/aralık dışı); \
                              sabit vektör ÜRETİLMEZ"
                    .to_string();
                let _ = self.event_bus.publish(AgentEvent::ErrorHalt {
                    task_id,
                    agent_name: self.name().to_string(),
                    error_code: "HALT_INVALID_TARGET_VECTOR".to_string(),
                    error_message: reason.clone(),
                    severity: Severity::Critical,
                });
                return Err(HaltReason::UncertaintyHalt(reason));
            }
        };

        let similarity = match Self::cosine_similarity(&user_vec, &target_vec) {
            Some(s) => s as f32,
            None => {
                let reason =
                    "Vektörlerde ortak boyut yok veya magnitude sıfır; hesap YAPILAMAZ".to_string();
                let _ = self.event_bus.publish(AgentEvent::ErrorHalt {
                    task_id,
                    agent_name: self.name().to_string(),
                    error_code: "HALT_DEGENERATE_VECTORS".to_string(),
                    error_message: reason.clone(),
                    severity: Severity::Critical,
                });
                return Err(HaltReason::UncertaintyHalt(reason));
            }
        };

        // [004] fix: yaklaşım gerçek similarity eşiklerinden ([032 ile aynı).
        let approach = if similarity > 0.85 {
            "ATOMIK_REZONANS - Derin bağlantı mümkün"
        } else if similarity > 0.70 {
            "YUKSEK_UYUM - Güçlü çekim alanı"
        } else if similarity > 0.50 {
            "ORTA_FREKANS - Dikkatli yaklaşım"
        } else {
            "FREKANS_UYUSMAZLIGI - Sistem kapat, yeni hedef"
        };

        // [004] fix: boyut bazlı gerçek eşleşme dökümü.
        let mut freq_match = HashMap::new();
        freq_match.insert("overall_match".to_string(), similarity);
        if let (Some(u), Some(t)) = (user_vec.get("depth"), target_vec.get("depth")) {
            freq_match.insert("depth_match".to_string(), (1.0 - (u - t).abs()) as f32);
        }
        if let (Some(u), Some(t)) = (user_vec.get("energy"), target_vec.get("energy")) {
            freq_match.insert("energy_match".to_string(), (1.0 - (u - t).abs()) as f32);
        }

        let profile = ResonanceProfile {
            compatibility_score: similarity,
            frequency_match: freq_match,
            recommended_approach: approach.to_string(),
            red_flags: Self::detect_red_flags(&user_vec, &target_vec),
        };

        let payload = serde_json::to_string(&profile)
            .map_err(|e| HaltReason::LlmParseError(e.to_string()))?;

        // [005] fix: gerçek hash + gerçek süre.
        let _ = self.event_bus.publish(AgentEvent::TaskCompleted {
            task_id,
            agent_name: self.name().to_string(),
            final_result_hash: Self::sha256_hex(&payload),
            duration_ms: started.elapsed().as_millis() as u64,
        });

        // [005] fix: confidence literal 1.0 değil — kanıt kapsamından türetilir:
        // zorunlu 2 boyut + katkıda bulunan ek boyutların oranı.
        let required_present = 2.0f32;
        let extra = user_vec
            .keys()
            .filter(|k| target_vec.contains_key(*k) && **k != "depth" && **k != "energy")
            .count() as f32;
        let confidence = ((required_present + extra.min(2.0)) / 4.0).clamp(0.0, 1.0);

        Ok(AnalysisResult {
            confidence,
            payload,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::event_bus::EventBus;
    use std::sync::Arc;

    fn input_json(
        user_depth: f64,
        user_energy: f64,
        target_depth: f64,
        target_energy: f64,
    ) -> String {
        serde_json::json!({
            "user_authentic_vector": { "depth": user_depth, "energy": user_energy },
            "target_analysis_vector": { "depth": target_depth, "energy": target_energy }
        })
        .to_string()
    }

    fn calc() -> ResonanceCalculator {
        ResonanceCalculator::new(Arc::new(EventBus::new(16)))
    }

    #[tokio::test]
    async fn test_similarity_depends_on_real_input() {
        // [003] sözleşme: aynı kod, farklı girdi -> FARKLI sonuç.
        let near = calc()
            .execute(&input_json(0.9, 0.5, 0.9, 0.5))
            .await
            .unwrap();
        let far = calc()
            .execute(&input_json(0.1, 0.9, 0.9, 0.1))
            .await
            .unwrap();

        let near_profile: ResonanceProfile = serde_json::from_str(&near.payload).unwrap();
        let far_profile: ResonanceProfile = serde_json::from_str(&far.payload).unwrap();

        assert!(near_profile.compatibility_score > far_profile.compatibility_score);
        assert!(near_profile.compatibility_score > 0.99); // özdeş vektörler
        assert!(far_profile.compatibility_score < 0.5);
        // [004]: yaklaşım literal değil, eşikten türetiliyor
        assert!(near_profile
            .recommended_approach
            .contains("ATOMIK_REZONANS"));
        assert!(far_profile
            .recommended_approach
            .contains("FREKANS_UYUSMAZLIGI"));
    }

    #[tokio::test]
    async fn test_depth_mismatch_red_flag_produced() {
        // [033 eşitleme]: derinlik bayrağı gerçek farktan üretilir.
        let result = calc()
            .execute(&input_json(0.9, 0.5, 0.2, 0.5))
            .await
            .unwrap();
        let profile: ResonanceProfile = serde_json::from_str(&result.payload).unwrap();
        assert!(profile
            .red_flags
            .contains(&"DERINLIK_UYUSMAZLIGI".to_string()));
    }

    #[tokio::test]
    async fn test_invalid_vector_halts_instead_of_fabricating() {
        // [003]: aralık dışı boyut -> HALT; sabit 0.9/0.8 ÜRETİLMEZ.
        let bad = serde_json::json!({
            "user_authentic_vector": { "depth": -10.0, "energy": 0.5 },
            "target_analysis_vector": { "depth": 0.5, "energy": 0.5 }
        })
        .to_string();
        match calc().execute(&bad).await {
            Err(HaltReason::UncertaintyHalt(msg)) => {
                assert!(msg.contains("geçersiz"), "açlayıcı halt mesajı: {}", msg);
            }
            other => panic!("HALT beklenirdi, geldi: {:?}", other.map(|r| r.payload)),
        }
    }

    #[tokio::test]
    async fn test_confidence_is_derived_not_literal_one() {
        // Yalnızca 2 zorunlu boyut: güven 0.5 (literal 1.0 değil).
        let result = calc()
            .execute(&input_json(0.6, 0.5, 0.7, 0.5))
            .await
            .unwrap();
        assert!((result.confidence - 0.5).abs() < 1e-6);
    }
}
