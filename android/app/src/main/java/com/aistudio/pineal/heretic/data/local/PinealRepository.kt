package com.aistudio.pineal.heretic.data.local

import kotlinx.coroutines.flow.Flow

class PinealRepository(private val dao: AnalysisDao, private val reconDao: ReconDao) {
    fun getHypotheses(targetId: String) = reconDao.getTargetHypotheses(targetId)
    suspend fun saveHypotheses(hypotheses: List<HypothesisEntity>) = reconDao.insertHypotheses(hypotheses)
    suspend fun clearTargetHypotheses(targetId: String) = reconDao.clearTarget(targetId)
    val history: Flow<List<AnalysisEntity>> = dao.getAllHistory()

    suspend fun saveAnalysis(entity: AnalysisEntity): Long {
        return dao.insertAnalysis(entity)
    }

    suspend fun deleteAnalysis(id: Long) {
        dao.deleteById(id)
    }

    suspend fun clearHistory() {
        dao.clearAll()
    }
}
