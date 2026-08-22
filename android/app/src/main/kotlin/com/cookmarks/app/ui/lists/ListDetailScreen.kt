package com.cookmarks.app.ui.lists

import android.util.Log
import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.cookmarks.app.api.Api
import com.cookmarks.app.ui.components.Loaded
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.launch

@Composable
fun ListDetailScreen(
    listId: String,
    onBack: () -> Unit,
    onOpenRecipe: (String) -> Unit,
    onReadThrough: () -> Unit,
) {
    val colors = CmTheme.colors
    val scope = rememberCoroutineScope()
    var tick by remember { mutableIntStateOf(0) }
    val state by rememberLoad(listId, tick) { Api.service.list(listId) }
    var filter by rememberSaveable { mutableStateOf("") }

    Loaded(state, onRetry = { tick++ }) { detail ->
        val shown = remember(detail, filter) {
            val q = filter.trim().lowercase()
            if (q.isEmpty()) detail.recipes else detail.recipes.filter { it.name.lowercase().contains(q) }
        }
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(bottom = 32.dp),
        ) {
            item {
                IconButton(onClick = onBack) {
                    Icon(
                        Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = "Back to lists",
                        tint = colors.muted,
                    )
                }
            }
            item {
                Column(modifier = Modifier.padding(horizontal = 20.dp)) {
                    Text(
                        text = detail.name,
                        style = MaterialTheme.typography.displaySmall,
                        color = colors.ink,
                    )
                    MonoLabel(
                        "${detail.recipe_count} recipes",
                        colour = colors.faint,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                    if (detail.recipes.isNotEmpty()) {
                        Button(
                            onClick = onReadThrough,
                            shape = MaterialTheme.shapes.extraSmall,
                            colors = ButtonDefaults.buttonColors(containerColor = colors.clay),
                            modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
                        ) {
                            Text(text = "Read through", style = MaterialTheme.typography.labelLarge)
                        }
                        OutlinedTextField(
                            value = filter,
                            onValueChange = { filter = it },
                            placeholder = { Text("Filter recipes") },
                            singleLine = true,
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = colors.clay,
                                unfocusedBorderColor = colors.lineStrong,
                                cursorColor = colors.clay,
                            ),
                            modifier = Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 8.dp),
                        )
                    } else {
                        Text(
                            text = "Nothing on this list yet.",
                            style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                            color = colors.muted,
                            modifier = Modifier.padding(vertical = 20.dp),
                        )
                    }
                }
            }
            itemsIndexed(shown, key = { _, r -> r.id }) { i, recipe ->
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onOpenRecipe(recipe.id) }
                        .padding(start = 20.dp, end = 8.dp, top = 4.dp, bottom = 4.dp),
                ) {
                    MonoLabel((i + 1).toString().padStart(3, '0'), colour = colors.clay)
                    Column(modifier = Modifier.weight(1f).padding(start = 14.dp)) {
                        Text(
                            text = recipe.name,
                            style = MaterialTheme.typography.bodyLarge,
                            color = colors.ink,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                        MonoLabel(
                            recipe.book_title,
                            colour = colors.faint,
                            modifier = Modifier.padding(top = 2.dp),
                        )
                    }
                    IconButton(onClick = {
                        scope.launch {
                            try {
                                Api.service.removeFromList(detail.id, recipe.id)
                                tick++
                            } catch (e: CancellationException) {
                                throw e
                            } catch (e: Exception) {
                                Log.w("ListDetail", "remove from list failed", e)
                            }
                        }
                    }) {
                        Icon(
                            Icons.Filled.Close,
                            contentDescription = "Remove ${recipe.name} from list",
                            tint = colors.faint,
                        )
                    }
                }
                if (i < shown.lastIndex) {
                    HorizontalDivider(color = colors.line, modifier = Modifier.padding(horizontal = 20.dp))
                }
            }
        }
    }
}
