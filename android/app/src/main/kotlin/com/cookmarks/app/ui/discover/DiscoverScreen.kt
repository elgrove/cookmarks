package com.cookmarks.app.ui.discover

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import com.cookmarks.app.api.Api
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme

private const val RESTING_CHIPS = 30
private const val SEARCH_CHIPS = 60

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DiscoverScreen(onPlay: (GameSource) -> Unit) {
    val colors = CmTheme.colors
    var selected by remember { mutableStateOf(listOf<String>()) }
    var filter by remember { mutableStateOf("") }
    val keywords by rememberLoad(Unit) { Api.service.keywords(limit = 500) }

    val all = keywords?.getOrNull().orEmpty().map { it.name }.distinctBy(String::lowercase)
    val query = filter.trim()
    val matches = all.filter { it !in selected && it.contains(query, ignoreCase = true) }
    val cap = if (query.isEmpty()) RESTING_CHIPS else SEARCH_CHIPS
    val shown = selected + matches.take(cap)

    Column(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 16.dp),
        ) {
            Text(
                text = "Discover",
                style = MaterialTheme.typography.displaySmall,
                color = colors.ink,
                modifier = Modifier.padding(bottom = 4.dp),
            )
            Text(
                text = "A deck of recipes you haven't kept. Swipe right to favourite, left to dismiss.",
                style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                color = colors.muted,
                modifier = Modifier.padding(bottom = 16.dp),
            )
            MonoLabel("Narrow the deck by keyword", colour = colors.faint, modifier = Modifier.padding(bottom = 8.dp))
            OutlinedTextField(
                value = filter,
                onValueChange = { filter = it },
                placeholder = { Text("Find a keyword") },
                singleLine = true,
                leadingIcon = { Icon(Icons.Filled.Search, contentDescription = null, tint = colors.muted) },
                trailingIcon = {
                    if (filter.isNotEmpty()) {
                        IconButton(onClick = { filter = "" }) {
                            Icon(Icons.Filled.Close, contentDescription = "Clear keyword search", tint = colors.faint)
                        }
                    }
                },
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = colors.clay,
                    unfocusedBorderColor = colors.lineStrong,
                    cursorColor = colors.clay,
                ),
                modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
            )
            if (keywords == null) {
                Box(modifier = Modifier.fillMaxWidth().padding(vertical = 24.dp)) {
                    CircularProgressIndicator(color = colors.clay, modifier = Modifier.size(24.dp))
                }
            }
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                shown.forEach { keyword ->
                    val active = keyword in selected
                    MonoLabel(
                        keyword,
                        colour = if (active) colors.bg else colors.muted,
                        modifier = Modifier
                            .border(1.dp, if (active) colors.clay else colors.lineStrong)
                            .then(if (active) Modifier.background(colors.clay) else Modifier)
                            .clickable {
                                selected = if (active) selected - keyword else selected + keyword
                            }
                            .padding(horizontal = 10.dp, vertical = 6.dp),
                    )
                }
            }
            if (matches.size > cap) {
                Text(
                    text = "${matches.size - cap} more — search to narrow.",
                    style = MaterialTheme.typography.bodySmall.copy(fontStyle = FontStyle.Italic),
                    color = colors.faint,
                    modifier = Modifier.padding(top = 12.dp),
                )
            }
            if (all.isNotEmpty() && matches.isEmpty() && query.isNotEmpty()) {
                Text(
                    text = "No keyword matches “$query”.",
                    style = MaterialTheme.typography.bodySmall.copy(fontStyle = FontStyle.Italic),
                    color = colors.faint,
                    modifier = Modifier.padding(top = 12.dp),
                )
            }
        }
        HorizontalDivider(color = colors.line)
        Button(
            onClick = {
                onPlay(if (selected.isEmpty()) GameSource.All else GameSource.Search("", selected))
            },
            shape = MaterialTheme.shapes.extraSmall,
            colors = ButtonDefaults.buttonColors(containerColor = colors.clay),
            modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 12.dp),
        ) {
            val label = when {
                selected.isEmpty() -> "Play all recipes"
                selected.size == 1 -> "Play ${selected.single()}"
                else -> "Play ${selected.size} keywords"
            }
            Text(text = label, style = MaterialTheme.typography.labelLarge)
        }
    }
}
