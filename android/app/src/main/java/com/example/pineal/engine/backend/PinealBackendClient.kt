package com.example.pineal.engine.backend

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import retrofit2.http.Body
import retrofit2.http.POST
import java.util.concurrent.TimeUnit

/**
 * Pineal backend köprüsü (2026-10-23).
 *
 * Neden: uygulama Aspasia koç sohbetini doğrudan Gemini'ye gönderiyordu.
 * Sonuç: LLM anahtarı cihazda, kasa/maliyet/kota kapıları devre dışı,
 * model istemi denetlenemez ve telemetri üretilmiyordu.
 *
 * Yeni akış: yapılandırılmış bağlam → `/api/mobile/coach` (sunucu istemi
 * kurar, gateway/kasa/kota aynen geçerli). Sunucuya ulaşılamazsa uygulama
 * **dürüst geri düşüş** yapar ve hangi yolu kullandığını kullanıcıya söyler
 * (bkz. [AspasiaChatEngine] → `ChatReply.source`).
 */

@Serializable
data class CoachProfileContext(
    val username: String? = null,
    val communication_tone: String? = null,
    val core_passions: List<String> = emptyList(),
    val narcissism: String? = null,
    val machiavellianism: String? = null,
    val psychopathy: String? = null,
    val manipulation_strategy: String? = null,
    val suggested_opening_message: String? = null
)

@Serializable
data class CoachHypothesis(
    val status: String? = null,
    val trait: String? = null,
    val evidence: String? = null
)

@Serializable
data class CoachRequest(
    val client_id: String = "android",
    val user_message: String,
    val language: String = "tr",
    val model_override: String? = null,
    val profile_context: CoachProfileContext? = null,
    val hypotheses: List<CoachHypothesis> = emptyList(),
    val image_data: String? = null
)

@Serializable
data class CoachReply(
    val answer: String,
    val source: String = "backend",
    val model: String? = null,
    val language: String? = null,
    val context_fields: List<String> = emptyList()
)

@Serializable
data class BackendErrorBody(
    val error: BackendError? = null
)

@Serializable
data class BackendError(
    val code: String? = null,
    val message: String? = null,
    val reason: String? = null
)

interface PinealBackendApi {
    @POST("api/mobile/coach")
    suspend fun coach(@Body request: CoachRequest): CoachReply
}

object BackendClient {
    /**
     * Backend tabanı. Yayın derlemesinde [BuildConfigField] ile verilir;
     * emülatör varsayılanı 10.0.2.2 (host makine) adresidir.
     */
    val baseUrl: String = "http://10.0.2.2:8000/"

    private val okHttpClient = OkHttpClient.Builder()
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS)
        .writeTimeout(90, TimeUnit.SECONDS)
        .build()

    private val json = Json { ignoreUnknownKeys = true; isLenient = true; encodeDefaults = true }

    val api: PinealBackendApi by lazy {
        Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(okHttpClient)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(PinealBackendApi::class.java)
    }
}

/**
 * Yanıtın NEREDEN geldiğini taşır — "backend" ya da "gemini-fallback".
 * Arayüz bunu gösterir; sessiz geri düşüş yok.
 */
data class ChatReply(
    val text: String,
    val source: String,
    val detail: String = ""
)
