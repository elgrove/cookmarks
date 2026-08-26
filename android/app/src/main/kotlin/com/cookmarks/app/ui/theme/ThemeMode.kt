package com.cookmarks.app.ui.theme

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow

enum class ThemeMode(val label: String) {
    System("System"),
    Light("Light"),
    Dark("Dark"),
}

object ThemePref {
    private lateinit var prefs: SharedPreferences

    val mode = MutableStateFlow(ThemeMode.System)

    fun init(context: Context) {
        prefs = context.getSharedPreferences("settings", Context.MODE_PRIVATE)
        mode.value = runCatching { ThemeMode.valueOf(prefs.getString("theme", null) ?: "") }
            .getOrDefault(ThemeMode.System)
    }

    fun set(value: ThemeMode) {
        mode.value = value
        prefs.edit().putString("theme", value.name).apply()
    }
}
