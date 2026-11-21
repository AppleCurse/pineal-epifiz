package com.aistudio.pineal.heretic.engine

import com.aistudio.pineal.heretic.engine.gemini.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString

enum class ReconConfidence {
    SONAR_ATILDI,
    KANITLANDI,
    KRITIK_FIRSAT
}

@Serializable
data class ForensicHypothesis(
    val psychologicalTrait: String,
    val forensicImplication: String,
    val status: String,
    val extractedEvidence: String,
    val missingDataVectors: List<String> = emptyList()
)

@Serializable
data class ReconUpdateResponse(
    val updatedHypotheses: List<ForensicHypothesis>,
    val missingDataVectors: List<String> = emptyList()
)

class ForensicReconEngine {

    private val _liveReconState = MutableStateFlow<List<ForensicHypothesis>>(emptyList())
    val liveReconState: StateFlow<List<ForensicHypothesis>> = _liveReconState.asStateFlow()

    private val _errorState = MutableStateFlow<String?>(null)
    val errorState: StateFlow<String?> = _errorState.asStateFlow()

    private val jsonParser = Json { ignoreUnknownKeys = true; isLenient = true; encodeDefaults = true }

    suspend fun injectEvidence(rawEvidence: String, apiKey: String, contextType: String = "TEXT_OR_RITUAL") {
        _errorState.value = null

        val currentHypotheses = _liveReconState.value
        val currentJsonStr = if (currentHypotheses.isEmpty()) "Henüz hipotez yok (İlk Sonar)" else jsonParser.encodeToString(currentHypotheses)

        val prompt = """
            Sen profesyonel bir Bilişsel Dilbilim (Cognitive Linguistics) ve Davranışsal Sentez motorusun.
            GÖREVİN: Kullanıcının verdiği kırıntı verileri (ham metin, ritüel, kelime seçimi) inceleyerek psikolojik hipotezler kurmak.

            KATI KURALLAR (İHLAL EDİLEMEZ):
            1. Asla matematiksel skor, yüzde, olasılık veya istatistik ÜRETME (Örn: 0.82 veya %76 gibi ifadeler KESİNLİKLE YASAK). Tahmin yapmıyoruz, objektif sentez yapıyoruz.
            2. Her hipoteze KATI BİR DURUM ETİKETİ (status) ata. Bu etiketler SADECE şu üçünden biri olabilir:
               - "SONAR_ATILDI": Tek bir kırıntıdan sezilen, henüz doğrulanmamış zayıf sezgi.
               - "KANITLANDI": İki veya daha fazla farklı kırıntı aynı kalıbı doğruladı.
               - "KRITIK_FIRSAT": Kişinin potansiyelini maksimize edebileceği, derin motivasyon noktası.
            3. Sadece sunulan kanıtın (evidence) alt metnini oku. Asla profilin tamamını kafadan uydurma.
            4. Haritayı netleştirmek için 'missingDataVectors' alanına makinenin ihtiyaç duyduğu eksik veri türlerini yaz.

            Mevcut Keşif Haritası (Hipotezler): $currentJsonStr
            Yeni Gelen Bağlamsal Veri [$contextType]: "$rawEvidence"

            Gelen veriyi Bilişsel Dilbilim çerçevesinde incele. Önceki hipotezleri güçlendir, çürüt, durumlarını güncelle (SONAR_ATILDI -> KANITLANDI vb.) veya yenilerini ekle.
            Çıktı SADECE geçerli bir ReconUpdateResponse formatında JSON olmalıdır. Markdown (```json) KULLANMA.
        """.trimIndent()

        try {
            val request = GenerateContentRequest(
                contents = listOf(Content(parts = listOf(Part(text = prompt)))),
                generationConfig = GenerationConfig(
                    responseFormat = ResponseFormat(text = ResponseFormatText(mimeType = "application/json")),
                    temperature = 0.2f
                ),
                systemInstruction = Content(parts = listOf(Part(text = "You are the Recon Engine. Output ONLY valid JSON.")))
            )

            val apiResponse = RetrofitClient.service.generateContentPro(apiKey, request)
            var responseText = apiResponse.candidates?.firstOrNull()?.content?.parts?.firstOrNull()?.text ?: throw IllegalStateException("Sentez ağı boş yanıt döndürdü.")

            responseText = responseText.trim()
            if (responseText.startsWith("```json")) responseText = responseText.removePrefix("```json")
            if (responseText.startsWith("```")) responseText = responseText.removePrefix("```")
            if (responseText.endsWith("```")) responseText = responseText.removeSuffix("```")
            responseText = responseText.trim()

            val reconUpdate = jsonParser.decodeFromString<ReconUpdateResponse>(responseText)
            val normalizedHypotheses = reconUpdate.updatedHypotheses.map { h ->
                h.copy(status = h.status.trim().uppercase()
                    .replace("İ", "I").replace("Ç", "C")
                    .replace("Ş", "S").replace("Ğ", "G")
                    .replace("Ü", "U").replace("Ö", "O"))
            }
            _liveReconState.update { normalizedHypotheses }

        } catch (e: Exception) {
            _errorState.value = "Keşif Motoru Hatası: ${e.message}"
        }
    }

    fun clearErrorState() {
        _errorState.value = null
    }

    fun clearReconState() {
        _liveReconState.value = emptyList()
        _errorState.value = null
    }

    fun setReconState(hypotheses: List<ForensicHypothesis>) {
        _liveReconState.value = hypotheses
    }
}
