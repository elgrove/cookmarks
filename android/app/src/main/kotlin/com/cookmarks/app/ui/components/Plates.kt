package com.cookmarks.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.cookmarks.app.ui.theme.CmTheme
import com.cookmarks.app.ui.theme.Serif

@Composable
fun MonoLabel(text: String, modifier: Modifier = Modifier, colour: androidx.compose.ui.graphics.Color = CmTheme.colors.muted) {
    Text(
        text = text.uppercase(),
        style = MaterialTheme.typography.labelSmall,
        color = colour,
        modifier = modifier,
    )
}

@Composable
fun NoImagePlate(name: String, openingLine: String?, modifier: Modifier = Modifier) {
    val colors = CmTheme.colors
    Row(
        modifier = modifier
            .background(colors.bgWarm)
            .border(1.dp, colors.line)
            .padding(20.dp)
            .clearAndSetSemantics {},
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = name.firstOrNull()?.uppercase() ?: "·",
            fontFamily = Serif,
            fontWeight = FontWeight.Light,
            fontStyle = FontStyle.Italic,
            fontSize = 64.sp,
            color = colors.clay,
        )
        if (!openingLine.isNullOrBlank()) {
            Text(
                text = openingLine,
                style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                color = colors.muted,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(start = 16.dp),
            )
        }
    }
}

@Composable
fun CoverPlate(title: String, modifier: Modifier = Modifier) {
    val colors = CmTheme.colors
    Box(
        modifier = modifier
            .background(colors.bgWarm)
            .border(1.dp, colors.line)
            .padding(12.dp)
            .clearAndSetSemantics {},
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = title,
            fontFamily = Serif,
            fontStyle = FontStyle.Italic,
            fontSize = 16.sp,
            lineHeight = 22.sp,
            color = colors.ink,
            maxLines = 5,
            overflow = TextOverflow.Ellipsis,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
        )
    }
}

@Composable
fun CentredState(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Box(modifier = modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        content()
    }
}

@Composable
fun ErrorState(message: String, modifier: Modifier = Modifier) {
    CentredState(modifier) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            MonoLabel("Something went wrong")
            Text(
                text = message,
                style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                color = CmTheme.colors.muted,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 40.dp),
            )
        }
    }
}
