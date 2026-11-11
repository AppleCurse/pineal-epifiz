//! PINEAL-HERETIC v4.0 Core Library
//!
//! Bellek-güvenli, tip-kesin ajan orchestration motoru.

pub mod agent_pipeline;
pub mod agents;
pub mod aspasia;
pub mod chief;
pub mod event_bus;
pub mod ghost;
pub mod redis_bridge;
pub mod task_isolation;
pub mod token_compressor;
pub mod uncertainty;
pub mod vault;
// [W4.1] tauri_bridge yalnızca masaüstü kabuğu derlemesinde (feature="tauri").
// Böylece rust_core çekirdeği CI'da webkit sistem bağımlılıkları olmadan
// derlenip test edilebilir; kabuk (src-tauri) feature'ı açar.
#[cfg(feature = "tauri")]
pub mod tauri_bridge;

pub use agent_pipeline::{AgentNode, AnalysisResult, HaltReason};
pub use agents::autonomous_verifier::{AutonomousVerifier, VerificationResult, VerifierReport};
pub use agents::mirror_truth::{MirrorReflection, MirrorTruthAgent};
pub use agents::resonance_calculator::{ResonanceCalculator, ResonanceProfile};
pub use aspasia::{AspasiaEngine, ASPASIA_SYSTEM_PROMPT};
pub use chief::{ChiefEngine, ExecutiveSummary};
pub use event_bus::{AgentEvent, EventBus, Severity as EventSeverity, TelemetryEvent};
pub use ghost::GhostBrowser;
pub use task_isolation::{TaskContext, TaskManager};
pub use token_compressor::{compress_prompt, CompressionLevel};
pub use uncertainty::{
    ConfidenceLevel, Evidence, InsufficientEvidence, Severity, UncertaintyEngine, UncertaintyError,
};
pub use vault::{EncryptedPayload, StealthVault, VaultError};
