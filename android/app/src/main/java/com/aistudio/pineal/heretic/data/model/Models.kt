package com.aistudio.pineal.heretic.data.model

import kotlinx.serialization.Serializable

@Serializable
data class HolisticProfile(
    val username: String = "",
    val passions: PassionProfile = PassionProfile(),
    val frictions: FrictionProfile = FrictionProfile(),
    val cognitive: CognitiveStyle = CognitiveStyle(),
    val bridge: AuthenticBridge? = null,
    val depthReport: DepthReport = DepthReport(),
    val shadowProfile: ShadowProfile = ShadowProfile(),
    val overallConfidence: Double = 0.0,
    val timestamp: Long = System.currentTimeMillis()
)

@Serializable
data class PassionProfile(
    val corePassions: List<String> = emptyList(),
    val energizingTopics: List<String> = emptyList(),
    val flowTriggers: List<String> = emptyList(),
    val evidenceQuotes: List<String> = emptyList()
)

@Serializable
data class FrictionProfile(
    val sensitivities: List<String> = emptyList(),
    val stressTriggers: List<String> = emptyList(),
    val boundarySignals: List<String> = emptyList()
)

@Serializable
data class CognitiveMetrics(
    val creativity: Double = 0.0,
    val analytical: Double = 0.0,
    val empathy: Double = 0.0,
    val leadership: Double = 0.0,
    val adaptability: Double = 0.0
)

@Serializable
data class CognitiveStyle(
    val communicationTone: String = "",
    val complexityLevel: String = "",
    val socialOrientation: String = "",
    val humorStyle: String = "",
    val metrics: CognitiveMetrics = CognitiveMetrics()
)

@Serializable
data class AuthenticBridge(
    val sharedPassions: List<String> = emptyList(),
    val resonanceScore: Double = 0.0,
    val authenticOpeningTopic: String = "",
    val suggestedOpeningMessage: String = "",
    val conversationStarterRationale: String = ""
)

@Serializable
data class RealityFinding(
    val topic: String,
    val observation: String,
    val evidenceQuotes: List<String> = emptyList()
)

@Serializable
data class QuoteGuardSummary(
    val kept: Int = 0,
    val droppedFakeQuote: Int = 0
)

@Serializable
data class DepthReport(
    val realityIndex: Double = 0.0,
    val essenceOneLiner: String = "",
    val realityFindings: List<RealityFinding> = emptyList(),
    val contradictions: List<RealityFinding> = emptyList(),
    val quoteGuard: QuoteGuardSummary = QuoteGuardSummary()
)

@Serializable
data class VisualEvidence(
    val aestheticStyle: String = "",
    val visualEvidenceSummary: String = "",
    val detectedObjects: List<String> = emptyList(),
    val sceneTone: String = ""
)

@Serializable
data class TraitAnalysis(
    val level: String = "",
    val semanticEvidence: String = ""
)

@Serializable
data class DarkTriad(
    val narcissism: TraitAnalysis = TraitAnalysis(),
    val machiavellianism: TraitAnalysis = TraitAnalysis(),
    val psychopathy: TraitAnalysis = TraitAnalysis()
)

@Serializable
data class ShadowProfile(
    val manipulationRisk: String = "",
    val strategy: String = "",
    val darkProfile: DarkTriad = DarkTriad()
)

@Serializable
data class TelemetryData(
    val cacheHitRate: String = "",
    val cacheHits: Int = 0,
    val llmCallsObserved: Int = 0
)

data class AgentExecution(
    val id: String,
    val name: String,
    val colorHex: Long,
    var status: String = "", // IDLE, RUNNING, COMPLETED, HALTED
    var confidence: Double = 0.0
)

data class LogEntry(
    val ts: String,
    val level: String, // INFO, WARNING, ERROR, SUCCESS
    val msg: String
)

data class ChatMessage(
    val id: String = java.util.UUID.randomUUID().toString(),
    val sender: String, // SİZ, ASPASIA, SİSTEM
    val text: String,
    val timestamp: Long = System.currentTimeMillis(),
    val imageUri: String? = null
)
