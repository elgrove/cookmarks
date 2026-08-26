package com.cookmarks.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

@Immutable
data class CmColors(
    val bg: Color,
    val bgWarm: Color,
    val ink: Color,
    val muted: Color,
    val faint: Color,
    val line: Color,
    val lineStrong: Color,
    val clay: Color,
    val clayDeep: Color,
)

val IvoryColors = CmColors(
    bg = Color(0xFFFAF9F5),
    bgWarm = Color(0xFFF3EFE5),
    ink = Color(0xFF141413),
    muted = Color(0xFF86847B),
    faint = Color(0xFFB0AEA5),
    line = Color(0xFFE8E6DC),
    lineStrong = Color(0xFFD8D4C6),
    clay = Color(0xFFD97757),
    clayDeep = Color(0xFFC2613F),
)

val MidnightColors = CmColors(
    bg = Color(0xFF14181E),
    bgWarm = Color(0xFF1C222B),
    ink = Color(0xFFEEF1F6),
    muted = Color(0xFF939BA7),
    faint = Color(0xFF565F6B),
    line = Color(0xFF28303A),
    lineStrong = Color(0xFF354050),
    clay = Color(0xFFDF8460),
    clayDeep = Color(0xFFEF9E7D),
)

val LocalCmColors = staticCompositionLocalOf { IvoryColors }

object CmTheme {
    val colors: CmColors
        @Composable get() = LocalCmColors.current
}

@Composable
fun CookmarksTheme(content: @Composable () -> Unit) {
    val mode by ThemePref.mode.collectAsState()
    val darkTheme = when (mode) {
        ThemeMode.System -> isSystemInDarkTheme()
        ThemeMode.Light -> false
        ThemeMode.Dark -> true
    }
    val cm = if (darkTheme) MidnightColors else IvoryColors
    val scheme = if (darkTheme) {
        darkColorScheme(
            primary = cm.clay,
            onPrimary = cm.bg,
            secondary = cm.clayDeep,
            background = cm.bg,
            onBackground = cm.ink,
            surface = cm.bg,
            onSurface = cm.ink,
            surfaceVariant = cm.bgWarm,
            onSurfaceVariant = cm.muted,
            surfaceContainer = cm.bgWarm,
            outline = cm.line,
            outlineVariant = cm.lineStrong,
            error = Color(0xFFEF9E7D),
        )
    } else {
        lightColorScheme(
            primary = cm.clay,
            onPrimary = Color.White,
            secondary = cm.clayDeep,
            background = cm.bg,
            onBackground = cm.ink,
            surface = cm.bg,
            onSurface = cm.ink,
            surfaceVariant = cm.bgWarm,
            onSurfaceVariant = cm.muted,
            surfaceContainer = cm.bgWarm,
            outline = cm.line,
            outlineVariant = cm.lineStrong,
            error = Color(0xFFC2613F),
        )
    }
    CompositionLocalProvider(LocalCmColors provides cm) {
        MaterialTheme(colorScheme = scheme, typography = CookmarksTypography, content = content)
    }
}
