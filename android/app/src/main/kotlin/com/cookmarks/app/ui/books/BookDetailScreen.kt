package com.cookmarks.app.ui.books

import android.text.Html
import android.util.Log
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.BookDetail
import com.cookmarks.app.api.RecipeIndexEntry
import com.cookmarks.app.ui.Feedback
import com.cookmarks.app.ui.cleanTitle
import com.cookmarks.app.ui.components.CoverPlate
import com.cookmarks.app.ui.components.Loaded
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme
import com.cookmarks.app.ui.titleSubtitle
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.launch

@Composable
fun BookDetailScreen(
    bookId: String,
    onBack: () -> Unit,
    onReadFrom: (String?) -> Unit,
    onDiscover: (String) -> Unit,
) {
    var tick by remember { mutableIntStateOf(0) }
    val state by rememberLoad(bookId, tick) {
        val detail = Api.service.book(bookId)
        val index = Api.service.recipeIndex(bookId)
        detail to index
    }
    Loaded(state, onRetry = { tick++ }) { (detail, index) ->
        BookDetailContent(detail, index, onBack, onReadFrom, onDiscover)
    }
}

@Composable
private fun BookDetailContent(
    detail: BookDetail,
    index: List<RecipeIndexEntry>,
    onBack: () -> Unit,
    onReadFrom: (String?) -> Unit,
    onDiscover: (String) -> Unit,
) {
    val colors = CmTheme.colors
    val scope = rememberCoroutineScope()
    val description = remember(detail.description) {
        Html.fromHtml(detail.description, Html.FROM_HTML_MODE_COMPACT).toString().trim()
    }
    val positions = remember(index) {
        index.withIndex().associate { (i, entry) -> entry.id to i + 1 }
    }

    var isQueued by remember(detail.id, detail.queued) { mutableStateOf(detail.queued) }
    var queueBusy by remember(detail.id) { mutableStateOf(false) }

    var readingState by remember(detail.id, detail.reading) { mutableStateOf(detail.reading) }
    var readBusy by remember(detail.id) { mutableStateOf(false) }
    val isFinished = readingState?.finished == true

    var extractBusy by remember(detail.id) { mutableStateOf(false) }
    var extractQueued by remember(detail.id) { mutableStateOf(false) }
    var menuExpanded by remember { mutableStateOf(false) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 32.dp),
    ) {
        item {
            IconButton(onClick = onBack) {
                Icon(
                    Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "Back to books",
                    tint = colors.muted,
                )
            }
        }
        item {
            Row(modifier = Modifier.padding(horizontal = 20.dp)) {
                Box(modifier = Modifier.width(110.dp).aspectRatio(0.72f)) {
                    if (detail.has_cover) {
                        AsyncImage(
                            model = Api.bookCoverUrl(detail.id),
                            contentDescription = "Cover of ${detail.title}",
                            contentScale = ContentScale.Crop,
                            modifier = Modifier.fillMaxSize(),
                        )
                    } else {
                        CoverPlate(cleanTitle(detail.title), modifier = Modifier.fillMaxSize())
                    }
                }
                Column(modifier = Modifier.padding(start = 16.dp)) {
                    MonoLabel(detail.author)
                    Text(
                        text = cleanTitle(detail.title),
                        style = MaterialTheme.typography.displaySmall,
                        color = colors.ink,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                    val subtitle = titleSubtitle(detail.title)
                    if (subtitle.isNotEmpty()) {
                        Text(
                            text = subtitle,
                            style = MaterialTheme.typography.bodyMedium,
                            color = colors.muted,
                            modifier = Modifier.padding(top = 4.dp),
                        )
                    }
                    MonoLabel(
                        listOfNotNull(
                            "${detail.recipe_count} recipes",
                            detail.pubdate?.take(4),
                        ).joinToString("  ·  "),
                        colour = colors.faint,
                        modifier = Modifier.padding(top = 8.dp),
                    )
                    readingState?.let { reading ->
                        MonoLabel(
                            if (reading.finished) "Finished" else "${(reading.fraction * 100).toInt()}% read",
                            colour = colors.clayDeep,
                            modifier = Modifier.padding(top = 4.dp),
                        )
                    }
                }
            }
        }
        if (description.isNotBlank()) {
            item {
                Text(
                    text = description,
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.ink,
                    maxLines = 6,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 16.dp),
                )
            }
        }
        detail.resume_recipe?.let { resume ->
            item {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 20.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Button(
                        onClick = {
                            val startId = if (readingState == null || isFinished) null else resume.id
                            onReadFrom(startId)
                        },
                        shape = RoundedCornerShape(topStart = 4.dp, bottomStart = 4.dp, topEnd = 0.dp, bottomEnd = 0.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = colors.clay),
                        modifier = Modifier.weight(1f),
                    ) {
                        Text(
                            text = if (readingState == null || isFinished) "Start reading" else "Continue — ${resume.name}",
                            style = MaterialTheme.typography.labelLarge,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    Box {
                        Button(
                            onClick = { menuExpanded = true },
                            shape = RoundedCornerShape(topStart = 0.dp, bottomStart = 0.dp, topEnd = 4.dp, bottomEnd = 4.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = colors.clayDeep,
                                contentColor = MaterialTheme.colorScheme.onPrimary,
                            ),
                            contentPadding = PaddingValues(horizontal = 8.dp),
                            modifier = Modifier.padding(start = 1.dp),
                        ) {
                            Icon(
                                Icons.Filled.ArrowDropDown,
                                contentDescription = "More reading options",
                            )
                        }
                        DropdownMenu(
                            expanded = menuExpanded,
                            onDismissRequest = { menuExpanded = false },
                            modifier = Modifier.background(colors.bgWarm),
                        ) {
                            DropdownMenuItem(
                                text = {
                                    Text(
                                        text = "Play in Discover",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = colors.ink,
                                    )
                                },
                                onClick = {
                                    menuExpanded = false
                                    onDiscover(cleanTitle(detail.title))
                                },
                            )
                        }
                    }
                }
            }
        }
        item {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp, vertical = 6.dp),
            ) {
                OutlinedButton(
                    onClick = {
                        if (queueBusy) return@OutlinedButton
                        scope.launch {
                            queueBusy = true
                            val next = !isQueued
                            isQueued = next
                            try {
                                val res = if (next) {
                                    Api.service.queueBook(detail.id)
                                } else {
                                    Api.service.unqueueBook(detail.id)
                                }
                                isQueued = res.queued
                            } catch (e: CancellationException) {
                                throw e
                            } catch (e: Exception) {
                                Log.w("BookDetail", "queue toggle failed", e)
                                isQueued = !next
                                Feedback.show("Couldn't update reading queue")
                            } finally {
                                queueBusy = false
                            }
                        }
                    },
                    shape = MaterialTheme.shapes.extraSmall,
                    border = BorderStroke(1.dp, if (isQueued) colors.clay else colors.lineStrong),
                    colors = ButtonDefaults.outlinedButtonColors(
                        containerColor = if (isQueued) colors.bgWarm else Color.Transparent,
                        contentColor = if (isQueued) colors.clayDeep else colors.ink,
                    ),
                    contentPadding = PaddingValues(horizontal = 4.dp, vertical = 6.dp),
                    modifier = Modifier
                        .weight(1f)
                        .semantics {
                            selected = isQueued
                            stateDescription = if (isQueued) "in queue" else "not in queue"
                        },
                ) {
                    Text(
                        text = if (isQueued) "In queue" else "Queue to read",
                        style = MaterialTheme.typography.labelLarge.copy(fontSize = 12.sp),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        textAlign = TextAlign.Center,
                    )
                }

                OutlinedButton(
                    onClick = {
                        if (readBusy) return@OutlinedButton
                        scope.launch {
                            readBusy = true
                            try {
                                val res = if (isFinished) {
                                    Api.service.resetBookProgress(detail.id)
                                } else {
                                    Api.service.markBookRead(detail.id)
                                }
                                readingState = res.reading
                            } catch (e: CancellationException) {
                                throw e
                            } catch (e: Exception) {
                                Log.w("BookDetail", "read status toggle failed", e)
                                Feedback.show("Couldn't update reading status")
                            } finally {
                                readBusy = false
                            }
                        }
                    },
                    shape = MaterialTheme.shapes.extraSmall,
                    border = BorderStroke(1.dp, colors.lineStrong),
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = colors.ink,
                    ),
                    contentPadding = PaddingValues(horizontal = 4.dp, vertical = 6.dp),
                    modifier = Modifier
                        .weight(1f)
                        .semantics {
                            selected = isFinished
                            stateDescription = if (isFinished) "finished" else "not finished"
                        },
                ) {
                    Text(
                        text = if (isFinished) "Mark unread" else "Mark read",
                        style = MaterialTheme.typography.labelLarge.copy(fontSize = 12.sp),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        textAlign = TextAlign.Center,
                    )
                }

                OutlinedButton(
                    onClick = {
                        if (extractBusy) return@OutlinedButton
                        scope.launch {
                            extractBusy = true
                            try {
                                Api.service.triggerExtraction(detail.id)
                                extractQueued = true
                            } catch (e: CancellationException) {
                                throw e
                            } catch (e: Exception) {
                                Log.w("BookDetail", "extraction trigger failed", e)
                                Feedback.show("Couldn't trigger extraction")
                            } finally {
                                extractBusy = false
                            }
                        }
                    },
                    enabled = !extractBusy && !extractQueued,
                    shape = MaterialTheme.shapes.extraSmall,
                    border = BorderStroke(1.dp, colors.lineStrong),
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = colors.ink,
                    ),
                    contentPadding = PaddingValues(horizontal = 4.dp, vertical = 6.dp),
                    modifier = Modifier.weight(1f),
                ) {
                    Text(
                        text = when {
                            extractBusy -> "Extracting…"
                            extractQueued -> "Queued"
                            detail.recipe_count > 0 -> "Re-extract"
                            else -> "Extract"
                        },
                        style = MaterialTheme.typography.labelLarge.copy(fontSize = 12.sp),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        textAlign = TextAlign.Center,
                    )
                }
            }
        }
        if (index.isNotEmpty()) {
            item {
                Column(modifier = Modifier.padding(horizontal = 20.dp)) {
                    HorizontalDivider(color = colors.lineStrong, modifier = Modifier.padding(top = 16.dp, bottom = 16.dp))
                    MonoLabel("Recipe index — ${index.size}")
                }
            }
            itemsIndexed(index, key = { _, entry -> entry.id }) { i, entry ->
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable(
                            role = Role.Button,
                            onClickLabel = "Read ${entry.name}",
                        ) { onReadFrom(entry.id) }
                        .padding(horizontal = 20.dp, vertical = 12.dp),
                ) {
                    MonoLabel(
                        (positions.getValue(entry.id)).toString().padStart(3, '0'),
                        colour = colors.clay,
                    )
                    Text(
                        text = entry.name,
                        style = MaterialTheme.typography.bodyLarge,
                        color = colors.ink,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier
                            .weight(1f)
                            .padding(start = 14.dp),
                    )
                    if (entry.is_favourite) {
                        Text(
                            "★",
                            color = colors.clay,
                            modifier = Modifier
                                .padding(start = 8.dp)
                                .semantics { contentDescription = "Favourite" },
                        )
                    }
                }
                if (i < index.lastIndex) {
                    HorizontalDivider(color = colors.line, modifier = Modifier.padding(horizontal = 20.dp))
                }
            }
        } else {
            item {
                Text(
                    text = "No recipes extracted from this book yet.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.muted,
                    modifier = Modifier.padding(20.dp),
                )
            }
        }
    }
}
