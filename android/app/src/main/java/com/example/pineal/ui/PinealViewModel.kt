package com.example.pineal.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider

import android.content.Context
import android.graphics.BitmapFactory
import android.net.Uri
import android.util.Log

import androidx.lifecycle.viewModelScope
import com.example.pineal.BuildConfig
import com.example.pineal.data.local.AnalysisEntity
import com.example.pineal.data.local.PinealRepository
import com.example.pineal.data.model.*
import com.example.pineal.engine.AspasiaChatEngine
import com.example.pineal.engine.ForensicReconEngine
import com.example.pineal.engine.ForensicHypothesis
import com.example.pineal.data.local.HypothesisEntity
import com.example.pineal.engine.PinealAnalyzerEngine
import com.example.pineal.engine.PipelineEvent
import com.example.pineal.i18n.AppLanguage
import com.example.pineal.i18n.AppStrings
import com.example.pineal.i18n.StringsDict
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

enum class CockpitTab {
    PROFILE_360, ASPASIA_CHAT, LOGS_TELEMETRY, HISTORY
}

data class PinealUiState(
    val language: AppLanguage = AppLanguage.TR,
    val selectedTab: CockpitTab = CockpitTab.PROFILE_360,
    val targetUrl: String = "",
    val rituals: String = "",
    val playlist: String = "",
    val envies: String = "",
    val selectedPlatforms: Set<String> = emptySet(),
    val apiKey: String = "",
    val osintApiKey: String = "",
    val useDeepExtraction: Boolean = false,
    val cookie: String = "",
    val isVaultSealed: Boolean = false,
    val useCloudApi: Boolean = false,
    val selectedModel: String = "gemini-flash-latest",
    val isProcessing: Boolean = false,
    val taskState: String = "IDLE",
    val taskId: String = "",
    val overallConfidence: Double = 0.0,
    val resonanceScore: Double = 0.0,
    val resonanceApproach: String = "",
    val redFlags: List<String> = emptyList(),
    val currentAgentId: String = "",
    val agents: List<AgentExecution> = defaultAgents(),
    val logs: List<LogEntry> = defaultLogs(),
    val telemetry: TelemetryData = TelemetryData(),
    val holisticProfile: HolisticProfile? = null,
    val chatMessages: List<ChatMessage> = defaultChatMessages(),
    val chatInput: String = "",
    val attachedImageUri: String? = null,
    val isChatSending: Boolean = false,
    val historyList: List<AnalysisEntity> = emptyList(),
    val toastMessage: String? = null
) {
    val strings: StringsDict
        get() = if (language == AppLanguage.TR) AppStrings.tr else AppStrings.en
}

private fun defaultAgents() = listOf(
    AgentExecution("deep_inference", "DERİN ÇIKARIM AĞI (LLM)", 0xFFA855F7)
)

private fun defaultLogs() = listOf(
    LogEntry("00:00:01", "INFO", "Pineal-Gland v${BuildConfig.VERSION_NAME} Bilişsel Sentez Merkezi Hazır (Room + Coroutines)"),
    LogEntry("00:00:02", "INFO", "Bilişsel Sentez Hattı ve Profil Analiz Paneli Aktif.")
)

private fun defaultChatMessages() = listOf(
    ChatMessage(
        sender = "ASPASIA",
        text = "Sistem çevrimiçi. Verileri ve telemetriyi incelemeye hazırım."
    )
)

class PinealViewModel(
    private val repository: PinealRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(PinealUiState())
    val uiState: StateFlow<PinealUiState> = _uiState.asStateFlow()

    private val analyzerEngine = PinealAnalyzerEngine()
    private val aspasiaEngine = AspasiaChatEngine()
    private val reconEngine = ForensicReconEngine()

    private val timeFormat = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
    private val json = Json { ignoreUnknownKeys = true; prettyPrint = true }

    init {
        viewModelScope.launch {
            repository.history.collect { history ->
                _uiState.update { it.copy(historyList = history) }
            }
        }
    }

    fun setLanguage(lang: AppLanguage) {
        _uiState.update { it.copy(language = lang) }
    }

    fun selectTab(tab: CockpitTab) {
        _uiState.update { it.copy(selectedTab = tab) }
    }

    fun setTargetUrl(url: String) {
        _uiState.update { it.copy(targetUrl = url) }
        if (url.isNotBlank()) loadTargetHypotheses(url)
    }
    fun setRituals(rituals: String) { _uiState.update { it.copy(rituals = rituals) } }
    fun setPlaylist(playlist: String) { _uiState.update { it.copy(playlist = playlist) } }
    fun setEnvies(envies: String) { _uiState.update { it.copy(envies = envies) } }
    fun setApiKey(key: String) { _uiState.update { it.copy(apiKey = key) } }
    fun setCookie(cookie: String) { _uiState.update { it.copy(cookie = cookie) } }
    fun setOsintApiKey(key: String) { _uiState.update { it.copy(osintApiKey = key) } }
    fun toggleDeepExtraction(enabled: Boolean) { _uiState.update { it.copy(useDeepExtraction = enabled) } }
    fun setModel(model: String) { _uiState.update { it.copy(selectedModel = model) } }
    fun toggleCloudApi(useCloud: Boolean) { _uiState.update { it.copy(useCloudApi = useCloud) } }

    /**
     * [RÖNTGEN 2026-09-23] DÜRÜST KASA DURUMU.
     *
     * Eski sürüm bu metotta `isVaultSealed = true` yapıp "Kasa mühürlendi ·
     * Kimlik ve anahtarlar bellekte güvenceye alındı" logluyordu; UI yeşil
     * asma kilit + "KASA • AKTİF (MÜHÜRLENDİ)" basıyordu. Gerçekte Android
     * tarafında HİÇBİR mühürleme/şifreleme yok: anahtarlar düz String olarak
     * StateFlow içinde yaşıyor (EncryptedSharedPreferences / Android Keystore
     * kullanılmıyor) ve diske hiç yazılmıyor. Yani ekrandaki güvenlik iddiası
     * ölçülmeyen bir durumdu — Python tarafındaki kasa mandalı sözleşmesi
     * (backend/api.py `_check_vault_interlock`, gerçek anahtar malzemesi
     * şartı) burada UYGULANMIYOR.
     *
     * Bu metod artık yalnız operatörün "kasa modu" işaretini tutar ve bunu
     * olduğu gibi söyler. Gerçek mühür için: Keystore-backed şifreli saklama +
     * anahtar malzemesi doğrulaması eklenmeli (docs/reports/... adım 7).
     */
    fun sealVault() {
        _uiState.update {
            val log = LogEntry(
                timeFormat.format(Date()),
                "WARNING",
                "Kasa modu İŞARETLENDİ (şifreli saklama YOK): anahtarlar yalnız bellekte, düz metin StateFlow içinde tutuluyor."
            )
            it.copy(isVaultSealed = true, logs = it.logs + log)
        }
    }

    fun togglePlatform(platform: String) {
        _uiState.update {
            val current = it.selectedPlatforms.toMutableSet()
            if (current.contains(platform)) {
                current.remove(platform)
            } else {
                current.add(platform)
            }
            it.copy(selectedPlatforms = current)
        }
    }

    fun triggerAnalysis() {
        val state = _uiState.value
        if (state.isProcessing || state.targetUrl.isBlank()) return

        val newTaskId = "TASK-" + UUID.randomUUID().toString().substring(0, 8).uppercase()

        _uiState.update {
            it.copy(
                isProcessing = true,
                taskState = "PROCESSING",
                taskId = newTaskId,
                currentAgentId = "mirror_truth",
                agents = defaultAgents(),
                toastMessage = null
            )
        }

        viewModelScope.launch {
            analyzerEngine.executeAnalysisPipeline(
                targetUrl = state.targetUrl,
                rituals = state.rituals,
                playlist = state.playlist,
                envies = state.envies,
                platforms = state.selectedPlatforms,
                apiKey = state.apiKey,
                useCloudApi = state.useCloudApi
            ).collect { event ->
                when (event) {
                    is PipelineEvent.Log -> {
                        _uiState.update { it.copy(logs = it.logs + event.entry) }
                    }
                    is PipelineEvent.AgentUpdate -> {
                        _uiState.update { current ->
                            val updatedAgents = current.agents.map { agent ->
                                if (agent.id == event.agentId) {
                                    agent.copy(status = event.status, confidence = event.confidence)
                                } else agent
                            }
                            current.copy(
                                agents = updatedAgents,
                                currentAgentId = event.agentId
                            )
                        }
                    }
                    is PipelineEvent.TelemetryUpdate -> {
                        _uiState.update { it.copy(telemetry = event.telemetry) }
                    }
                    is PipelineEvent.PartialProfile -> {
                        _uiState.update { it.copy(holisticProfile = event.profile) }
                    }
                    is PipelineEvent.Completed -> {
                        _uiState.update {
                            it.copy(
                                isProcessing = false,
                                taskState = "COMPLETED",
                                holisticProfile = event.profile,
                                overallConfidence = event.profile.overallConfidence,
                                resonanceScore = event.resonanceScore,
                                resonanceApproach = event.approach,
                                redFlags = event.redFlags
                            )
                        }
                        try {
                            val entity = AnalysisEntity(
                                targetUrl = state.targetUrl,
                                username = event.profile.username,
                                rituals = state.rituals,
                                playlist = state.playlist,
                                envies = state.envies,
                                resonanceScore = event.resonanceScore,
                                overallConfidence = event.profile.overallConfidence,
                                fullJson = json.encodeToString(event.profile),
                                timestamp = System.currentTimeMillis()
                            )
                            repository.saveAnalysis(entity)
                        } catch (e: Exception) {
                            e.printStackTrace()
                        }
                    }
                    is PipelineEvent.Failed -> {
                        _uiState.update {
                            it.copy(
                                isProcessing = false,
                                taskState = "FAILED",
                                logs = it.logs + LogEntry(timeFormat.format(Date()), "ERROR", "HATA: ${event.reason}")
                            )
                        }
                    }
                }
            }
        }
    }


    val liveReconState: StateFlow<List<ForensicHypothesis>> = reconEngine.liveReconState
    val reconErrorState: StateFlow<String?> = reconEngine.errorState

    fun clearReconError() {
        reconEngine.clearErrorState()
    }

    fun feedNewEvidence(newInfo: String) {
        val state = _uiState.value
        if (state.isProcessing || state.targetUrl.isBlank()) return

        _uiState.update { it.copy(isProcessing = true, logs = it.logs + LogEntry(timeFormat.format(Date()), "INFO", "[KILAVUZ GEMİ] Yeni kanıt işleniyor...")) }

        viewModelScope.launch {
            try {
                reconEngine.injectEvidence(newInfo, state.apiKey, "USER_INPUT")

                val currentHypotheses = reconEngine.liveReconState.value
                val entities = currentHypotheses.map {
                    HypothesisEntity(
                        targetId = state.targetUrl,
                        trait = it.psychologicalTrait,
                        implication = it.forensicImplication,
                        status = it.status,
                        evidence = it.extractedEvidence,
                        missingDataVectors = it.missingDataVectors.joinToString(",")
                    )
                }
                repository.clearTargetHypotheses(state.targetUrl)
                repository.saveHypotheses(entities)

                _uiState.update { it.copy(isProcessing = false) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isProcessing = false, logs = it.logs + LogEntry(timeFormat.format(Date()), "ERROR", "HATA: ${e.message}")) }
            }
        }
    }

    fun loadTargetHypotheses(targetId: String) {
        viewModelScope.launch {
            repository.getHypotheses(targetId).collect { entities ->
                val hypotheses = entities.map {
                    ForensicHypothesis(
                        psychologicalTrait = it.trait,
                        forensicImplication = it.implication,
                        status = it.status,
                        extractedEvidence = it.evidence,
                        missingDataVectors = if (it.missingDataVectors.isNotBlank()) it.missingDataVectors.split(",") else emptyList()
                    )
                }
                reconEngine.setReconState(hypotheses)
            }
        }
    }
    fun setChatInput(text: String) { _uiState.update { it.copy(chatInput = text) } }
    fun setAttachedImage(uri: String?) { _uiState.update { it.copy(attachedImageUri = uri) } }

    fun sendChatMessage() {
        val state = _uiState.value
        val text = state.chatInput.trim()
        val image = state.attachedImageUri
        if (text.isBlank() && image == null) return

        val userMsg = ChatMessage(
            sender = state.strings.you,
            text = if (image != null) "[GÖRSEL / IMAGE] $text" else text,
            imageUri = image
        )

        _uiState.update {
            it.copy(
                chatMessages = it.chatMessages + userMsg,
                chatInput = "",
                attachedImageUri = null,
                isChatSending = true
            )
        }

        viewModelScope.launch {
            kotlinx.coroutines.delay(600)

            val replyText = aspasiaEngine.generateResponse(
                userMessage = text,
                currentProfile = state.holisticProfile,
                liveHypotheses = reconEngine.liveReconState.value,
                hasImage = image != null,
                imageBitmap = null, // simplified for now due to context issues
                language = state.language,
                apiKey = state.apiKey
            )
            val aspasiaMsg = ChatMessage(
                sender = "ASPASIA",
                text = replyText
            )
            _uiState.update {
                it.copy(
                    chatMessages = it.chatMessages + aspasiaMsg,
                    isChatSending = false
                )
            }
        }
    }

    fun askExplainState() {
        val q = if (_uiState.value.language == AppLanguage.TR)
            "Şu anki telemetri ve analiz durumunu özetler misin? Hangi aşamadayız?"
        else
            "Can you summarize the current telemetry and analysis state? Where are we?"
        setChatInput(q)
        sendChatMessage()
    }

    fun deleteHistoryItem(id: Long) {
        viewModelScope.launch {
            repository.deleteAnalysis(id)
        }
    }

    fun clearAllHistory() {
        viewModelScope.launch {
            repository.clearHistory()
        }
    }

    fun loadFromHistory(entity: AnalysisEntity) {
        _uiState.update {
            try {
                val profile = json.decodeFromString<HolisticProfile>(entity.fullJson)
                it.copy(
                    targetUrl = entity.targetUrl,
                    rituals = entity.rituals,
                    playlist = entity.playlist,
                    envies = entity.envies,
                    holisticProfile = profile,
                    resonanceScore = entity.resonanceScore,
                    overallConfidence = entity.overallConfidence,
                    selectedTab = CockpitTab.PROFILE_360
                )
            } catch (e: Exception) {
                it.copy(
                    targetUrl = entity.targetUrl,
                    rituals = entity.rituals,
                    playlist = entity.playlist,
                    envies = entity.envies,
                    selectedTab = CockpitTab.PROFILE_360
                )
            }
        }
    }

    fun clearToast() {
        _uiState.update { it.copy(toastMessage = null) }
    }
}

class PinealViewModelFactory(
    private val repository: PinealRepository
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        return PinealViewModel(repository) as T
    }
}
