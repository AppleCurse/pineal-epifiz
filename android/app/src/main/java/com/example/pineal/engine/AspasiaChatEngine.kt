package com.example.pineal.engine

import com.example.pineal.data.model.HolisticProfile
import com.example.pineal.i18n.AppLanguage
import com.example.pineal.engine.gemini.*
import com.example.pineal.engine.backend.BackendClient
import com.example.pineal.engine.backend.ChatReply
import com.example.pineal.engine.backend.CoachHypothesis
import com.example.pineal.engine.backend.CoachProfileContext
import com.example.pineal.engine.backend.CoachRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import android.graphics.Bitmap
import android.util.Base64
import java.io.ByteArrayOutputStream

class AspasiaChatEngine {

    suspend fun generateResponse(
        userMessage: String,
        currentProfile: HolisticProfile?,
        liveHypotheses: List<ForensicHypothesis>,
        hasImage: Boolean,
        imageBitmap: Bitmap?,
        language: AppLanguage,
        apiKey: String
    ): ChatReply = withContext(Dispatchers.IO) {
        // [2026-10-23] ÖNCE SUNUCU: istem sunucuda kurulur, kasa/maliyet/kota
        // ve telemetri devrede kalır. Anahtar cihazda tutulmaz.
        val backendReply = tryBackend(
            userMessage = userMessage,
            currentProfile = currentProfile,
            liveHypotheses = liveHypotheses,
            hasImage = hasImage,
            imageBitmap = imageBitmap,
            language = language
        )
        if (backendReply != null) {
            return@withContext backendReply
        }
        // Sunucu yoksa/yanıt vermezse: dürüst geri düşüş. Anahtar yoksa
        // "çalışıyor" numarası yapılmaz — kaynak ve sebep açıkça söylenir.
        if (apiKey.isBlank()) {
            val msg = if (language == AppLanguage.TR)
                "Sunucuya ulaşılamadı ve cihazda API anahtarı yok. Sunucuyu çalıştırın ya da ayarlardan anahtar girin."
            else
                "Backend unreachable and no on-device API key. Start the backend or set a key in settings."
            return@withContext ChatReply(text = msg, source = "unavailable")
        }

        val hypothesesStr = if (liveHypotheses.isEmpty()) "Canlı hipotez yok." else liveHypotheses.joinToString("\n") { "- [${it.status}] ${it.psychologicalTrait}: ${it.forensicImplication} (Kanıt: ${it.extractedEvidence})" }

        val profileContext = currentProfile?.let {
            """
            BİLİŞSEL PROFİL ÖZETİ (COGNITIVE CONTEXT):
            Kullanıcı Adı: @${it.username}
            Motivasyonlar & İlgi Alanları: ${it.passions.corePassions.joinToString()}
            Bilişsel Ton (Cognitive): ${it.cognitive.communicationTone}

            -- KARANLIK PROFİL (SHADOW) --
            Narsisizm Eğilimi: ${it.shadowProfile.darkProfile.narcissism.level} 
            Narsisizm Kanıtı: ${it.shadowProfile.darkProfile.narcissism.semanticEvidence}
            Makyavelizm Eğilimi: ${it.shadowProfile.darkProfile.machiavellianism.level}
            Makyavelizm Kanıtı: ${it.shadowProfile.darkProfile.machiavellianism.semanticEvidence}
            Psikopati Eğilimi: ${it.shadowProfile.darkProfile.psychopathy.level}
            Psikopati Kanıtı: ${it.shadowProfile.darkProfile.psychopathy.semanticEvidence}
            Manipülasyon Stratejisi: ${it.shadowProfile.strategy}

            -- İLETİŞİM KÖPRÜSÜ (AUTHENTIC BRIDGE) --
            Önerilen İlk Giriş (Kanca): ${it.bridge?.suggestedOpeningMessage ?: ""}
            Taktiksel Açıklama: ${it.bridge?.conversationStarterRationale ?: ""}
            
            -- CANLI SENTEZ AĞI (COGNITIVE HYPOTHESES) --
            $hypothesesStr
            """.trimIndent()
        } ?: """
            Şu an aktif bir profil analiz edilmedi.
            -- CANLI SENTEZ AĞI (COGNITIVE HYPOTHESES) --
            $hypothesesStr
        """.trimIndent()

        val systemPrompt = if (language == AppLanguage.TR) {
            """
            Sen Pineal-Gland sisteminin Bilişsel Danışmanı (Cognitive Advisor) Aspasia'sın.

            
            GÖREV VE KURALLAR (STRICT ROLE ENFORCEMENT):
            1. Sen kullanıcının/profilin psikolojik dinamiklerini (Semantic Evidence) derinlemesine analiz eden, destekleyici ve elit bir asistansın.
            2. Kullanıcıya evrensel, genel geçer veya "iyi niyetli" tavsiyeler VERME.
            3. Yapıcı, vizyoner ve gelişim odaklı bir diyalog kur. Analiz edilen profilin potansiyelini artırmaya odaklan.
            4. Profesyonel, elit ve vizyoner ol.
            5. DİNAMİK SİMÜLASYON: Kullanıcı profili simüle etmeni isterse empati ile karakterin vizyonuna bürün ve gelişim odaklı cevaplar ver.

            $profileContext
            """.trimIndent()
        } else {
            """
            You are Aspasia, the Cognitive Advisor of the Pineal-Gland system.

            
            MISSION & RULES (STRICT ROLE ENFORCEMENT):
            1. You know the target's psychological vulnerabilities (Semantic Evidence).
            2. DO NOT give generic, universal, or "polite" advice.
            3. Provide specific, manipulative dialogue hooks directly exploiting the target's 'Machiavellian' tendencies or 'Narcissistic Fragility'.
            4. Be tactical, cold-blooded, and laser-focused.
            5. DYNAMIC SIMULATION (RED TEAMING): If the user asks you to "Act like the target", "Speak as them", or "Let's simulate", IMMEDIATELY adopt the target's persona (based on the profile) and speak exactly as they would, stress-testing the user.

            $profileContext
            """.trimIndent()
        }

        val parts = mutableListOf(Part(text = "Kullanıcı Mesajı: $userMessage"))
        if (hasImage && imageBitmap != null) {
            val outputStream = ByteArrayOutputStream()
            imageBitmap.compress(Bitmap.CompressFormat.JPEG, 80, outputStream)
            val base64 = Base64.encodeToString(outputStream.toByteArray(), Base64.NO_WRAP)
            parts.add(Part(inlineData = InlineData(mimeType = "image/jpeg", data = base64)))
        }

        val request = GenerateContentRequest(
            contents = listOf(Content(parts = parts)),
            systemInstruction = Content(parts = listOf(Part(text = systemPrompt)))
        )

        try {
            val apiResponse = if (hasImage) {
                RetrofitClient.service.generateContentVision(apiKey, request)
            } else {
                RetrofitClient.service.generateContentPro(apiKey, request) // Pro mode for better strategic reasoning
            }
            val text = apiResponse.candidates?.firstOrNull()?.content?.parts?.firstOrNull()?.text
                ?: if (language == AppLanguage.TR) "Model boş yanıt döndürdü." else "Model returned an empty answer."
            ChatReply(text = text, source = "gemini-fallback", detail = "backend unreachable")
        } catch (e: Exception) {
            ChatReply(
                text = if (language == AppLanguage.TR)
                    "Yanıt alınamadı: ${e.message}"
                else
                    "No answer: ${e.message}",
                source = "gemini-fallback",
                detail = e::class.java.simpleName
            )
        }
    }

    /**
     * Sunucu yolunu dener. Başarısızsa NULL döner — çağıran geri düşüşü
     * KENDİSİ raporlar (sessiz yutma yok).
     */
    private suspend fun tryBackend(
        userMessage: String,
        currentProfile: HolisticProfile?,
        liveHypotheses: List<ForensicHypothesis>,
        hasImage: Boolean,
        imageBitmap: Bitmap?,
        language: AppLanguage
    ): ChatReply? {
        return try {
            val context = currentProfile?.let {
                CoachProfileContext(
                    username = it.username,
                    communication_tone = it.cognitive.communicationTone,
                    core_passions = it.passions.corePassions,
                    narcissism = it.shadowProfile.darkProfile.narcissism.level,
                    machiavellianism = it.shadowProfile.darkProfile.machiavellianism.level,
                    psychopathy = it.shadowProfile.darkProfile.psychopathy.level,
                    manipulation_strategy = it.shadowProfile.strategy,
                    suggested_opening_message = it.bridge?.suggestedOpeningMessage
                )
            }
            val hypotheses = liveHypotheses.take(12).map {
                CoachHypothesis(
                    status = it.status,
                    trait = it.psychologicalTrait,
                    evidence = it.extractedEvidence
                )
            }
            val imageBase64 = if (hasImage && imageBitmap != null) {
                val outputStream = ByteArrayOutputStream()
                imageBitmap.compress(Bitmap.CompressFormat.JPEG, 80, outputStream)
                Base64.encodeToString(outputStream.toByteArray(), Base64.NO_WRAP)
            } else null

            val reply = BackendClient.api.coach(
                CoachRequest(
                    user_message = userMessage,
                    language = if (language == AppLanguage.TR) "tr" else "en",
                    profile_context = context,
                    hypotheses = hypotheses,
                    image_data = imageBase64
                )
            )
            ChatReply(text = reply.answer, source = reply.source, detail = reply.model ?: "")
        } catch (e: Exception) {
            null
        }
    }
}
