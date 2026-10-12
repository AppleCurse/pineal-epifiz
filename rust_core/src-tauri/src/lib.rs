use pineal_heretic_core::{
    ChiefEngine, AspasiaEngine, EventBus, TaskManager, StealthVault,
};
use pineal_heretic_core::vault::default_vault_path;
use pineal_heretic_core::tauri_bridge::{CoreState, setup_telemetry_bridge, setup_agent_status_bridge_local};
#[cfg(feature = "redis")]
use pineal_heretic_core::tauri_bridge::setup_agent_status_bridge;
#[cfg(feature = "redis")]
use pineal_heretic_core::redis_bridge::live::RedisBridge;
use std::sync::Arc;
use tokio::sync::Mutex;
use serde::{Deserialize, Serialize};

// ─── FAZ 1-A: Vault Komutlari ─────────────────────────────────────────

#[tauri::command]
async fn create_vault(
    password: String,
    state: tauri::State<'_, CoreState>,
) -> Result<String, String> {
    let vault_path = default_vault_path();
    if let Some(parent) = vault_path.parent() {
        std::fs::create_dir_all(parent).ok();
    }
    let vault = StealthVault::new(&vault_path, &password)
        .map_err(|e| format!("Vault olusturulamadi: {}", e))?;
    let mut vault_state = state.vault.lock().await;
    *vault_state = Some(vault);
    Ok("Kasa basariyla olusturuldu. Argon2id + age ile muhurlendi.".to_string())
}

#[tauri::command]
async fn open_vault(
    password: String,
    state: tauri::State<'_, CoreState>,
) -> Result<String, String> {
    let vault_path = default_vault_path();
    if !vault_path.exists() {
        return Err("Vault dosyasi bulunamadi. Once kasa olusturun.".to_string());
    }
    let vault = StealthVault::load(&vault_path, &password)
        .map_err(|e| format!("Vault acilamadi (yanlis parola?): {}", e))?;
    let mut vault_state = state.vault.lock().await;
    *vault_state = Some(vault);
    Ok("Kasa acildi. Kimlik bilgileri kullanima hazir.".to_string())
}

#[tauri::command]
async fn check_vault_status(
    state: tauri::State<'_, CoreState>,
) -> Result<bool, String> {
    let vault_state = state.vault.lock().await;
    Ok(vault_state.is_some())
}

#[tauri::command]
async fn lock_vault(
    state: tauri::State<'_, CoreState>,
) -> Result<String, String> {
    let mut vault_state = state.vault.lock().await;
    if let Some(mut v) = vault_state.take() {
        v.secure_wipe();
    }
    Ok("Kasa kilitlendi. Dis dunya erisimi durduruldu.".to_string())
}

#[tauri::command]
async fn vault_exists() -> Result<bool, String> {
    Ok(default_vault_path().exists())
}

// ─── FAZ 1-B: Credentials ─────────────────────────────────────────────

#[tauri::command]
async fn set_vault_credentials(
    key: String,
    value: String,
    state: tauri::State<'_, CoreState>,
) -> Result<String, String> {
    let vault_state = state.vault.lock().await;
    match vault_state.as_ref() {
        Some(vault) => {
            #[derive(Serialize)]
            struct Credential { value: String }
            let cred = Credential { value };
            vault.store(&key, &cred)
                .map_err(|e| format!("Kasaya yazilamadi: {}", e))?;
            Ok(format!("{} basariyla kasaya muhurlediniz.", key))
        }
        None => Err("Kasa acik degil. Once 'Kasa Ac' veya 'Kasa Olustur' butonuna basin.".to_string()),
    }
}

#[tauri::command]
async fn get_vault_credentials(
    key: String,
    state: tauri::State<'_, CoreState>,
) -> Result<String, String> {
    let vault_state = state.vault.lock().await;
    match vault_state.as_ref() {
        Some(vault) => {
            #[derive(Deserialize)]
            struct Credential { value: String }
            let cred: Credential = vault.retrieve(&key)
                .map_err(|e| format!("Kasadan okunamadi: {}", e))?;
            Ok(cred.value)
        }
        None => Err("Kasa acik degil. Once 'Kasa Ac' veya 'Kasa Olustur' butonuna basin.".to_string()),
    }
}

// ─── FAZ 1-C: Aspasia ─────────────────────────────────────────────────

#[tauri::command]
async fn query_aspasia(
    user_message: Option<String>,
    state: tauri::State<'_, CoreState>,
) -> Result<String, String> {
    let mut aspasia = state.aspasia.lock().await;
    let report = aspasia.report_system_overview().await;
    if let Some(msg) = user_message {
        if !msg.is_empty() {
            return Ok(format!("[Mosyo sorusu: {}]\n\n{}", msg, report));
        }
    }
    Ok(report)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentStatusPayload {
    pub agent_id: String,
    pub status: String,
    pub timestamp: String,
    pub metadata: Option<serde_json::Value>,
}

#[tauri::command]
async fn emit_agent_status(
    agent_id: String,
    status: String,
    metadata: Option<serde_json::Value>,
    state: tauri::State<'_, CoreState>,
) -> Result<String, String> {
    let payload = AgentStatusPayload {
        agent_id: agent_id.clone(),
        status: status.clone(),
        timestamp: chrono::Utc::now().to_rfc3339(),
        metadata,
    };
    let event = pineal_heretic_core::event_bus::AgentEvent::StepCompleted {
        task_id: uuid::Uuid::new_v4(),
        agent_name: agent_id.clone(),
        step_name: status.clone(),
        output_hash: serde_json::to_string(&payload).unwrap_or_default(),
    };
    let _ = state.event_bus.publish(event);
    Ok(format!("{} -> {}", agent_id, status))
}

// ─── FAZ 1-D: Analiz ──────────────────────────────────────────────────

#[tauri::command]
async fn start_analysis(
    target_url: String,
    _scraper_type: Option<String>,
    _user_rituals: Option<Vec<String>>,
    _user_playlist: Option<Vec<String>>,
    _user_envies: Option<Vec<String>>,
    state: tauri::State<'_, CoreState>,
) -> Result<String, String> {
    {
        let vault_state = state.vault.lock().await;
        if vault_state.is_none() {
            return Err("VAULT KILITLI: Operator anahtari cevirmeden dis dunyaya OSINT/Scraper istegi cikamaz. Once kasayi acin.".to_string());
        }
    }
    let result = state.task_manager.execute_isolated_task(
        target_url,
        _user_rituals.unwrap_or_default(),
        _user_playlist.unwrap_or_default(),
        _user_envies.unwrap_or_default(),
    ).await;
    result.map_err(|e| format!("Analiz baslatilamadi: {}", e))
}

#[tauri::command]
async fn get_system_info() -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({
        "product": "ATLAS PINEAL OBSERVATORY",
        "version": "5.0.0",
        "build": "tauri-native",
        "gpu_acceleration": true,
        "vault_path": default_vault_path().to_string_lossy(),
        "timestamp": chrono::Utc::now().to_rfc3339()
    }))
}

// ─── Tauri Uygulama Baslangici - NATIVE WINDOW + GPU ──────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let event_bus = Arc::new(EventBus::new(1000));
    let api_key = std::env::var("OPENROUTER_API_KEY").unwrap_or_default();
    let chief = ChiefEngine::new(100);
    let aspasia = AspasiaEngine::new(chief, api_key);
    let vault: Option<StealthVault> = None;
    let task_manager = TaskManager::new(event_bus.clone());

    let core_state = CoreState {
        task_manager: Arc::new(task_manager),
        aspasia: Arc::new(Mutex::new(aspasia)),
        vault: Arc::new(Mutex::new(vault)),
        event_bus: event_bus.clone(),
    };

    let telemetry_rx = event_bus.subscribe();
    let agent_status_local_rx = event_bus.subscribe();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_log::Builder::default().build())
        .manage(core_state)
        .invoke_handler(tauri::generate_handler![
            start_analysis,
            query_aspasia,
            create_vault,
            open_vault,
            check_vault_status,
            lock_vault,
            vault_exists,
            set_vault_credentials,
            get_vault_credentials,
            emit_agent_status,
            get_system_info,
        ])
        .setup(move |app| {
            use tauri::Manager;
            let app_handle = app.handle().clone();
            let app_handle_telemetry = app.handle().clone();
            let app_handle_local = app.handle().clone();
            let app_handle_redis = app.handle().clone();

            // 1. Telemetri köprüsü: EventBus -> Svelte (pineal-telemetry)
            setup_telemetry_bridge(app_handle_telemetry, telemetry_rx);

            // 2. Lokal fallback: EventBus -> Agent Rack (pineal-agent-status)
            // Redis yoksa bile TaskStarted/StepCompleted -> Active/Ready çevirir
            setup_agent_status_bridge_local(app_handle_local, agent_status_local_rx);

            // 3. Redis canlı köprüsü: Redis Pub/Sub -> Svelte (pineal-agent-status)
            // REDIS_URL varsa gerçek canlı köprü; yoksa fallback zaten çalışıyor
            #[cfg(feature = "redis")]
            {
                let redis_url = std::env::var("REDIS_URL").unwrap_or_else(|_| "redis://localhost:6379/0".to_string());
                match RedisBridge::new(&redis_url) {
                    Ok(bridge) => {
                        let rx = bridge.subscribe();
                        setup_agent_status_bridge(app_handle_redis, rx);
                        tauri::async_runtime::spawn(async move {
                            if let Err(e) = bridge.run_listener().await {
                                eprintln!("[RedisBridge] listener hatasi: {}", e);
                            }
                        });
                        println!("[RedisBridge] Aktif: {}", redis_url);
                    }
                    Err(e) => {
                        eprintln!("[RedisBridge] Baglanti kurulamadi (fallback): {}", e);
                    }
                }
            }
            #[cfg(not(feature = "redis"))]
            {
                let _ = app_handle_redis;
                println!("[AgentRack] Redis feature kapali — lokal fallback aktif");
            }

            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_title("ATLAS PINEAL OBSERVATORY - HERETIC v5.0 [NATIVE GPU]");
                let _ = window.center();
                let _ = window.set_focus();
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
