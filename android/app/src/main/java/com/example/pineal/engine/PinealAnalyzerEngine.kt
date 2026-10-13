package com.example.pineal.engine

import com.example.pineal.BuildConfig
import com.example.pineal.data.model.*
import com.example.pineal.engine.gemini.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.abs

sealed class PipelineEvent {
    data class Log(val entry: LogEntry) : PipelineEvent()
    data class AgentUpdate(val agentId: String, val status: String, val confidence: Double) : PipelineEvent()
    data class TelemetryUpdate(val telemetry: TelemetryData) : PipelineEvent()
    data class PartialProfile(val profile: HolisticProfile) : PipelineEvent()
    data class Completed(val profile: HolisticProfile, val resonanceScore: Double, val approach: String, val redFlags: List<String>) : PipelineEvent()
    data class Failed(val reason: String) : PipelineEvent()
}

class PinealAnalyzerEngine {
    private val timeFormat = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
    private val jsonParser = Json { ignoreUnknownKeys = true; isLenient = true; encodeDefaults = true }

    fun executeAnalysisPipeline(
        targetUrl: String,
        rituals: String,
        playlist: String,
        envies: String,
        platforms: Set<String>,
        apiKey: String,
        useCloudApi: Boolean
    ): Flow<PipelineEvent> = flow {
        val cleanHandle = targetUrl.trim().removePrefix("https://instagram.com/").removePrefix("https://x.com/").removePrefix("@").split("/").firstOrNull { it.isNotBlank() } ?: "target_user"

        emit(PipelineEvent.Log(LogEntry(timeFormat.format(Date()), "INFO", "SİSTEM AKTİF · PINEAL-GLAND v${BuildConfig.VERSION_NAME} SENTEZ BAŞLADI (GEMINI EDGE AI)")))
        emit(PipelineEvent.Log(LogEntry(timeFormat.format(Date()), "INFO", "Profil: @$cleanHandle | Mod: Gemini LLM Inference")))

        if (apiKey.isBlank()) {
            emit(PipelineEvent.Log(LogEntry(timeFormat.format(Date()), "ERROR", "GEMINI API ANAHTARI EKSİK! Lütfen ayarlar menüsünden API anahtarınızı girin.")))
            emit(PipelineEvent.Failed("Gemini API Anahtarı eksik."))
            return@flow
        }

        // [RÖNTGEN 2026-09-23] HAYALET AJAN DURUMLARI KALDIRILDI.
        // Bu üç satır mirror_truth / autonomous_verifier / human_behavior
        // ajanlarını "RUNNING" diye yayınlıyordu; Android tarafında bu ajanlar
        // YOK — tek bir Gemini çağrısı var (aşağıda). ViewModel bu isimleri
        // ajan listesinde eşleştiremese de `currentAgentId` alanına yazıyordu,
        // yani ekran "şu an koşan ajan: MIRROR TRUTH" diyordu. Durum artık
        // gerçekten koşan hattın kimliğiyle yayınlanıyor.
        emit(PipelineEvent.AgentUpdate("deep_inference", "RUNNING", 0.0))
        emit(PipelineEvent.Log(LogEntry(timeFormat.format(Date()), "INFO", "[LLM_ORCHESTRATOR] Google Gemini Pro ile derin bağlamsal çıkarım başlatılıyor...")))

        try {
            val prompt = """
                Sen uzman bir bilişsel profil analisti (Pineal Gland) sistemisin.
                Aşağıda verilen bilgilere dayanarak verilen kişinin psikolojik, sosyal ve davranışsal profilini pozitif, vizyoner ve gelişim odaklı bir dille çıkarman gerekiyor.
                Tüm çıkarımlarının bir 'LLM Tahmini' (Inference) olduğunu kabul ederek, mantıklı, tutarlı ve derinlikli bir JSON üretmelisin.

                Profil Bilgileri:
                - Kullanıcı Adı / URL: @$cleanHandle
                - Gözlemlenen Ritüeller (Kullanıcı girdisi): $rituals
                - Dinlediği Müzikler / Çalma Listesi (Kullanıcı girdisi): $playlist
                - Kıskançlık / Özendiği Şeyler (Kullanıcı girdisi): $envies
                - Biyometrik/Dijital Ayak İzi Kaynakları (Seçilen Platformlar): ${platforms.joinToString(", ")}

                (Not: Analizi yaparken seçilen bu platformların psikolojik doğasını göz önünde bulundur.
                Örn: LinkedIn profesyonel maske ve hiyerarşi, X/Twitter reaktif dürtüsellik, Instagram estetik/sosyal onay,
                TikTok trend odaklılık, Snapchat geçicilik, Bluesky/Mastodon niş komünite göstergesidir.)

                Çıktın SADECE JSON formatında olmalı. Başka metin veya markdown (```json) EKLEME.
                JSON yapısı aşağıdaki data sınıflarının özelliklerini tamamen ve HİÇ EKSİKSİZ şekilde içermelidir:

                {
                    "depthReport": { "realityIndex": <0.0-1.0>, "essenceOneLiner": "...", "realityFindings": [ { "topic": "...", "observation": "...", "evidenceQuotes": ["..."] } ], "contradictions": [ ... ], "quoteGuard": { "kept": <sayı>, "droppedFakeQuote": <sayı> } },
                    "shadowProfile": { "manipulationRisk": "DÜŞÜK/ORTA/YÜKSEK/KRİTİK", "strategy": "...", "darkProfile": { "narcissism": { "level": "...", "semanticEvidence": "..." }, "machiavellianism": { "level": "...", "semanticEvidence": "..." }, "psychopathy": { "level": "...", "semanticEvidence": "..." } } },
                    "passions": { "corePassions": ["..."], "energizingTopics": ["..."], "flowTriggers": ["..."], "evidenceQuotes": ["..."] },
                    "frictions": { "sensitivities": ["..."], "stressTriggers": ["..."], "boundarySignals": ["..."] },
                    "cognitive": { "communicationTone": "...", "complexityLevel": "...", "socialOrientation": "...", "humorStyle": "...", "metrics": { "creativity": <0.0-1.0>, "analytical": <0.0-1.0>, "empathy": <0.0-1.0>, "leadership": <0.0-1.0>, "adaptability": <0.0-1.0> } },
                    "bridge": { "sharedPassions": ["..."], "resonanceScore": <0.0-1.0>, "authenticOpeningTopic": "...", "suggestedOpeningMessage": "...", "conversationStarterRationale": "..." }
                }
            """.trimIndent()

            val request = GenerateContentRequest(
                contents = listOf(Content(parts = listOf(Part(text = prompt)))),
                generationConfig = GenerationConfig(
                    responseFormat = ResponseFormat(
                        text = ResponseFormatText(mimeType = "application/json")
                    )
                ),
                systemInstruction = Content(parts = listOf(Part(text = "You are an analytical JSON engine. Only output valid JSON without any markdown code blocks.")))
            )

            val apiResponse = RetrofitClient.service.generateContentPro(apiKey, request)
            var responseText = apiResponse.candidates?.firstOrNull()?.content?.parts?.firstOrNull()?.text ?: ""

            responseText = responseText.trim()
            if (responseText.startsWith("```json")) responseText = responseText.removePrefix("```json")
            if (responseText.startsWith("```")) responseText = responseText.removePrefix("```")
            if (responseText.endsWith("```")) responseText = responseText.removeSuffix("```")
            responseText = responseText.trim()

            val analyzerResponse = jsonParser.decodeFromString<AnalyzerResponse>(responseText)

            emit(PipelineEvent.AgentUpdate("deep_inference", "COMPLETED", analyzerResponse.bridge.resonanceScore))
            emit(PipelineEvent.Log(LogEntry(timeFormat.format(Date()), "SUCCESS", "[DERİN ÇIKARIM AĞI] Profil verileri analiz edildi ve sentez haritası oluşturuldu (Single-Shot LLM Inference)")))

            val holisticProfile = HolisticProfile(
                username = cleanHandle,
                passions = analyzerResponse.passions,
                frictions = analyzerResponse.frictions,
                cognitive = analyzerResponse.cognitive,
                bridge = analyzerResponse.bridge,
                depthReport = analyzerResponse.depthReport,
                shadowProfile = analyzerResponse.shadowProfile,
                // [RÖNTGEN 2026-09-23] Bu değer MODELİN KENDİ BEYANIDIR
                // (bridge.resonanceScore): Android hattında bağımsız doğrulama,
                // jüri paneli, kanıt-URL denetimi veya entailment kapısı YOKTUR
                // (Python tarafındaki agent_core/agents/autonomous_verifier.py
                // sözleşmesi burada uygulanmıyor). UI etiketi buna göre
                // "MODEL BEYANI GÜVEN (DOĞRULANMADI)" olarak düzeltildi
                // (i18n/I18n.kt) — "TOPLAM SİSTEM GÜVENİ" doğrulanmış bir
                // ölçüm iddiasıydı.
                overallConfidence = analyzerResponse.bridge.resonanceScore,
                timestamp = System.currentTimeMillis()
            )

            val promptTokens = prompt.length / 4 // Rough estimate
            val completionTokens = responseText.length / 4 // Rough estimate
            emit(PipelineEvent.TelemetryUpdate(TelemetryData(
                cacheHitRate = "N/A (Canlı Çıkarım)",
                cacheHits = 0,
                llmCallsObserved = 1
            )))
            emit(PipelineEvent.Log(LogEntry(timeFormat.format(Date()), "SUCCESS", "LLM Çıkarımı Tamamlandı. ~${promptTokens + completionTokens} token işlendi.")))
            emit(PipelineEvent.Log(LogEntry(timeFormat.format(Date()), "SUCCESS", "360° İNSAN HARİTASI OLUŞTURULDU — TEK LLM ÇIKARIMI: bağımsız doğrulama, kanıt URL denetimi ve mühür (SHA-256) YOK.")))

            val redFlags = analyzerResponse.frictions.sensitivities.take(2)
            emit(PipelineEvent.Completed(
                profile = holisticProfile,
                resonanceScore = analyzerResponse.bridge.resonanceScore,
                approach = analyzerResponse.bridge.conversationStarterRationale,
                redFlags = redFlags
            ))

        } catch (e: Exception) {
            emit(PipelineEvent.Log(LogEntry(timeFormat.format(Date()), "ERROR", "API Hatası: ${e.message}")))
            emit(PipelineEvent.Failed("Gemini API Çağrısı Başarısız: ${e.message}"))
        }
    }
    fun evolveProfile(
        currentProfile: HolisticProfile,
        newEvidence: String,
        platforms: Set<String>,
        apiKey: String
    ): Flow<PipelineEvent> = flow {
        emit(PipelineEvent.Log(LogEntry(timeFormat.format(Date()), "INFO", "[SENTEZ AĞI] Yeni profil verisi sisteme ekleniyor...")))
        // [RÖNTGEN 2026-09-23] hayalet ajan adı düzeltildi; ayrıca ESKİ
        // profilin güven skoru yeni koşunun skoru gibi yayınlanıyordu
        // (ölçülmeyen değer). Yeni koşu 0.0 ile başlar, sonucu kendi çağrısı
        // belirler.
        emit(PipelineEvent.AgentUpdate("deep_inference", "RUNNING", 0.0))

        if (apiKey.isBlank()) {
            emit(PipelineEvent.Log(LogEntry(timeFormat.format(Date()), "ERROR", "GEMINI API ANAHTARI EKSİK!")))
            emit(PipelineEvent.Failed("Gemini API Anahtarı eksik."))
            return@flow
        }

        try {
            val currentJsonStr = jsonParser.encodeToString(currentProfile)

            val prompt = """
                Sen Pineal-Gland sisteminin "Bilişsel Keşif (Cognitive Recon Engine)" modülüsün.
                Bilişsel dilbilim (cognitive linguistics) prensipleriyle profili sürekli analiz eder ve vizyon haritasını netleştirirsin.
                Sana mevcut statik profil ve GÖZLEMLENEN YENİ VERİ / DAVRANIŞ (Bağlam) verilecektir.

                MEVCUT PROFİL (JSON):
                $currentJsonStr

                GÖZLEMLENEN YENİ KANIT / KIRINTI (Kullanıcı girdisi):
                $newEvidence
                (Bu verinin geldiği/ilişkili olduğu platformlar: ${platforms.joinToString(", ")} - Bu platformların psikolojik doğasını (örn: X'te reaktif, LinkedIn'de maskeli) hesaba kat.)

                GÖREVİN:
                1. Bu yeni veriyi derinlemesine analiz et (örn: "Bu adam Chopin dinliyor" demez, "Melankolik ses dizilimlerine yönelimi..." diyerek derinlemesine bilişsel bir çıkarım yapar).
                2. Mevcut profildeki özellikleri, çelişkileri, karanlık profil (Makyavelizm/Narsisizm/Psikopati) kanıtlarını ve iletişim kancalarını (bridge) bu YENİ KANITA GÖRE GÜNCELLE.
                3. Profilde ciddi bir değişiklik veya yeni bir "Depth (Derinlik)" saptarsan realityFindings veya contradictions içine ekle.
                4. Shadow Profile içerisindeki "semanticEvidence" kısımlarına yeni davranışın kanıtını yedir.
                5. Kesinlikle mevcut profilin JSON YAPISINI bozmadan, sadece güncellenmiş ve evrimleşmiş halini SADECE JSON olarak döndür.
            """.trimIndent()

            val request = GenerateContentRequest(
                contents = listOf(Content(parts = listOf(Part(text = prompt)))),
                generationConfig = GenerationConfig(
                    responseFormat = ResponseFormat(
                        text = ResponseFormatText(mimeType = "application/json")
                    )
                ),
                systemInstruction = Content(parts = listOf(Part(text = "You are the Recon Engine. Output ONLY valid JSON of the updated HolisticProfile structure without markdown blocks.")))
            )

            val apiResponse = RetrofitClient.service.generateContentPro(apiKey, request)
            var responseText = apiResponse.candidates?.firstOrNull()?.content?.parts?.firstOrNull()?.text ?: ""

            responseText = responseText.trim()
            if (responseText.startsWith("```json")) responseText = responseText.removePrefix("```json")
            if (responseText.startsWith("```")) responseText = responseText.removePrefix("```")
            if (responseText.endsWith("```")) responseText = responseText.removeSuffix("```")
            responseText = responseText.trim()

            val analyzerResponse = jsonParser.decodeFromString<AnalyzerResponse>(responseText)

            emit(PipelineEvent.Log(LogEntry(timeFormat.format(Date()), "SUCCESS", "[SENTEZ AĞI] Harita güncellendi, yeni veri bilişsel profile işlendi.")))
            emit(PipelineEvent.AgentUpdate("deep_inference", "COMPLETED", analyzerResponse.bridge.resonanceScore))

            val updatedProfile = HolisticProfile(
                username = currentProfile.username,
                passions = analyzerResponse.passions,
                frictions = analyzerResponse.frictions,
                cognitive = analyzerResponse.cognitive,
                bridge = analyzerResponse.bridge,
                depthReport = analyzerResponse.depthReport,
                shadowProfile = analyzerResponse.shadowProfile,
                overallConfidence = analyzerResponse.bridge.resonanceScore, // model beyanı (doğrulanmadı)
                timestamp = System.currentTimeMillis()
            )

            val redFlags = analyzerResponse.frictions.sensitivities.take(2)
            emit(PipelineEvent.Completed(
                profile = updatedProfile,
                resonanceScore = analyzerResponse.bridge.resonanceScore,
                approach = analyzerResponse.bridge.conversationStarterRationale,
                redFlags = redFlags
            ))

        } catch (e: Exception) {
            emit(PipelineEvent.Log(LogEntry(timeFormat.format(Date()), "ERROR", "Kılavuz Gemi API Hatası: ${e.message}")))
            emit(PipelineEvent.Failed("Kılavuz Gemi Çağrısı Başarısız: ${e.message}"))
        }
    }
}
