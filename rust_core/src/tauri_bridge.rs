//! [W4.3] Tauri köprüsü — YALNIZCA paylaşılan state + telemetri köprüsü.
//!
//! [009]/[047] fix: Tauri command'larının tek sahibi src-tauri/src/lib.rs'tir.
//! Bu dosyadaki ikiz implementasyonlar (/tmp'li vault yolu, parametresiz
//! query_aspasia, kayıtsız get_vault_credentials) kaldırıldı — çift sahiplik
//! davranış ayrışmasına yol açıyordu (farklı vault dosyaları, farklı imzalar).
//!
//! Kalanlar:
//! - CoreState: motorların Tauri State yönetimi için tek sarıcı
//! - TauriEventPayload + setup_telemetry_bridge: EventBus -> Svelte emit hattı
//! - setup_agent_status_bridge: Redis -> Svelte Agent Rack hattı

use serde::Serialize;
use std::sync::Arc;
use tauri::{AppHandle, Emitter};
use tokio::sync::Mutex;

use crate::aspasia::AspasiaEngine;
use crate::event_bus::{EventBus, TelemetryEvent};
use crate::redis_bridge::AgentStatusPayload;
use crate::task_isolation::TaskManager;
use crate::vault::StealthVault;

/// State wrapper to hold our core engines for Tauri
pub struct CoreState {
    pub task_manager: Arc<TaskManager>,
    pub aspasia: Arc<Mutex<AspasiaEngine>>,
    pub vault: Arc<Mutex<Option<StealthVault>>>, // Option: başlangıçta boş
    pub event_bus: Arc<EventBus>,
}

#[derive(Serialize, Clone)]
pub struct TauriEventPayload {
    pub event_type: String,
    pub data: String,
}

#[derive(Serialize, Clone)]
pub struct AgentStatusTauriPayload {
    pub agent_id: String,
    pub status: String,
    pub timestamp: String,
    pub metadata: serde_json::Value,
}

impl From<AgentStatusPayload> for AgentStatusTauriPayload {
    fn from(p: AgentStatusPayload) -> Self {
        Self {
            agent_id: p.agent_id,
            status: p.status,
            timestamp: p.timestamp.to_rfc3339(),
            metadata: p.metadata,
        }
    }
}

/// Canlı Telemetri Köprüsü (EventBus -> Tauri Emit)
pub fn setup_telemetry_bridge(
    app_handle: AppHandle,
    mut rx: tokio::sync::broadcast::Receiver<TelemetryEvent>,
) {
    tauri::async_runtime::spawn(async move {
        while let Ok(event) = rx.recv().await {
            // Event'i JSON'a çevir
            if let Ok(json_str) = serde_json::to_string(&event) {
                let payload = TauriEventPayload {
                    event_type: "telemetry_update".to_string(),
                    data: json_str,
                };

                // Tauri arayüzüne (Svelte) gönder
                let _ = app_handle.emit("pineal-telemetry", payload);
            }
        }
    });
}

/// Agent Rack canlı köprüsü (Redis Pub/Sub -> Tauri Emit)
/// Python tarafındaki redis_bus ile aynı kanal: pineal:agent_status
#[cfg(feature = "redis")]
pub fn setup_agent_status_bridge(
    app_handle: AppHandle,
    mut rx: tokio::sync::broadcast::Receiver<AgentStatusPayload>,
) {
    tauri::async_runtime::spawn(async move {
        while let Ok(status) = rx.recv().await {
            let payload: AgentStatusTauriPayload = status.into();
            let _ = app_handle.emit("pineal-agent-status", payload);
        }
    });
}

#[cfg(not(feature = "redis"))]
pub fn setup_agent_status_bridge(
    _app_handle: AppHandle,
    _rx: tokio::sync::broadcast::Receiver<AgentStatusPayload>,
) {
    // redis feature kapalıysa no-op
}

/// Fallback: doğrudan EventBus üzerinden agent_status_update simülasyonu
/// (Redis yoksa bile local tracker için)
pub fn setup_agent_status_bridge_local(
    app_handle: AppHandle,
    mut rx: tokio::sync::broadcast::Receiver<TelemetryEvent>,
) {
    // Sadece AgentEvent::TaskStarted / StepCompleted gibi eventleri
    // Agent Rack durumuna çevirir — basit fallback
    tauri::async_runtime::spawn(async move {
        while let Ok(telemetry) = rx.recv().await {
            let (agent_id, status) = match &telemetry.event {
                crate::event_bus::AgentEvent::TaskStarted { agent_name, .. } => {
                    (agent_name.clone(), "Active")
                }
                crate::event_bus::AgentEvent::StepCompleted { agent_name, .. } => {
                    (agent_name.clone(), "Ready")
                }
                crate::event_bus::AgentEvent::ErrorHalt { agent_name, .. } => {
                    (agent_name.clone(), "Wait")
                }
                _ => continue,
            };
            let payload = AgentStatusTauriPayload {
                agent_id: agent_id.clone(),
                status: status.to_string(),
                timestamp: telemetry.timestamp.to_rfc3339(),
                metadata: serde_json::json!({ "source": "event_bus_fallback" }),
            };
            let _ = app_handle.emit("pineal-agent-status", payload);
        }
    });
}
