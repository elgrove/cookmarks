package com.cookmarks.app.ui.books

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
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.BookSummary
import com.cookmarks.app.ui.cleanTitle
import com.cookmarks.app.ui.components.CoverPlate
import com.cookmarks.app.ui.components.Loaded
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme

@Composable
fun BooksScreen(onOpenBook: (String) -> Unit) {
    val colors = CmTheme.colors
    var tick by remember { mutableIntStateOf(0) }
    val state by rememberLoad(tick) { Api.service.books() }
    val queueState by rememberLoad(tick) { Api.service.readingQueue() }
    var query by rememberSaveable { mutableStateOf("") }
    var sort by rememberSaveable { mutableStateOf(BookSort.ADDED) }

    Loaded(state, onRetry = { tick++ }) { books ->
        val queue = queueState?.getOrNull().orEmpty().reversed().map { it.id }
        val shown = arrangeBooks(books, query, sort, queue)
        LazyVerticalGrid(
            columns = GridCells.Fixed(2),
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            item(span = { androidx.compose.foundation.lazy.grid.GridItemSpan(2) }) {
                Column {
                    Text(
                        text = "Books",
                        style = MaterialTheme.typography.displaySmall,
                        color = colors.ink,
                        modifier = Modifier.padding(bottom = 12.dp),
                    )
                    OutlinedTextField(
                        value = query,
                        onValueChange = { query = it },
                        placeholder = { Text("Filter by title or author") },
                        singleLine = true,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = colors.clay,
                            unfocusedBorderColor = colors.lineStrong,
                            cursorColor = colors.clay,
                        ),
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(20.dp),
                        modifier = Modifier.padding(top = 12.dp),
                    ) {
                        BookSort.entries.forEach { option ->
                            MonoLabel(
                                text = option.label,
                                colour = if (option == sort) colors.clay else colors.faint,
                                modifier = Modifier.clickable { sort = option },
                            )
                        }
                    }
                }
            }
            if (sort == BookSort.QUEUE && shown.isEmpty()) {
                item(span = { androidx.compose.foundation.lazy.grid.GridItemSpan(2) }) {
                    Text(
                        text = "Nothing queued yet.",
                        style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                        color = colors.muted,
                        modifier = Modifier.padding(vertical = 20.dp),
                    )
                }
            }
            items(shown, key = { it.id }) { book ->
                BookCard(book, onClick = { onOpenBook(book.id) })
            }
        }
    }
}

@Composable
private fun BookCard(book: BookSummary, onClick: () -> Unit) {
    val colors = CmTheme.colors
    Column(modifier = Modifier.clickable(onClick = onClick)) {
        Box(modifier = Modifier.fillMaxWidth().aspectRatio(0.72f)) {
            if (book.has_cover) {
                AsyncImage(
                    model = Api.bookCoverUrl(book.id),
                    contentDescription = "Cover of ${book.title}",
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(),
                )
            } else {
                CoverPlate(cleanTitle(book.title), modifier = Modifier.fillMaxSize())
            }
        }
        if (book.progress != null) {
            Box(
                modifier = Modifier
                    .fillMaxWidth(book.progress.toFloat().coerceIn(0f, 1f))
                    .height(2.dp)
                    .background(colors.clay),
            )
        }
        Text(
            text = cleanTitle(book.title),
            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
            color = colors.ink,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(top = 8.dp),
        )
        MonoLabel(book.author, modifier = Modifier.padding(top = 2.dp))
    }
}
