package com.aistudio.pineal.heretic.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "analysis_history")
data class AnalysisEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val targetUrl: String,
    val username: String,
    val rituals: String,
    val playlist: String,
    val envies: String,
    val resonanceScore: Double,
    val overallConfidence: Double,
    val fullJson: String,
    val timestamp: Long = System.currentTimeMillis()
)
