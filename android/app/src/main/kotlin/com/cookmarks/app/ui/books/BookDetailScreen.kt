package com.cookmarks.app.ui.books

import android.text.Html
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.BookDetail
import com.cookmarks.app.api.RecipeIndexEntry
import com.cookmarks.app.ui.cleanTitle
import com.cookmarks.app.ui.components.CoverPlate
import com.cookmarks.app.ui.components.Loaded
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme
import com.cookmarks.app.ui.titleSubtitle

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
    val description = remember(detail.description) {
        Html.fromHtml(detail.description, Html.FROM_HTML_MODE_COMPACT).toString().trim()
    }
    var filter by rememberSaveable { mutableStateOf("") }
    val positions = remember(index) {
        index.withIndex().associate { (i, entry) -> entry.id to i + 1 }
    }
    val shown = remember(index, filter) {
        val q = filter.trim().lowercase()
        if (q.isEmpty()) index else index.filter { it.name.lowercase().contains(q) }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 32.dp),
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
                            style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
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
                    detail.reading?.let { reading ->
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
                Button(
                    onClick = { onReadFrom(resume.id) },
                    shape = MaterialTheme.shapes.extraSmall,
                    colors = ButtonDefaults.buttonColors(containerColor = colors.clay),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 20.dp, vertical = 4.dp),
                ) {
                    Text(
                        text = if (detail.reading == null) "Start reading" else "Continue — ${resume.name}",
                        style = MaterialTheme.typography.labelLarge,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
        if (index.isNotEmpty()) {
            item {
                MonoLabel(
                    "Play in Discover \u2192",
                    colour = colors.clayDeep,
                    modifier = Modifier
                        .clickable { onDiscover(cleanTitle(detail.title)) }
                        .padding(horizontal = 20.dp, vertical = 10.dp),
                )
            }
            item {
                Column(modifier = Modifier.padding(horizontal = 20.dp)) {
                    HorizontalDivider(color = colors.lineStrong, modifier = Modifier.padding(top = 20.dp, bottom = 16.dp))
                    MonoLabel("Recipe index — ${index.size}")
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
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 12.dp, bottom = 8.dp),
                    )
                }
            }
            itemsIndexed(shown, key = { _, entry -> entry.id }) { i, entry ->
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onReadFrom(entry.id) }
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
                        Text("★", color = colors.clay, modifier = Modifier.padding(start = 8.dp))
                    }
                }
                if (i < shown.lastIndex) {
                    HorizontalDivider(color = colors.line, modifier = Modifier.padding(horizontal = 20.dp))
                }
            }
        } else {
            item {
                Text(
                    text = "No recipes extracted from this book yet.",
                    style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                    color = colors.muted,
                    modifier = Modifier.padding(20.dp),
                )
            }
        }
    }
}
