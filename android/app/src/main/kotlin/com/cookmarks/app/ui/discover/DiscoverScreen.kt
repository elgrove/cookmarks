package com.cookmarks.app.ui.discover

import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.cookmarks.app.api.Api
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DiscoverScreen(onPlay: (GameSource) -> Unit) {
    val colors = CmTheme.colors
    var query by remember { mutableStateOf("") }
    val keywords by rememberLoad(Unit) { Api.service.keywords() }

    fun playSearch() {
        if (query.isNotBlank()) onPlay(GameSource.Search(query.trim(), null))
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
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
            text = "A deck of recipes you haven't kept. Swipe right to favourite, left to dismiss for good.",
            style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
            color = colors.muted,
            modifier = Modifier.padding(bottom = 16.dp),
        )
        Button(
            onClick = { onPlay(GameSource.All) },
            shape = MaterialTheme.shapes.extraSmall,
            colors = ButtonDefaults.buttonColors(containerColor = colors.clay),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(text = "Play everything", style = MaterialTheme.typography.labelLarge)
        }
        MonoLabel("Or deal a narrower deck", colour = colors.faint, modifier = Modifier.padding(top = 20.dp, bottom = 8.dp))
        OutlinedTextField(
            value = query,
            onValueChange = { query = it },
            placeholder = { Text("Search, or describe a dish") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { playSearch() }),
            trailingIcon = {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = { playSearch() }) {
                        Icon(Icons.Filled.Search, contentDescription = "Play this search", tint = colors.muted)
                    }
                    IconButton(
                        onClick = { if (query.isNotBlank()) onPlay(GameSource.Semantic(query.trim())) },
                        modifier = Modifier.semantics { contentDescription = "Play AI search" },
                    ) {
                        Text(text = "✦", fontSize = 20.sp, color = colors.muted)
                    }
                }
            },
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = colors.clay,
                unfocusedBorderColor = colors.lineStrong,
                cursorColor = colors.clay,
            ),
            modifier = Modifier.fillMaxWidth(),
        )
        val resting = keywords?.getOrNull().orEmpty()
        if (resting.isNotEmpty()) {
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.padding(top = 16.dp),
            ) {
                resting.forEach { keyword ->
                    Text(
                        text = keyword.name,
                        style = MaterialTheme.typography.labelSmall,
                        color = colors.muted,
                        modifier = Modifier
                            .border(1.dp, colors.lineStrong)
                            .clickable { onPlay(GameSource.Search("", keyword.name)) }
                            .padding(horizontal = 10.dp, vertical = 6.dp),
                    )
                }
            }
        }
    }
}
