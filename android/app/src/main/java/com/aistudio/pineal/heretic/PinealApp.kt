package com.aistudio.pineal.heretic

import android.app.Application
import com.aistudio.pineal.heretic.data.local.PinealDatabase
import com.aistudio.pineal.heretic.data.local.PinealRepository

class PinealApp : Application() {
    lateinit var repository: PinealRepository
        private set

    override fun onCreate() {
        super.onCreate()
        val db = PinealDatabase.getInstance(this)
        repository = PinealRepository(db.analysisDao(), db.reconDao())
    }
}
