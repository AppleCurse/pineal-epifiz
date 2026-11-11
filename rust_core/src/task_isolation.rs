//! [W4.2] TaskManager — Rust/Tauri tarafının tek görev girişi.
//!
//! Eski zincir ([001]/[002]/[049]) iki adımda ölüydü:
//!   1) scraper.py → X-unsupported → her girişte exit 1
//!   2) agent_core.agents.rust_bridge_agent → modül HİÇ YOK
//!
//! Yeni sözleşme: TEK subprocess — `python3 scripts/run_task.py`.
//! Platform kararı (instagram/x/unsupported_web) Python tarafındaki tek
//! sahiplikli platform_registry'de verilir ([023]); Rust'ta ikinci bir
//! karar katmanı YARATILMAZ ([009] duplication dersi).
//!
//! Güvenlik/süreç sözleşmesi:
//! - Veri stdin JSON olarak geçilir; script metnine/komut satırına ASLA
//!   gömülmez ([045] enjeksiyon dersi, [046] anahtar sızıntısı dersi).
//! - kill_on_drop + timeout: takılan süreç öldürülür, Tauri command asılı kalmaz.
//! - Telemetri hash'i stdout'un SHA-256'sıdır; StepCompleted/TaskCompleted
//!   AYNI hash'i paylaşır ([048]: MD5 + çift-kaynak tutarsızlığı kaldırıldı).

use crate::event_bus::{AgentEvent, EventBus, Severity};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tokio::io::AsyncWriteExt;
use tokio::process::Command;
use uuid::Uuid;

/// Alt süreç için üst sınır: uzun bir gerçek analiz (playwright + ajan zinciri)
/// için cömert, sonsuz bekleme değil.
const TASK_TIMEOUT_SECS: u64 = 900;

#[derive(Debug, Clone)]
pub struct TaskContext {
    pub task_id: Uuid,
    pub state: HashMap<String, String>,
}

pub struct TaskManager {
    tasks: Arc<Mutex<HashMap<Uuid, TaskContext>>>,
    event_bus: Arc<EventBus>,
    python_path: String,
    task_script: String,
}

fn default_python() -> String {
    if let Ok(py) = std::env::var("PINEAL_PYTHON") {
        return py;
    }
    if cfg!(windows) {
        "python".to_string()
    } else {
        "python3".to_string()
    }
}

fn project_root() -> String {
    if let Ok(root) = std::env::var("PINEAL_PROJECT_ROOT") {
        return root;
    }
    if let Ok(manifest) = std::env::var("CARGO_MANIFEST_DIR") {
        if let Some(parent) = std::path::Path::new(&manifest).parent() {
            return parent.to_string_lossy().to_string();
        }
    }
    std::env::current_dir()
        .map(|d| d.to_string_lossy().to_string())
        .unwrap_or_else(|_| ".".to_string())
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

/// UTF-8 char-boundary güvenli kısaltma (Türkçe metinlerde byte-slice PANİK eder).
fn head(s: &str, n: usize) -> String {
    s.chars().take(n).collect()
}

impl TaskManager {
    pub fn new(event_bus: Arc<EventBus>) -> Self {
        let root = project_root();
        Self {
            tasks: Arc::new(Mutex::new(HashMap::new())),
            event_bus,
            python_path: default_python(),
            task_script: format!("{}/scripts/run_task.py", root),
        }
    }

    pub fn create_task(&self) -> Uuid {
        let task_id = Uuid::new_v4();
        let ctx = TaskContext {
            task_id,
            state: HashMap::new(),
        };
        self.tasks.lock().unwrap().insert(task_id, ctx);
        task_id
    }

    pub fn get_task(&self, task_id: &Uuid) -> Option<TaskContext> {
        self.tasks.lock().unwrap().get(task_id).cloned()
    }

    /// [049] fix: haritadan temizlik — task kayıtları sonsuz büyümez.
    fn finish_task(&self, task_id: &Uuid) {
        self.tasks.lock().unwrap().remove(task_id);
    }

    /// Tek girişli analiz zinciri: scripts/run_task.py (gerçek PinealExecutor).
    ///
    /// Çıkış kodu sözleşmesi (run_task.py):
    ///   0 = pipeline koştu (TaskStatus JSON; halted_* dürüst duraklar dahil)
    ///   2 = platform desteklenmiyor / yetki bekleniyor
    ///   3 = kazıma kanıt üretemedi
    ///   4 = iç hata
    pub async fn execute_isolated_task(
        &self,
        target_url: String,
        user_rituals: Vec<String>,
        user_playlist: Vec<String>,
        user_envies: Vec<String>,
    ) -> Result<String, String> {
        let task_id = self.create_task();
        let result = self
            .run_pipeline(
                task_id,
                target_url,
                user_rituals,
                user_playlist,
                user_envies,
            )
            .await;
        self.finish_task(&task_id);
        result
    }

    async fn run_pipeline(
        &self,
        task_id: Uuid,
        target_url: String,
        user_rituals: Vec<String>,
        user_playlist: Vec<String>,
        user_envies: Vec<String>,
    ) -> Result<String, String> {
        // [049] fix: her URL için sabit "X profili kaziniyor" demiyoruz;
        // platform kararı Python registry'sinde verilir, burada tarafsız özet.
        let started = Instant::now();
        let _ = self.event_bus.publish(AgentEvent::TaskStarted {
            task_id,
            agent_name: "TaskManager(run_task)".to_string(),
            input_summary: format!(
                "Hedef: {}, ritüel: {}, çalma listesi: {}, kıskançlık: {} (platform kararı registry'de)",
                target_url, user_rituals.join(", "), user_playlist.join(", "), user_envies.join(", ")
            ),
        });

        // Veri stdin'de — script metnine gömülmez ([045]).
        let payload = json!({
            "url": target_url,
            "rituals": user_rituals,
            "playlist": user_playlist,
            "envies": user_envies,
        });

        let mut child = Command::new(&self.python_path)
            .arg(&self.task_script)
            .current_dir(project_root())
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .kill_on_drop(true) // timeout iptalinde süreci öldür ([049])
            .spawn()
            .map_err(|e| {
                format!(
                    "run_task.py süreci başlatılamadı ({}): {}",
                    self.task_script, e
                )
            })?;

        if let Some(mut stdin) = child.stdin.take() {
            let bytes = serde_json::to_vec(&payload)
                .map_err(|e| format!("stdin JSON oluşturulamadı: {}", e))?;
            stdin
                .write_all(&bytes)
                .await
                .map_err(|e| format!("stdin yazılamadı: {}", e))?;
            // EOF gönder; betik okumayı bitirir.
            drop(stdin);
        }

        // Zaman sınırlı bekleme: takılan süreç öldürülür ([049] — timeout yoktu).
        let output = match tokio::time::timeout(
            Duration::from_secs(TASK_TIMEOUT_SECS),
            child.wait_with_output(),
        )
        .await
        {
            Ok(res) => res.map_err(|e| format!("run_task.py süreci okunamadı: {}", e))?,
            Err(_) => {
                let msg = format!(
                    "GÖREV ZAMAN AŞIMI: {} saniyede tamamlanmadı, süreç öldürüldü.",
                    TASK_TIMEOUT_SECS
                );
                let _ = self.event_bus.publish(AgentEvent::ErrorHalt {
                    task_id,
                    agent_name: "TaskManager(run_task)".to_string(),
                    error_code: "TASK_TIMEOUT".to_string(),
                    error_message: msg.clone(),
                    severity: Severity::Critical,
                });
                return Err(msg);
            }
        };

        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        let exit_ok = output.status.success();

        // stdout her durumda JSON olmalı (run_task.py sözleşmesi); önce onu çöz.
        let json_result: Value = serde_json::from_str(stdout.trim()).map_err(|e| {
            format!(
                "run_task.py çıktısı JSON değil: {} | stdout: {} | stderr: {}",
                e,
                head(&stdout, 300),
                head(&stderr, 300)
            )
        })?;

        if !exit_ok {
            // 2/3/4: dürüst, açıklayalı durumlar — status alanını hata kodu yap.
            let status = json_result
                .get("status")
                .and_then(|v| v.as_str())
                .unwrap_or("failed");
            let note = json_result
                .get("note")
                .or_else(|| json_result.get("error"))
                .or_else(|| json_result.get("reason"))
                .and_then(|v| v.as_str())
                .unwrap_or("Bilinmeyen neden")
                .to_string();
            let message = format!(
                "Görev durdu ({}): {} | stderr: {}",
                status,
                note,
                head(&stderr, 200)
            );
            let _ = self.event_bus.publish(AgentEvent::ErrorHalt {
                task_id,
                agent_name: "TaskManager(run_task)".to_string(),
                error_code: format!("PYTHON_{}", status.to_uppercase()),
                error_message: message.clone(),
                severity: Severity::High,
            });
            return Err(message);
        }

        // Pipeline koştu — status alanı TaskStatus.status ([048] artık tek kaynak).
        let status = json_result
            .get("status")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown")
            .to_string();
        if status == "failed" {
            let error_msg = json_result
                .get("error")
                .and_then(|v| v.as_str())
                .unwrap_or("Bilinmeyen hata");
            let _ = self.event_bus.publish(AgentEvent::ErrorHalt {
                task_id,
                agent_name: "TaskManager(run_task)".to_string(),
                error_code: "EXECUTOR_ERROR".to_string(),
                error_message: error_msg.to_string(),
                severity: Severity::High,
            });
            return Err(format!("Executor hatası: {}", error_msg));
        }

        if let Some(analysis) = json_result.get("mirror_analysis") {
            let alignment_score = analysis
                .get("alignment_score")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0) as f32;
            let anchor_count = analysis
                .get("authentic_anchors")
                .and_then(|v| v.as_array())
                .map(|v| v.len() as u32)
                .unwrap_or(0);
            let overall_frequency = analysis
                .get("user_core_frequency")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown")
                .to_string();
            let _ = self.event_bus.publish(AgentEvent::FrequencyUpdate {
                task_id,
                alignment_score,
                authentic_anchor_count: anchor_count,
                overall_frequency,
            });
        }

        // [048] fix: tek kaynak (stdout), SHA-256, iki event AYNI hash.
        let result_hash = sha256_hex(stdout.trim().as_bytes());
        let _ = self.event_bus.publish(AgentEvent::StepCompleted {
            task_id,
            agent_name: "TaskManager(run_task)".to_string(),
            step_name: "FullPipelineCompleted".to_string(),
            output_hash: result_hash.clone(),
        });

        let _ = self.event_bus.publish(AgentEvent::TaskCompleted {
            task_id,
            agent_name: "TaskManager(run_task)".to_string(),
            final_result_hash: result_hash,
            duration_ms: started.elapsed().as_millis() as u64,
        });

        Ok(stdout.to_string())
    }
}
