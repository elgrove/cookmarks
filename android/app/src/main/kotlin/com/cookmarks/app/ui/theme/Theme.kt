package com.cookmarks.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

@Immutable
data class CmColors(
    val bg: Color,
    val bgWarm: Color,
    val ink: Color,
    val muted: Color,
    val faint: Color,
    val line: Color,
    val lineStrong: Color,
    val accent: Color,
    val accentDeep: Color,
) {
    /** Compatibility aliases for existing UI call sites. */
    val clay: Color get() = accent
    val clayDeep: Color get() = accentDeep
}

val IvoryColors = CmColors(
    bg = Color(0xFFFAFAF5),
    bgWarm = Color(0xFFF1EEE4),
    ink = Color(0xFF1E2025),
    muted = Color(0xFF6F6D5C),
    faint = Color(0xFFA5A294),
    line = Color(0xFFE0DDD1),
    lineStrong = Color(0xFFC9C6B8),
    accent = Color(0xFF1F6F50),
    accentDeep = Color(0xFF155239),
)

val MidnightColors = CmColors(
    bg = Color(0xFF16181C),
    bgWarm = Color(0xFF1D2126),
    ink = Color(0xFFECEEE7),
    muted = Color(0xFF9A988B),
    faint = Color(0xFF63665A),
    line = Color(0xFF2A2E33),
    lineStrong = Color(0xFF3C4148),
    accent = Color(0xFF46A87D),
    accentDeep = Color(0xFF67C096),
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
            primary = cm.accent,
            onPrimary = cm.bg,
            secondary = cm.accentDeep,
            background = cm.bg,
            onBackground = cm.ink,
            surface = cm.bg,
            onSurface = cm.ink,
            surfaceVariant = cm.bgWarm,
            onSurfaceVariant = cm.muted,
            surfaceContainer = cm.bgWarm,
            outline = cm.line,
            outlineVariant = cm.lineStrong,
            error = Color(0xFFE0715A),
        )
    } else {
        lightColorScheme(
            primary = cm.accent,
            onPrimary = cm.bg,
            secondary = cm.accentDeep,
            background = cm.bg,
            onBackground = cm.ink,
            surface = cm.bg,
            onSurface = cm.ink,
            surfaceVariant = cm.bgWarm,
            onSurfaceVariant = cm.muted,
            surfaceContainer = cm.bgWarm,
            outline = cm.line,
            outlineVariant = cm.lineStrong,
            error = Color(0xFFB3402A),
        )
    }
    val shapes = Shapes(
        extraSmall = RoundedCornerShape(0.dp),
        small = RoundedCornerShape(0.dp),
        medium = RoundedCornerShape(0.dp),
        large = RoundedCornerShape(0.dp),
        extraLarge = RoundedCornerShape(0.dp),
    )
    CompositionLocalProvider(LocalCmColors provides cm) {
        MaterialTheme(colorScheme = scheme, typography = CookmarksTypography, shapes = shapes, content = content)
    }
}
