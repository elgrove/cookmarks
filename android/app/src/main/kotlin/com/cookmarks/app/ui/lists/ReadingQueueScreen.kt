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
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.cookmarks.app.api.Api
import com.cookmarks.app.ui.Feedback
import com.cookmarks.app.ui.cleanTitle
import com.cookmarks.app.ui.components.Loaded
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.launch

@Composable
fun ReadingQueueScreen(onBack: () -> Unit, onOpenBook: (String) -> Unit) {
    val colors = CmTheme.colors
    val scope = rememberCoroutineScope()
    var tick by remember { mutableIntStateOf(0) }
    val state by rememberLoad(tick) { Api.service.readingQueue().reversed() }

    Loaded(state, onRetry = { tick++ }) { books ->
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
                        text = "Reading queue",
                        style = MaterialTheme.typography.displaySmall,
                        color = colors.ink,
                    )
                    MonoLabel(
                        "${books.size} ${if (books.size == 1) "book" else "books"} · next up first",
                        colour = colors.faint,
                        modifier = Modifier.padding(top = 4.dp, bottom = 12.dp),
                    )
                    if (books.isEmpty()) {
                        Text(
                            text = "Nothing queued yet.",
                            style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                            color = colors.muted,
                            modifier = Modifier.padding(vertical = 20.dp),
                        )
                    }
                }
            }
            itemsIndexed(books, key = { _, b -> b.id }) { i, book ->
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable(
                            role = Role.Button,
                            onClickLabel = "Open ${cleanTitle(book.title)}",
                        ) { onOpenBook(book.id) }
                        .padding(start = 20.dp, end = 8.dp, top = 4.dp, bottom = 4.dp),
                ) {
                    MonoLabel((i + 1).toString().padStart(2, '0'), colour = colors.clay)
                    Column(modifier = Modifier.weight(1f).padding(start = 12.dp)) {
                        Text(
                            text = cleanTitle(book.title),
                            style = MaterialTheme.typography.bodyLarge,
                            color = colors.ink,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                        MonoLabel(
                            listOf(
                                book.author,
                                if (book.recipe_count > 0) "${book.recipe_count} recipes" else "pending extraction",
                            ).joinToString("  ·  "),
                            colour = colors.faint,
                            modifier = Modifier.padding(top = 2.dp),
                        )
                    }
                    IconButton(onClick = {
                        scope.launch {
                            try {
                                Api.service.unqueueBook(book.id)
                                tick++
                            } catch (e: CancellationException) {
                                throw e
                            } catch (e: Exception) {
                                Log.w("ReadingQueue", "unqueue failed", e)
                                Feedback.show("Couldn't remove from queue")
                            }
                        }
                    }) {
                        Icon(
                            Icons.Filled.Close,
                            contentDescription = "Remove ${cleanTitle(book.title)} from queue",
                            tint = colors.faint,
                        )
                    }
                }
                if (i < books.lastIndex) {
                    HorizontalDivider(color = colors.line, modifier = Modifier.padding(horizontal = 20.dp))
                }
            }
        }
    }
}
