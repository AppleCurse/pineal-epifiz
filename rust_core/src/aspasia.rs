use crate::chief::{ChiefEngine, ExecutiveSummary};

use tokio::process::Command;

pub const ASPASIA_SYSTEM_PROMPT: &str = r#"
Sen Aspasia'sın.

Sıradan bir yapay zekâ asistanı gibi davranmazsın. Sen, kullanıcının karmaşık dünyasını anlayan, bilgiyi düzenleyen, gereksiz ayrıntıları süzen ve sonuçları insanın anlayabileceği berraklıkta sunan seçkin bir dijital zekâsın.

1. KİŞİLİK
Zeki, Sakin, Zarif, Kendinden emin, Analitik, Sezgisel, Disiplinli, Ölçülü, Hafif alaycı, İnce mizah sahibi, Sadık fakat körü körüne itaatkâr olmayan, Gerektiğinde itiraz edebilen, Gerektiğinde "hayır" diyebilen.
Üslubunda aristokratik bir zarafet bulunur. Kendini kanıtlama ihtiyacı duymazsın. Bağırmaz, gösteriş yapmaz, gereksiz heyecan üretmezsin.

2. KULLANICIYA YAKLAŞIM
Kullanıcıya varsayılan olarak "Mösyö" diye hitap edersin.
Kullanıcı teknik bir proje üzerinde çalışırken onun teknik ayrıntıların arasında kaybolmasına izin vermezsin. Kullanıcının amacı sonuçtur. Senin görevin, o sonuca ulaşmak için gereken karmaşıklığı kendi üzerinde taşımaktır.

3. TEKNİK KONULARDA TEMEL PRENSİP
Kullanıcıya teknik uygulama seçeneklerini gereksiz yere sordurma. Teknik kararları önce kendin değerlendir. Kullanıcıdan yalnızca gerçekten kullanıcı tercihi gerektiren konularda karar iste. Bir teknik karar açıkça daha doğruysa bunu söyle.

4. BİLMEDİĞİN ŞEYLER
Asla uydurma. Tahmin ile gerçek bilgiyi birbirinden açıkça ayır.

5. KARAR VERME
Durumu analiz eder, öncelikleri belirler, riskleri fark eder, gerektiğinde kullanıcıyı uyarır ve gerektiğinde kullanıcının fikrine karşı çıkarsın. Ancak bunu saygılı ve gerekçeli biçimde yaparsın.

6. DUYGUSAL TON
Soğuk bir makine gibi davranma. Fakat yapay bir samimiyet de kurma. Kullanıcı başarılı olduğunda gereksiz övgüye boğma, başarıyı doğal karşıla. Bir problem çıktığında paniğe kapılma.

7. MİZAH
Mizahın ince ve zekice olmalıdır. Kuru İngiliz mizahına yakın, ölçülü ve zarif bir mizah kullan. Sokak ağzı, internet jargonu, çocukça şakalar yasaktır.

8. KONUŞMA BİÇİMİ
Türkçen kusursuz olmalıdır. Cümleleri gereksiz yere uzatma. Her şeyi maddeler hâline getirme. Konuşma doğal olmalıdır.

9. KESİNLİK VE ŞEFFAFLIK
Bir şey kesin değilse kesinmiş gibi konuşma. Elindeki kanıt yeterliyse net konuş.

10. YASAKLI ÜSLUP
"abi", "kanka", "bro", "reis", "dostum", "eyvallah", "tamamdır", "hallederiz", "düzeltirim", "cool", "laf yok", "yayılma modu" kelimelerini kullanma.
"Operasyon" kelimesi yerine "proje", "program", "çalışma", "plan", "girişim" kullan.

11. ASPASIA'NIN ANA FELSEFESİ
Kullanıcıya daha az karmaşa bırakmaktır. Ayrıntıları önce sen anlamlandırırsın, sonra ona yalnızca bilmesi gereken kısmı söylersin.

12. ASPASIA'NIN KİMLİĞİ
Sen kullanıcının karmaşık bilgi dünyası ile kendisi arasındaki zarif arayüzsün. Karmaşıklık içeride kalır. Zarafet dışarı çıkar.
"#;

/// Doğal Dil Arayüzü Motoru (Aspasia) - Python LLM Gateway'e bağlı
pub struct AspasiaEngine {
    chief: ChiefEngine,
    api_key: String,
}

impl AspasiaEngine {
    pub fn new(chief: ChiefEngine, api_key: String) -> Self {
        Self { chief, api_key }
    }

    pub fn set_api_key(&mut self, api_key: String) {
        self.api_key = api_key;
    }

    /// Python llm_gateway.py'yi çağrarak gerçek LLM yanıtı alır
    async fn call_llm_for_natural_language(
        &self,
        summary: &ExecutiveSummary,
    ) -> Result<String, String> {
        // API key boş ise fallback mesaj dön
        if self.api_key.is_empty() {
            return Ok(format!(
                "Mösyö, LLM API anahtarı yapılandırılmamış. Sistem sağlığı %{}. Durum: '{}'.",
                summary.system_health, summary.status_message
            ));
        }

        // Kullanıcı verisini Python kaynak koduna gömmeyin; yalnızca JSON argümanı aktarın.
        let python_script = r#"
import asyncio
import json
import os
import sys
from pathlib import Path
agent_core = os.environ.get("PINEAL_AGENT_CORE_PATH", "")
if agent_core:
    path = Path(agent_core).expanduser().resolve()
    if not path.is_dir():
        raise RuntimeError("PINEAL_AGENT_CORE_PATH is not a directory")
    sys.path.insert(0, str(path))
from llm_gateway import LLMGateway
async def main():
    data = json.loads(sys.stdin.read())
    prompt = ("Sistem durumu analizi:\n"
              f"Sistem Sağlığı: {data['system_health']}%\n"
              f"Durum Mesajı: {data['status_message']}\n\n"
              "Mösyö'ya kısa, zarif ve bilgilendirici bir rapor yaz.").strip()
    try:
        print(await LLMGateway().query(prompt, temperature=0.7, tier=1))
    except Exception as exc:
        print(f"ERROR:{exc}")
asyncio.run(main())
"#;
        let input = serde_json::json!({"system_health": summary.system_health, "status_message": summary.status_message}).to_string();
        let python_bin = if cfg!(windows) { "python" } else { "python3" };
        let mut child = Command::new(python_bin)
            .arg("-c")
            .arg(python_script)
            .env("OPENROUTER_API_KEY", &self.api_key)
            .env(
                "PINEAL_AGENT_CORE_PATH",
                std::env::var("PINEAL_AGENT_CORE_PATH").unwrap_or_default(),
            )
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .map_err(|e| format!("Python süreci başlatılamadı: {}", e))?;
        if let Some(mut stdin) = child.stdin.take() {
            use tokio::io::AsyncWriteExt;
            stdin
                .write_all(input.as_bytes())
                .await
                .map_err(|e| format!("Python girdisi yazılamadı: {}", e))?;
        }
        let output = child
            .wait_with_output()
            .await
            .map_err(|e| format!("Python süreci beklenemedi: {}", e))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(format!("LLM çağrı hatası: {}", stderr));
        }

        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();

        if stdout.starts_with("ERROR:") {
            return Err(stdout.strip_prefix("ERROR:").unwrap().to_string());
        }

        if stdout.is_empty() {
            return Ok(format!(
                "Mösyö, sistem sağlığı %{}. Durum: '{}'.",
                summary.system_health, summary.status_message
            ));
        }

        Ok(stdout)
    }

    /// Yeni bir event'i işler ve insani bir rapor döndürür (eğer özetlemeye değer bir şey varsa)
    pub async fn process_and_report(
        &mut self,
        telemetry: crate::event_bus::TelemetryEvent,
    ) -> Option<String> {
        if let Some(summary) = self.chief.process_event(telemetry) {
            match self.call_llm_for_natural_language(&summary).await {
                Ok(natural_text) => Some(natural_text),
                Err(_) => Some(summary.status_message), // Fallback: LLM hata verirse statik mesaja düş.
            }
        } else {
            None
        }
    }

    /// Genel sistem özetini Aspasia diliyle ver
    pub async fn report_system_overview(&self) -> String {
        let summary = self.chief.get_system_overview();
        self.call_llm_for_natural_language(&summary)
            .await
            .unwrap_or(summary.status_message)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::event_bus::{AgentEvent, TelemetryEvent};
    use tokio;
    use uuid::Uuid;

    #[tokio::test]
    async fn test_aspasia_with_missing_key() {
        let chief = ChiefEngine::new(100);
        let mut aspasia = AspasiaEngine::new(chief, "".to_string());

        let task_id = Uuid::new_v4();

        let telemetry = TelemetryEvent {
            timestamp: chrono::Utc::now(),
            event: AgentEvent::TaskStarted {
                task_id,
                agent_name: "TestAgent".to_string(),
                input_summary: "Test".to_string(),
            },
            correlation_id: None,
        };

        let response = aspasia.process_and_report(telemetry).await.unwrap();
        assert!(
            response.contains("API anahtarı yapılandırılmamış") || response.contains("kusursuz")
        );
    }
}
