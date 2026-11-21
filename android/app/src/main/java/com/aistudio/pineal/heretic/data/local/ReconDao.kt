package com.aistudio.pineal.heretic.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface ReconDao {
    @Query("SELECT * FROM recon_hypotheses WHERE targetId = :targetId ORDER BY timestamp DESC")
    fun getTargetHypotheses(targetId: String): Flow<List<HypothesisEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertHypotheses(hypotheses: List<HypothesisEntity>)

    
    @Query("DELETE FROM recon_hypotheses WHERE targetId = :targetId")
    suspend fun clearTarget(targetId: String)
}
