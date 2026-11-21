package com.aistudio.pineal.heretic.data.model

import kotlinx.serialization.Serializable

@Serializable
data class AnalyzerResponse(
    val depthReport: DepthReport,
    val shadowProfile: ShadowProfile,
    val passions: PassionProfile,
    val frictions: FrictionProfile,
    val cognitive: CognitiveStyle,
    val bridge: AuthenticBridge
)
