package com.aistudio.pineal.heretic.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "recon_hypotheses")
data class HypothesisEntity(
    @PrimaryKey(autoGenerate = true) val id: Int = 0,
    val targetId: String,
    val trait: String,
    val implication: String,
    val status: String,
    val evidence: String,
    val missingDataVectors: String = "",
    val timestamp: Long = System.currentTimeMillis()
)
