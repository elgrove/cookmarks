package com.cookmarks.app.ui.theme

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp

@Preview(showBackground = true)
@Composable
private fun ThemePreview() {
    CookmarksTheme {
        val colors = CmTheme.colors
        Column(modifier = Modifier.background(colors.bg).padding(20.dp)) {
            Row {
                listOf(colors.bg, colors.bgWarm, colors.ink, colors.muted, colors.faint, colors.clay, colors.clayDeep).forEach {
                    Box(modifier = Modifier.width(32.dp).height(32.dp).background(it))
                }
            }
            Text("Display serif italic", style = MaterialTheme.typography.displaySmall, modifier = Modifier.padding(top = 16.dp))
            Text("Headline grotesk", style = MaterialTheme.typography.headlineMedium)
            Text("Body reading copy in Source Serif 4.", style = MaterialTheme.typography.bodyLarge)
            Text("MONO LABEL · METADATA", style = MaterialTheme.typography.labelSmall)
        }
    }
}
