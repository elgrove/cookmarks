package com.cookmarks.app.ui.discover

import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.cookmarks.app.api.Api
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme

private const val INSPIRATION_POOL_SIZE = 100
private const val INSPIRATION_KEYWORD_COUNT = 6

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DiscoverScreen(onPlay: (GameSource) -> Unit) {
    val colors = CmTheme.colors
    var query by remember { mutableStateOf("") }
    val keywords by rememberLoad(Unit) { Api.service.keywords(limit = 500) }

    val trimmedQuery = query.trim()
    val inspiration = remember(keywords) {
        keywords?.getOrNull()
            .orEmpty()
            .sortedByDescending { it.recipe_count }
            .take(INSPIRATION_POOL_SIZE)
            .shuffled()
            .take(INSPIRATION_KEYWORD_COUNT)
    }
    val play = {
        onPlay(
            if (trimmedQuery.isEmpty()) GameSource.All else GameSource.Search(trimmedQuery, emptyList()),
        )
    }

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
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                label = { Text("Search recipes") },
                placeholder = { Text("Search recipes") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { play() }),
                leadingIcon = { Icon(Icons.Filled.Search, contentDescription = null, tint = colors.muted) },
                trailingIcon = {
                    if (query.isNotEmpty()) {
                        IconButton(onClick = { query = "" }) {
                            Icon(Icons.Filled.Close, contentDescription = "Clear recipe search", tint = colors.faint)
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
            if (inspiration.isNotEmpty()) {
                MonoLabel("Start with an idea", colour = colors.faint, modifier = Modifier.padding(bottom = 8.dp))
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    inspiration.forEach { keyword ->
                        MonoLabel(
                            keyword.name,
                            colour = colors.muted,
                            modifier = Modifier
                                .border(1.dp, colors.lineStrong)
                                .defaultMinSize(minHeight = 48.dp)
                                .clickable {
                                    query = keyword.name
                                }
                                .padding(horizontal = 10.dp, vertical = 6.dp),
                        )
                    }
                }
            }
        }
        HorizontalDivider(color = colors.line)
        Button(
            onClick = play,
            shape = MaterialTheme.shapes.extraSmall,
            colors = ButtonDefaults.buttonColors(containerColor = colors.clay),
            modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 12.dp),
        ) {
            val label = if (trimmedQuery.isEmpty()) "Play all recipes" else "Play “$trimmedQuery”"
            Text(text = label, style = MaterialTheme.typography.labelLarge)
        }
    }
}
