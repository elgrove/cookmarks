package com.cookmarks.app.ui.admin

import android.text.format.DateUtils
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.TaskRun
import com.cookmarks.app.ui.components.Loaded
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme
import com.cookmarks.app.ui.theme.ThemeMode
import com.cookmarks.app.ui.theme.ThemePref
import java.time.Instant
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive

private fun words(value: String) = value.replace('_', ' ')

private fun whenLabel(iso: String): String = runCatching {
    DateUtils.getRelativeTimeSpanString(Instant.parse(iso).toEpochMilli()).toString()
}.getOrDefault(iso)

private fun detailLine(run: TaskRun): String = run.detail.entries
    .filter { (_, v) -> v !is JsonNull && v is JsonPrimitive }
    .joinToString("  ·  ") { (k, v) -> "${words(k)} ${(v as JsonPrimitive).content}" }

@Composable
fun AdminScreen(onBack: () -> Unit) {
    val colors = CmTheme.colors
    var tick by remember { mutableIntStateOf(0) }
    val state by rememberLoad(tick) { Api.service.taskRuns() }
    val mode by ThemePref.mode.collectAsState()

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 32.dp),
    ) {
        item {
            IconButton(onClick = onBack) {
                Icon(
                    Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "Back",
                    tint = colors.muted,
                )
            }
        }
        item {
            Column(modifier = Modifier.padding(horizontal = 20.dp)) {
                Text(
                    text = "Admin",
                    style = MaterialTheme.typography.displaySmall,
                    color = colors.ink,
                    modifier = Modifier.padding(bottom = 20.dp),
                )
                MonoLabel("Theme", colour = colors.muted)
                Row(
                    horizontalArrangement = Arrangement.spacedBy(24.dp),
                    modifier = Modifier.padding(top = 8.dp, bottom = 24.dp),
                ) {
                    ThemeMode.entries.forEach { option ->
                        MonoLabel(
                            option.label,
                            colour = if (option == mode) colors.clay else colors.faint,
                            modifier = Modifier
                                .clickable { ThemePref.set(option) }
                                .padding(vertical = 8.dp),
                        )
                    }
                }
                MonoLabel("Task runs", colour = colors.muted)
            }
        }
        item {
            Loaded(state, onRetry = { tick++ }) { runs ->
                Column {
                    if (runs.isEmpty()) {
                        Text(
                            text = "No task runs yet.",
                            style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                            color = colors.muted,
                            modifier = Modifier.padding(horizontal = 20.dp, vertical = 20.dp),
                        )
                    }
                    runs.forEachIndexed { i, run ->
                        TaskRunRow(run)
                        if (i < runs.lastIndex) {
                            HorizontalDivider(color = colors.line, modifier = Modifier.padding(horizontal = 20.dp))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TaskRunRow(run: TaskRun) {
    val colors = CmTheme.colors
    Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 14.dp)) {
        Row(modifier = Modifier.fillMaxWidth()) {
            MonoLabel(
                words(run.status),
                colour = if (run.status == "failed") colors.clayDeep else colors.clay,
                modifier = Modifier.weight(1f),
            )
            MonoLabel(whenLabel(run.created_at), colour = colors.faint)
        }
        Text(
            text = run.book_title ?: words(run.task_type),
            style = MaterialTheme.typography.bodyLarge,
            color = colors.ink,
            modifier = Modifier.padding(top = 2.dp),
        )
        val meta = listOfNotNull(
            words(run.task_type).takeIf { run.book_title != null },
            run.model_name,
            run.cost_usd?.let { "\$$it" },
            detailLine(run).takeIf { it.isNotEmpty() },
        ).joinToString("  ·  ")
        if (meta.isNotEmpty()) {
            MonoLabel(meta, colour = colors.faint, modifier = Modifier.padding(top = 4.dp))
        }
        run.errors.forEach { error ->
            Text(
                text = error,
                style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                color = colors.clayDeep,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}
