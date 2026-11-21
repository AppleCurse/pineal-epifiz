package com.aistudio.pineal.heretic.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(entities = [AnalysisEntity::class, HypothesisEntity::class], version = 2, exportSchema = false)
abstract class PinealDatabase : RoomDatabase() {
    abstract fun analysisDao(): AnalysisDao
    abstract fun reconDao(): ReconDao

    companion object {
        @Volatile
        private var INSTANCE: PinealDatabase? = null

        fun getInstance(context: Context): PinealDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    PinealDatabase::class.java,
                    "pineal_gland.db"
                ).fallbackToDestructiveMigration()
                .build()
                INSTANCE = instance
                instance
            }
        }
    }
}
