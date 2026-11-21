package com.aistudio.pineal.heretic.data.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelsTest {
    @Test
    fun verifyHolisticProfileHasNoMockData() {
        val profile = HolisticProfile()
        assertEquals("Username must be empty string", "", profile.username)
        assertEquals("Overall confidence must be 0.0", 0.0, profile.overallConfidence, 0.0001)

        val passions = PassionProfile()
        assertTrue("Core passions must be empty", passions.corePassions.isEmpty())
        assertTrue("Flow triggers must be empty", passions.flowTriggers.isEmpty())

        val depth = DepthReport()
        assertEquals("Reality index must be 0.0", 0.0, depth.realityIndex, 0.0001)
        assertTrue("Contradictions must be empty", depth.contradictions.isEmpty())

        val visual = VisualEvidence()
        assertEquals("Aesthetic style must be empty string", "", visual.aestheticStyle)
    }
}
