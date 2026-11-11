//! PINEAL-HERETIC - Event Bus

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use tokio::sync::broadcast;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AgentEvent {
    TaskStarted {
        task_id: Uuid,
        agent_name: String,
        input_summary: String,
    },
    StepCompleted {
        task_id: Uuid,
        agent_name: String,
        step_name: String,
        output_hash: String,
    },
    ErrorHalt {
        task_id: Uuid,
        agent_name: String,
        error_code: String,
        error_message: String,
        severity: Severity,
    },
    AwaitingHuman {
        task_id: Uuid,
        agent_name: String,
        reason: String,
        options: Vec<String>,
    },
    TaskCompleted {
        task_id: Uuid,
        agent_name: String,
        final_result_hash: String,
        duration_ms: u64,
    },
    /// Contract mirrors agent_core.agents.mirror_truth.MirrorReflection.
    FrequencyUpdate {
        task_id: Uuid,
        alignment_score: f32,
        authentic_anchor_count: u32,
        overall_frequency: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Severity {
    Info,
    Warning,
    High,
    Critical,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TelemetryEvent {
    pub timestamp: DateTime<Utc>,
    pub event: AgentEvent,
    pub correlation_id: Option<Uuid>,
}

pub struct EventBus {
    sender: broadcast::Sender<TelemetryEvent>,
    _receiver_count: usize,
}

impl EventBus {
    pub fn new(buffer_size: usize) -> Self {
        let (sender, _) = broadcast::channel(buffer_size);
        Self {
            sender,
            _receiver_count: 0,
        }
    }

    #[allow(clippy::result_large_err)]
    pub fn publish(
        &self,
        event: AgentEvent,
    ) -> Result<(), broadcast::error::SendError<TelemetryEvent>> {
        let telemetry = TelemetryEvent {
            timestamp: Utc::now(),
            event,
            correlation_id: None,
        };
        self.sender.send(telemetry)?;
        Ok(())
    }

    pub fn subscribe(&self) -> broadcast::Receiver<TelemetryEvent> {
        self.sender.subscribe()
    }

    #[allow(clippy::result_large_err)]
    pub fn publish_with_correlation(
        &self,
        event: AgentEvent,
        correlation_id: Uuid,
    ) -> Result<(), broadcast::error::SendError<TelemetryEvent>> {
        let telemetry = TelemetryEvent {
            timestamp: Utc::now(),
            event,
            correlation_id: Some(correlation_id),
        };
        self.sender.send(telemetry)?;
        Ok(())
    }
}

pub struct EventBusBuilder {
    buffer_size: usize,
    log_to_file: bool,
    log_path: Option<String>,
}

impl Default for EventBusBuilder {
    fn default() -> Self {
        Self {
            buffer_size: 1000,
            log_to_file: false,
            log_path: None,
        }
    }
}

impl EventBusBuilder {
    pub fn new() -> Self {
        Self::default()
    }
    pub fn with_buffer_size(mut self, size: usize) -> Self {
        self.buffer_size = size;
        self
    }
    pub fn with_file_logging(mut self, path: &str) -> Self {
        self.log_to_file = true;
        self.log_path = Some(path.to_string());
        self
    }
    pub fn build(self) -> EventBus {
        EventBus::new(self.buffer_size)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::time::Duration;

    #[tokio::test]
    async fn test_event_bus_publish_subscribe() {
        let bus = EventBus::new(100);
        let mut rx = bus.subscribe();
        let task_id = Uuid::new_v4();
        bus.publish(AgentEvent::TaskStarted {
            task_id,
            agent_name: "MirrorOfTruth".to_string(),
            input_summary: "Hedef profil analizi başlatıldı".to_string(),
        })
        .unwrap();
        let received = tokio::time::timeout(Duration::from_millis(100), rx.recv())
            .await
            .expect("Timeout")
            .expect("Channel kapandı");
        match received.event {
            AgentEvent::TaskStarted { agent_name, .. } => assert_eq!(agent_name, "MirrorOfTruth"),
            _ => panic!("Yanlış event tipi"),
        }
    }

    #[tokio::test]
    async fn test_multiple_subscribers() {
        let bus = EventBus::new(100);
        let mut rx1 = bus.subscribe();
        let mut rx2 = bus.subscribe();
        bus.publish(AgentEvent::StepCompleted {
            task_id: Uuid::new_v4(),
            agent_name: "ShadowExecutor".to_string(),
            step_name: "JSON_Generation".to_string(),
            output_hash: "abc123".to_string(),
        })
        .unwrap();
        let r1 = rx1.recv().await.unwrap();
        let r2 = rx2.recv().await.unwrap();
        assert_eq!(r1.timestamp, r2.timestamp);
    }
}
