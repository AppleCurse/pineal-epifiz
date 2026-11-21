package com.aistudio.pineal.heretic.engine

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PinealAnalyzerEngineTest {
    @Test
    fun executeAnalysisPipeline_missingApiKey_emitsFailed() = runBlocking {
        val engine = PinealAnalyzerEngine()
        val flow = engine.executeAnalysisPipeline(
            targetUrl = "@testuser",
            rituals = "",
            playlist = "",
            envies = "",
            platforms = emptySet(),
            useCloudApi = true,
            apiKey = "" // Missing API KEY
        )
        val events = flow.toList()

        // At least one Log with ERROR and one Failed event should be emitted
        assertTrue("Should emit Failed event", events.any { it is PipelineEvent.Failed })

        
        // At least one Log with ERROR and one Failed event should be emitted
        assertTrue("Should emit Failed event", events.any { it is PipelineEvent.Failed })
        
        val failedEvent = events.find { it is PipelineEvent.Failed } as PipelineEvent.Failed
        assertEquals("Gemini API Anahtarı eksik.", failedEvent.reason)
    }
}
