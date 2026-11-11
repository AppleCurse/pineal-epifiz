use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::agent_pipeline::{AgentNode, AnalysisResult, HaltReason};
use crate::event_bus::{AgentEvent, EventBus};
use crate::uncertainty::{ConfidenceLevel, UncertaintyEngine};
use sha2::Digest;
use uuid::Uuid;

/// Mirror Reflection (Hedefin Çıktısı)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MirrorReflection {
    pub user_core_frequency: String,
    pub surface_persona: String,
    pub alignment_score: f32,
    pub authentic_anchors: Vec<String>,
}

pub struct MirrorTruthAgent {
    event_bus: EventBus,
}

impl MirrorTruthAgent {
    pub fn new(event_bus: EventBus) -> Self {
        Self { event_bus }
    }

    /// LLM API Çağrısı.
    ///
    /// [041] fix: eski gövde HTTP çağrısı YOKKEN prompt'ta "kitap/kahve"
    /// geçip geçmediğine bakıp SABİT JSON (alignment_score=0.88, sabit
    /// anchor'lar) döndürüyordu — sahte LLM. Rust tarafında yapılandırılmış
    /// gerçek istemci olmadığı sürece dürüstçe REDDEDİLİR; sahte yansıma
    /// ÜRETİLMEZ. (Gerçek analiz yolu: scripts/run_task.py -> Python
    /// MirrorOfTruth, [W4.2].)
    async fn call_llm(&self, _prompt: &str) -> Result<String, String> {
        Err(
            "LLM_UNAVAILABLE: Rust ajanında yapılandırılmış gerçek LLM istemcisi \
             yok; sahte MirrorReflection ÜRETİLMEZ"
                .to_string(),
        )
    }
}

#[async_trait]
impl AgentNode for MirrorTruthAgent {
    fn name(&self) -> &'static str {
        "MirrorOfTruth"
    }

    async fn execute(&self, input: &str) -> Result<AnalysisResult, HaltReason> {
        let task_id = Uuid::new_v4();

        // 1. Ajan Başladı Eventi
        let _ = self.event_bus.publish(AgentEvent::TaskStarted {
            task_id,
            agent_name: self.name().to_string(),
            input_summary: "Kullanıcı profil verisi alındı".to_string(),
        });

        // 2. Gelen JSON'u parse et
        let input_data: Value = serde_json::from_str(input)
            .map_err(|e| HaltReason::LlmParseError(format!("Invalid input JSON: {}", e)))?;

        // 3. Prompt oluştur
        let rituals = input_data.get("private_rituals").unwrap_or(&Value::Null);
        let prompt = format!(
            "Sen 'Mirror of Truth' ajanısın. Görevin, verilen kullanıcı verisinden yüzey kimliğini ve gerçek (core) frekansı bulmak.\nRitüeller: {}",
            rituals
        );

        // 4. LLM Çağrısı ([041]: başarısızlık yutulmaz, dürüst HALT olarak yükselir)
        let llm_json_str = match self.call_llm(&prompt).await {
            Ok(text) => text,
            Err(reason) => {
                let _ = self.event_bus.publish(AgentEvent::ErrorHalt {
                    task_id,
                    agent_name: self.name().to_string(),
                    error_code: "LLM_UNAVAILABLE".to_string(),
                    error_message: reason.clone(),
                    severity: crate::event_bus::Severity::Critical,
                });
                return Err(HaltReason::InsufficientEvidence(reason));
            }
        };

        // 5. UNCERTAINTY ENGINE: LLM Halüsinasyon Kontrolü
        let required_fields = vec![
            "user_core_frequency".to_string(),
            "surface_persona".to_string(),
            "alignment_score".to_string(),
            "authentic_anchors".to_string(),
        ];

        let engine = UncertaintyEngine::new(task_id, required_fields);

        // JSON'u Deserialize edelim
        let llm_data: Value = serde_json::from_str(&llm_json_str)
            .map_err(|e| HaltReason::LlmParseError(format!("LLM dönen JSON hatalı: {}", e)))?;

        // Fail-Fast Kontrolü
        match engine.evaluate(&llm_data) {
            Ok(ConfidenceLevel::Halt(evidence)) => {
                // EKSİK VERİ VAR - SİSTEMİ DURDUR!
                let error_msg = format!("LLM eksik veri döndü: {:?}", evidence.missing_fields);

                let _ = self.event_bus.publish(AgentEvent::ErrorHalt {
                    task_id,
                    agent_name: self.name().to_string(),
                    error_code: "UNCERTAINTY_HALT".to_string(),
                    error_message: error_msg.clone(),
                    severity: crate::event_bus::Severity::Critical,
                });

                return Err(HaltReason::UncertaintyHalt(error_msg));
            }
            Ok(ConfidenceLevel::Pass(_evidence)) => {
                // BAŞARILI
                let _ = self.event_bus.publish(AgentEvent::StepCompleted {
                    task_id,
                    agent_name: self.name().to_string(),
                    step_name: "Uncertainty_Check_Passed".to_string(),
                    output_hash: format!("{}:{}:uncertainty_pass", task_id, self.name()),
                });
            }
            Err(e) => {
                return Err(HaltReason::LlmParseError(e.to_string()));
            }
        }

        // Parse to Struct
        let reflection: MirrorReflection = engine
            .parse_llm_response(&llm_json_str)
            .map_err(|e| HaltReason::LlmParseError(e.to_string()))?;

        // [042] fix: gerçek süre, gerçek hash (SHA-256), türetilmiş güven.
        let started = std::time::Instant::now();
        let payload = serde_json::to_string(&reflection).unwrap();
        let mut hasher = sha2::Sha256::new();
        hasher.update(payload.as_bytes());
        let result_hash = format!("{:x}", hasher.finalize());

        let _ = self.event_bus.publish(AgentEvent::TaskCompleted {
            task_id,
            agent_name: self.name().to_string(),
            final_result_hash: result_hash,
            duration_ms: started.elapsed().as_millis() as u64,
        });

        // Güven sabit 0.95 DEĞİL: uncertainty kanıt skorundan türetilir.
        // [RÖNTGEN §8.5] `Evidence.score` artık SABİT 100 değil, ÖLÇÜLMÜŞ kanıt
        // kalitesi (kanıt taşıyan alan / aday alan, metadata hariç). Yani bu
        // güven de ölçümden gelir: placeholder/metadata şişkin bir payload
        // PASS etse bile güven 1.0 olamaz.
        let confidence = match engine.evaluate(&llm_data) {
            Ok(ConfidenceLevel::Pass(evidence)) => evidence.score as f32 / 100.0,
            _ => 0.0,
        };

        Ok(AnalysisResult {
            confidence,
            payload,
        })
    }
}
