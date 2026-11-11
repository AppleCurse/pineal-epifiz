//! Redis Pub/Sub bridge — Agent Rack canlı durum köprüsü
//!
//! Python tarafındaki `agent_core.services.redis_bus` ve `agent_status_tracker`
//! ile aynı kanalı kullanır: `pineal:agent_status`.
//!
//! Tauri tarafında event_bus üzerinden gelen AgentEvent'ler buradan Redis'e
//! publish edilir; Redis'ten gelen agent_status_update mesajları ise
//! Tauri event sistemi üzerinden `pineal-agent-status` olarak emit edilir.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentStatusPayload {
    pub agent_id: String,
    pub status: String, // Ready | Active | Wait
    pub timestamp: DateTime<Utc>,
    #[serde(default)]
    pub metadata: serde_json::Value,
}

impl AgentStatusPayload {
    pub fn new(agent_id: impl Into<String>, status: impl Into<String>) -> Self {
        Self {
            agent_id: agent_id.into(),
            status: status.into(),
            timestamp: Utc::now(),
            metadata: serde_json::Value::Object(Default::default()),
        }
    }

    pub fn with_metadata(mut self, meta: serde_json::Value) -> Self {
        self.metadata = meta;
        self
    }
}

#[cfg(feature = "redis")]
pub mod live {
    use super::*;
    use redis::aio::{MultiplexedConnection, PubSub};
    use redis::{AsyncCommands, Client};
    use tokio::sync::broadcast;
    use tracing::{info, warn};

    pub const AGENT_STATUS_CHANNEL: &str = "pineal:agent_status";
    pub const AGENT_STATUS_PATTERN: &str = "pineal:agent_status*";

    pub struct RedisBridge {
        client: Client,
        tx: broadcast::Sender<AgentStatusPayload>,
    }

    impl RedisBridge {
        pub fn new(redis_url: &str) -> Result<Self, redis::RedisError> {
            let client = Client::open(redis_url)?;
            let (tx, _) = broadcast::channel(256);
            Ok(Self { client, tx })
        }

        pub fn subscribe(&self) -> broadcast::Receiver<AgentStatusPayload> {
            self.tx.subscribe()
        }

        pub async fn publish_status(
            &self,
            payload: &AgentStatusPayload,
        ) -> Result<(), redis::RedisError> {
            let mut conn = self.client.get_multiplexed_async_connection().await?;
            let json = serde_json::to_string(payload).unwrap_or_default();
            let _: () = conn.publish(AGENT_STATUS_CHANNEL, json).await?;
            Ok(())
        }

        pub async fn set_agent_status(
            &self,
            agent_id: &str,
            status: &str,
            metadata: Option<serde_json::Value>,
        ) -> Result<(), redis::RedisError> {
            let payload = AgentStatusPayload {
                agent_id: agent_id.to_string(),
                status: status.to_string(),
                timestamp: Utc::now(),
                metadata: metadata.unwrap_or_default(),
            };
            self.publish_status(&payload).await
        }

        /// Arka planda PubSub dinleyicisi — gelen mesajları broadcast eder
        pub async fn run_listener(&self) -> Result<(), redis::RedisError> {
            let mut pubsub_conn = self.client.get_async_pubsub().await?;
            pubsub_conn.subscribe(AGENT_STATUS_CHANNEL).await?;
            info!("RedisBridge listener aktif: {}", AGENT_STATUS_CHANNEL);

            let tx = self.tx.clone();
            loop {
                let mut stream = pubsub_conn.on_message();
                use futures_util::StreamExt;
                while let Some(msg) = stream.next().await {
                    let payload_str: String = match msg.get_payload() {
                        Ok(s) => s,
                        Err(e) => {
                            warn!("Redis payload parse hatasi: {}", e);
                            continue;
                        }
                    };
                    match serde_json::from_str::<AgentStatusPayload>(&payload_str) {
                        Ok(parsed) => {
                            let _ = tx.send(parsed);
                        }
                        Err(e) => {
                            warn!(
                                "AgentStatus JSON parse hatasi: {} | raw={}",
                                e,
                                payload_str.chars().take(120).collect::<String>()
                            );
                        }
                    }
                }
            }
        }

        pub async fn set_all_wait(&self) -> Result<(), redis::RedisError> {
            // 12 ajan + fallback'ler için Wait
            let agents = crate::redis_bridge::all_agent_ids();
            for agent_id in agents {
                self.set_agent_status(agent_id, "Wait", None).await?;
            }
            Ok(())
        }

        // [RÖNTGEN 2026-09-23] `set_all_ready` KALDIRILDI: hiçbir ajan
        // koşmadan 12 slotu birden "Ready" ilan etmek ölçülmeyen bir durum
        // iddiasıdır (Python tarafındaki AgentStatusTracker.set_all_ready ile
        // aynı kusur). Ready yalnız gerçek bir ajan geçişinde yazılır.
    }
}

// Fallback — redis feature kapalıyken derlenebilir stub
#[cfg(not(feature = "redis"))]
pub mod live {
    use super::*;

    pub const AGENT_STATUS_CHANNEL: &str = "pineal:agent_status";

    pub struct RedisBridge;

    impl RedisBridge {
        pub fn new(_redis_url: &str) -> Result<Self, std::io::Error> {
            Ok(Self)
        }
        pub async fn publish_status(
            &self,
            _payload: &AgentStatusPayload,
        ) -> Result<(), std::io::Error> {
            Ok(())
        }
        pub async fn set_agent_status(
            &self,
            _agent_id: &str,
            _status: &str,
            _metadata: Option<serde_json::Value>,
        ) -> Result<(), std::io::Error> {
            Ok(())
        }
        pub async fn run_listener(&self) -> Result<(), std::io::Error> {
            Ok(())
        }
        pub async fn set_all_wait(&self) -> Result<(), std::io::Error> {
            Ok(())
        }
    }
}

/// Tüm Agent Rack slot ID'leri — Python tarafındaki AGENT_DEFINITIONS ile senkron
pub fn all_agent_ids() -> Vec<&'static str> {
    vec![
        "mirror_truth",
        "autonomous_verifier",
        "human_behavior",
        "passion_mapper",
        "friction_detector",
        "cognitive_profiler",
        "resonance_calculator",
        "pattern_interrupt",
        "osint_investigator",
        "authenticity_auditor",
        "depth_analyst",
        "resonance_synthesizer",
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn payload_serialize() {
        let p = AgentStatusPayload::new("mirror_truth", "Active");
        let json = serde_json::to_string(&p).unwrap();
        assert!(json.contains("mirror_truth"));
        assert!(json.contains("Active"));
    }

    #[test]
    fn all_ids_count() {
        assert_eq!(all_agent_ids().len(), 12);
    }
}
