use crate::agent_pipeline::{AgentNode, AnalysisResult, HaltReason};
use crate::event_bus::{AgentEvent, EventBus, Severity};
use crate::uncertainty::{ConfidenceLevel, UncertaintyEngine};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::Arc;
use uuid::Uuid;

#[derive(Debug, Serialize, Deserialize)]
pub struct Claim {
    pub claim_text: String,
    pub category: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct VerificationResult {
    pub claim_text: String,
    pub truth_status: String,
    pub evidence_url: String,
    pub contradiction_detail: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct VerifierReport {
    pub verifications: Vec<VerificationResult>,
    /// DOĞRULANMIŞ iddia oranı (confirmed/total) — Python sözleşmesiyle aynı
    /// (agent_core/agents/autonomous_verifier.py). Eski kod burada
    /// `verifications.len() / 3.0` yazıyordu: üç arama SONUCU döndüğünde,
    /// tek bir iddia bile eşleştirilmemişken "otantiklik 1.0" üretiliyordu.
    /// Teminat (kaç kaynak çekildi) kanıt DEĞİLDİR.
    pub overall_authenticity_score: f32,
    /// Arama teminatı ölçüsü (dönen kaynak / hedef 3). Otantiklik skoruyla
    /// karıştırılmaması için AYRI alandır.
    pub evidence_coverage: f32,
    /// Rapor hükmü. Rust hattında jüri + kanıt kapısı (entailment) YOKTUR;
    /// bu yüzden buradan asla "VERIFIED" çıkamaz.
    pub status: String,
}

/// Deterministik otantiklik skoru: yalnız DOĞRULANMIŞ iddialar sayılır.
/// `total == 0` -> 0.0 (kanıt yoksa skor da yok). Çekilen kaynak SAYISI skoru
/// asla yükseltmez.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TruthStatus {
    Verified,
    Unverified,
}

fn normalize_truth_status(value: &str) -> TruthStatus {
    match value.trim().to_ascii_uppercase().as_str() {
        "VERIFIED" | "DOĞRULANDI" => TruthStatus::Verified,
        _ => TruthStatus::Unverified,
    }
}

pub fn authenticity_score(confirmed: usize, total: usize) -> f32 {
    if total == 0 {
        0.0
    } else {
        confirmed as f32 / total as f32
    }
}

pub struct AutonomousVerifier {
    event_bus: Arc<EventBus>,
    tavily_key: Option<String>,
}

/// [048] fix: adli telemetri hash'i SHA-256 (MD5 değil).
fn sha256_hex(text: &str) -> String {
    use sha2::Digest;
    let mut hasher = sha2::Sha256::new();
    hasher.update(text.as_bytes());
    format!("{:x}", hasher.finalize())
}

impl AutonomousVerifier {
    pub fn new(event_bus: Arc<EventBus>, tavily_key: Option<String>) -> Self {
        Self {
            event_bus,
            tavily_key,
        }
    }
}

#[async_trait]
impl AgentNode for AutonomousVerifier {
    fn name(&self) -> &'static str {
        "AutonomousVerifier"
    }

    async fn execute(&self, input: &str) -> Result<AnalysisResult, HaltReason> {
        let task_id = Uuid::new_v4();
        let started = std::time::Instant::now();

        let _ = self.event_bus.publish(AgentEvent::TaskStarted {
            task_id,
            agent_name: self.name().to_string(),
            input_summary: "Web teyidi başlatıldı".to_string(),
        });

        if self.tavily_key.is_none() {
            let error_msg = "Eksik arama motoru anahtarı (Tavily)".to_string();
            let _ = self.event_bus.publish(AgentEvent::ErrorHalt {
                task_id,
                agent_name: self.name().to_string(),
                error_code: "HALT_NO_TAVILY".to_string(),
                error_message: error_msg.clone(),
                severity: Severity::Critical,
            });
            return Err(HaltReason::InsufficientEvidence(error_msg));
        }

        let input_data: Value = serde_json::from_str(input)
            .map_err(|e| HaltReason::LlmParseError(format!("Invalid input JSON: {}", e)))?;

        let tavily_api_key = self.tavily_key.as_ref().unwrap();
        let target_bio = input_data
            .get("target_profile")
            .and_then(|p| p.get("bio"))
            .and_then(|b| b.as_str())
            .unwrap_or("");

        // [043] fix: eski davranış fail-open'di — HTTP tamamen başarısız olsa
        // bile overall_score=1.0 kalıyordu (SIFIR kanıtla %100 otantiklik) ve
        // her arama sonucu koşulsuz "DOĞRULANDI" etiketi alıyordu (claim
        // eşleşmesi yok). Yeni sözleşme:
        //   - arama sonuçları yalnızca KAYNAK olarak kaydedilir (UNVERIFIED);
        //     gerçek claim eşleşmesi implemente edilmeden DOĞRULANDI DENMEZ
        //   - sağlayıcı/HTTP/parse hatası sessizce yutulmaz, kayda geçer
        //   - skor TEMİNAT ölçüsüdür (3 sonuç hedefine ulaşma oranı)
        let mut verifications = Vec::new();
        let mut failure_reason: Option<String> = None;

        if target_bio.is_empty() {
            failure_reason =
                Some("Hedef bio kanıtı yok; teyit edilecek iddia bulunamadı".to_string());
        } else {
            let client = reqwest::Client::new();
            let search_body = serde_json::json!({
                "api_key": tavily_api_key,
                "query": target_bio,
                "max_results": 3
            });

            match client
                .post("https://api.tavily.com/search")
                .json(&search_body)
                .send()
                .await
            {
                Ok(res) => match res.json::<Value>().await {
                    Ok(search_json) => {
                        if let Some(results) = search_json.get("results").and_then(|r| r.as_array())
                        {
                            for item in results {
                                let title = item
                                    .get("title")
                                    .and_then(|t| t.as_str())
                                    .unwrap_or("Bilinmeyen")
                                    .to_string();
                                let url = item
                                    .get("url")
                                    .and_then(|u| u.as_str())
                                    .unwrap_or("")
                                    .to_string();
                                let snippet = item
                                    .get("content")
                                    .and_then(|s| s.as_str())
                                    .unwrap_or("")
                                    .to_string();
                                verifications.push(VerificationResult {
                                    claim_text: title,
                                    truth_status: "UNVERIFIED".to_string(),
                                    evidence_url: url,
                                    contradiction_detail: snippet,
                                });
                            }
                            if verifications.is_empty() {
                                failure_reason = Some("Arama sonuç döndürmedi".to_string());
                            }
                        } else {
                            failure_reason =
                                Some("Arama yanıtı 'results' alanı içermiyor".to_string());
                        }
                    }
                    Err(e) => failure_reason = Some(format!("Arama yanıtı parse edilemedi: {}", e)),
                },
                Err(e) => failure_reason = Some(format!("Arama sağlayıcısına ulaşılamadı: {}", e)),
            }
        }

        if let Some(reason) = &failure_reason {
            tracing::warn!("[AutonomousVerifier] {}", reason);
        }

        // [RÖNTGEN 2026-09-23] Skor sözleşmesi Python ile aynı hâle getirildi:
        //   overall_authenticity_score = doğrulanmış iddia / toplam iddia
        //   evidence_coverage          = dönen kaynak / hedef (yalnız teminat)
        // Rust hattı iddia eşleştirmesi YAPMAZ (tüm kayıtlar UNVERIFIED), yani
        // bu skor bugün daima 0.0'dır ve aşağıdaki kanıt kapısı görevi durdurur.
        let source_count = verifications.len();
        let confirmed = verifications
            .iter()
            .filter(|v| normalize_truth_status(&v.truth_status) == TruthStatus::Verified)
            .count();
        let overall_score = authenticity_score(confirmed, verifications.len());
        let evidence_coverage = (verifications.len() as f32 / 3.0).min(1.0);
        let status = if confirmed > 0 && confirmed == verifications.len() {
            "VERIFIED".to_string()
        } else {
            "UNVERIFIED".to_string()
        };

        let report = VerifierReport {
            verifications,
            overall_authenticity_score: overall_score,
            evidence_coverage,
            status,
        };

        // KANIT KAPISI (fail-closed, Python parity): doğrulanmış iddia yoksa
        // hüküm üretilemez. Teminat (çekilen kaynak sayısı) onay sayılmaz.
        if confirmed == 0 {
            let reason = format!(
                "DOĞRULANMIŞ iddia yok: {} kaynak çekildi ama hiçbiri bir iddiayla \
                 eşleştirilmedi (Rust hattında jüri/entailment katmanı yoktur)",
                source_count
            );
            tracing::warn!("[AutonomousVerifier] {}", reason);
            let _ = self.event_bus.publish(AgentEvent::ErrorHalt {
                task_id,
                agent_name: self.name().to_string(),
                error_code: "NO_VERIFIED_CLAIM".to_string(),
                error_message: reason.clone(),
                severity: Severity::Critical,
            });
            return Err(HaltReason::InsufficientEvidence(reason));
        }

        let llm_json_str = serde_json::to_string(&report).unwrap();

        let required_fields = vec![
            "verifications".to_string(),
            "overall_authenticity_score".to_string(),
            "evidence_coverage".to_string(),
            "status".to_string(),
        ];

        let engine = UncertaintyEngine::new(task_id, required_fields);

        let llm_data: Value = serde_json::from_str(&llm_json_str)
            .map_err(|e| HaltReason::LlmParseError(format!("LLM dönen JSON hatalı: {}", e)))?;

        match engine.evaluate(&llm_data) {
            Ok(ConfidenceLevel::Halt(evidence)) => {
                let error_msg = format!("LLM eksik veri döndü: {:?}", evidence.missing_fields);
                let _ = self.event_bus.publish(AgentEvent::ErrorHalt {
                    task_id,
                    agent_name: self.name().to_string(),
                    error_code: "UNCERTAINTY_HALT".to_string(),
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
                    output_hash: sha256_hex(&llm_json_str),
                });
            }
            Err(e) => {
                return Err(HaltReason::LlmParseError(e.to_string()));
            }
        }

        let _ = self.event_bus.publish(AgentEvent::TaskCompleted {
            task_id,
            agent_name: self.name().to_string(),
            final_result_hash: sha256_hex(&llm_json_str),
            duration_ms: started.elapsed().as_millis() as u64,
        });

        Ok(AnalysisResult {
            // Güven = doğrulanmış iddia oranı (teminat değil).
            confidence: overall_score,
            payload: llm_json_str,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Skor TEMİNAT değil DOĞRULAMA ölçüsüdür: üç kaynak çekmek skoru 1.0
    /// yapmaz (eski kusur), doğrulanmış iddia oranı yapar.
    #[test]
    fn authenticity_score_is_confirmed_ratio_not_fetch_coverage() {
        assert_eq!(authenticity_score(0, 0), 0.0);
        assert_eq!(authenticity_score(0, 3), 0.0);
        assert_eq!(authenticity_score(1, 2), 0.5);
        assert_eq!(authenticity_score(3, 3), 1.0);
    }

    #[test]
    fn report_never_claims_verified_without_confirmed_claims() {
        let report = VerifierReport {
            verifications: vec![VerificationResult {
                claim_text: "başlık".to_string(),
                truth_status: "UNVERIFIED".to_string(),
                evidence_url: "https://kaynak.test".to_string(),
                contradiction_detail: "snippet".to_string(),
            }],
            overall_authenticity_score: authenticity_score(0, 1),
            evidence_coverage: 1.0 / 3.0,
            status: "UNVERIFIED".to_string(),
        };
        assert_eq!(report.status, "UNVERIFIED");
        assert_eq!(report.overall_authenticity_score, 0.0);
        // Teminat ile otantiklik skoru ayrı alanlardır (karıştırılamaz).
        assert!(report.evidence_coverage > report.overall_authenticity_score);
    }

    #[test]
    fn truth_status_normalization_does_not_promote_unverified_sources() {
        assert_eq!(
            normalize_truth_status("UNVERIFIED"),
            TruthStatus::Unverified
        );
        assert_eq!(normalize_truth_status("VERIFIED"), TruthStatus::Verified);
        assert_eq!(normalize_truth_status("DOĞRULANDI"), TruthStatus::Verified);
    }
}
