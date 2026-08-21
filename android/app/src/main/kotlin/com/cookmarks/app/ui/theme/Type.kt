package com.cookmarks.app.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.cookmarks.app.R

@OptIn(ExperimentalTextApi::class)
private fun variable(resId: Int, weight: FontWeight, style: FontStyle = FontStyle.Normal) =
    Font(
        resId = resId,
        weight = weight,
        style = style,
        variationSettings = FontVariation.Settings(FontVariation.weight(weight.weight)),
    )

val Grotesk = FontFamily(
    variable(R.font.schibsted_grotesk, FontWeight.Normal),
    variable(R.font.schibsted_grotesk, FontWeight.Medium),
    variable(R.font.schibsted_grotesk, FontWeight.SemiBold),
    variable(R.font.schibsted_grotesk, FontWeight.Bold),
    variable(R.font.schibsted_grotesk_italic, FontWeight.Normal, FontStyle.Italic),
    variable(R.font.schibsted_grotesk_italic, FontWeight.Medium, FontStyle.Italic),
)

val Serif = FontFamily(
    variable(R.font.source_serif4, FontWeight.Light),
    variable(R.font.source_serif4, FontWeight.Normal),
    variable(R.font.source_serif4, FontWeight.Medium),
    variable(R.font.source_serif4, FontWeight.SemiBold),
    variable(R.font.source_serif4_italic, FontWeight.Light, FontStyle.Italic),
    variable(R.font.source_serif4_italic, FontWeight.Normal, FontStyle.Italic),
    variable(R.font.source_serif4_italic, FontWeight.Medium, FontStyle.Italic),
)

val Mono = FontFamily(
    Font(R.font.ibm_plex_mono, FontWeight.Normal),
    Font(R.font.ibm_plex_mono_medium, FontWeight.Medium),
)

val CookmarksTypography = Typography(
    displayLarge = TextStyle(fontFamily = Serif, fontWeight = FontWeight.Light, fontStyle = FontStyle.Italic, fontSize = 44.sp, lineHeight = 48.sp),
    displayMedium = TextStyle(fontFamily = Serif, fontWeight = FontWeight.Light, fontStyle = FontStyle.Italic, fontSize = 34.sp, lineHeight = 40.sp),
    displaySmall = TextStyle(fontFamily = Serif, fontWeight = FontWeight.Light, fontStyle = FontStyle.Italic, fontSize = 28.sp, lineHeight = 34.sp),
    headlineLarge = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.SemiBold, fontSize = 26.sp, lineHeight = 32.sp),
    headlineMedium = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.SemiBold, fontSize = 22.sp, lineHeight = 28.sp),
    headlineSmall = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.SemiBold, fontSize = 18.sp, lineHeight = 24.sp),
    titleLarge = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.SemiBold, fontSize = 17.sp, lineHeight = 22.sp),
    titleMedium = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.Medium, fontSize = 15.sp, lineHeight = 20.sp),
    titleSmall = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.Medium, fontSize = 13.sp, lineHeight = 18.sp),
    bodyLarge = TextStyle(fontFamily = Serif, fontWeight = FontWeight.Normal, fontSize = 17.sp, lineHeight = 26.sp),
    bodyMedium = TextStyle(fontFamily = Serif, fontWeight = FontWeight.Normal, fontSize = 15.sp, lineHeight = 23.sp),
    bodySmall = TextStyle(fontFamily = Serif, fontWeight = FontWeight.Normal, fontSize = 13.sp, lineHeight = 19.sp),
    labelLarge = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.Medium, fontSize = 14.sp, lineHeight = 18.sp, letterSpacing = 0.02.em),
    labelMedium = TextStyle(fontFamily = Mono, fontWeight = FontWeight.Normal, fontSize = 11.sp, lineHeight = 16.sp, letterSpacing = 0.08.em),
    labelSmall = TextStyle(fontFamily = Mono, fontWeight = FontWeight.Normal, fontSize = 10.sp, lineHeight = 14.sp, letterSpacing = 0.14.em),
)
