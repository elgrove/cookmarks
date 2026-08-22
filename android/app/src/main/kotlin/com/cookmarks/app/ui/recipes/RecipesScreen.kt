package com.cookmarks.app.ui.recipes

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
import com.cookmarks.app.api.KeywordSummary
import com.cookmarks.app.api.RecipeSummary
import com.cookmarks.app.ui.components.ErrorState
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private const val PAGE_SIZE = 30

@Composable
fun RecipesScreen(onOpenRecipe: (String) -> Unit) {
    val colors = CmTheme.colors
    val scope = rememberCoroutineScope()
    var query by rememberSaveable { mutableStateOf("") }
    var semantic by rememberSaveable { mutableStateOf(false) }
    var selected by rememberSaveable { mutableStateOf(listOf<String>()) }
    var tick by remember { mutableIntStateOf(0) }

    var items by remember { mutableStateOf(listOf<RecipeSummary>()) }
    var total by remember { mutableIntStateOf(0) }
    var facets by remember { mutableStateOf(listOf<KeywordSummary>()) }
    var semanticUnavailable by remember { mutableStateOf(false) }
    var loading by remember { mutableStateOf(false) }
    var loadingMore by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    val restingKeywords by rememberLoad { Api.service.keywords() }

    LaunchedEffect(query, selected, semantic, tick) {
        if (query.isNotEmpty()) delay(300)
        loading = true
        error = null
        semanticUnavailable = false
        try {
            if (semantic) {
                if (query.isBlank()) {
                    items = emptyList()
                    total = 0
                } else {
                    val r = Api.service.semanticSearch(query)
                    semanticUnavailable = !r.available
                    items = r.items.map {
                        RecipeSummary(it.id, it.name, it.book_id, it.book_title, it.book_author, it.keywords)
                    }
                    total = r.total
                }
            } else {
                val r = Api.service.searchRecipes(q = query, keywords = selected, limit = PAGE_SIZE)
                items = r.items
                total = r.total
                facets = r.facets
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            error = e.message ?: "Unknown error"
        } finally {
            loading = false
        }
    }

    fun loadMore() {
        if (loadingMore || semantic || items.size >= total) return
        loadingMore = true
        scope.launch {
            try {
                val r = Api.service.searchRecipes(
                    q = query, keywords = selected, limit = PAGE_SIZE, offset = items.size,
                )
                items = items + r.items
                total = r.total
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
            } finally {
                loadingMore = false
            }
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(vertical = 16.dp),
    ) {
        item {
            Column(modifier = Modifier.padding(horizontal = 20.dp)) {
                Text(
                    text = "Recipes",
                    style = MaterialTheme.typography.displaySmall,
                    color = colors.ink,
                    modifier = Modifier.padding(bottom = 12.dp),
                )
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    placeholder = { Text(if (semantic) "Describe what you fancy" else "Search recipes") },
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
                    MonoLabel(
                        "Text",
                        colour = if (!semantic) colors.clay else colors.faint,
                        modifier = Modifier.clickable { semantic = false },
                    )
                    MonoLabel(
                        "Semantic",
                        colour = if (semantic) colors.clay else colors.faint,
                        modifier = Modifier.clickable { semantic = true },
                    )
                }
            }
        }
        if (!semantic) {
            item {
                KeywordChips(
                    resting = restingKeywords?.getOrNull().orEmpty(),
                    facets = facets,
                    selected = selected,
                    onToggle = { keyword ->
                        selected = if (keyword in selected) selected - keyword else selected + keyword
                    },
                )
            }
        }
        when {
            loading -> item {
                Box(modifier = Modifier.fillMaxWidth().padding(40.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = colors.clay)
                }
            }
            error != null -> item {
                Box(modifier = Modifier.fillMaxWidth().padding(vertical = 40.dp)) {
                    ErrorState(error ?: "", onRetry = { tick++ })
                }
            }
            semanticUnavailable -> item {
                StateLine("No AI provider configured — semantic search is off.")
            }
            semantic && query.isBlank() -> item {
                StateLine("Type a craving and semantic search finds the nearest recipes.")
            }
            items.isEmpty() -> item {
                StateLine("No matches.")
            }
            else -> {
                item {
                    MonoLabel(
                        "$total recipes",
                        colour = colors.faint,
                        modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
                    )
                }
                itemsIndexed(items, key = { _, r -> r.id }) { i, recipe ->
                    RecipeRow(i + 1, recipe, onClick = { onOpenRecipe(recipe.id) })
                    if (i < items.lastIndex) {
                        HorizontalDivider(color = colors.line, modifier = Modifier.padding(horizontal = 20.dp))
                    }
                }
                if (items.size < total && !semantic) {
                    item {
                        LaunchedEffect(items.size) { loadMore() }
                        Box(modifier = Modifier.fillMaxWidth().padding(20.dp), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator(color = colors.clay)
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun KeywordChips(
    resting: List<KeywordSummary>,
    facets: List<KeywordSummary>,
    selected: List<String>,
    onToggle: (String) -> Unit,
) {
    val colors = CmTheme.colors
    val pool = facets.ifEmpty { resting }
    val names = (selected + pool.map { it.name }).distinct().take(24)
    if (names.isEmpty()) return
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.padding(horizontal = 20.dp, vertical = 12.dp),
    ) {
        names.forEach { name ->
            val active = name in selected
            MonoLabel(
                name,
                colour = if (active) colors.bg else colors.muted,
                modifier = Modifier
                    .border(1.dp, if (active) colors.clay else colors.line)
                    .then(
                        if (active) Modifier.background(colors.clay) else Modifier
                    )
                    .clickable { onToggle(name) }
                    .padding(horizontal = 10.dp, vertical = 6.dp),
            )
        }
    }
}

@Composable
private fun RecipeRow(position: Int, recipe: RecipeSummary, onClick: () -> Unit) {
    val colors = CmTheme.colors
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 12.dp),
    ) {
        MonoLabel(position.toString().padStart(3, '0'), colour = colors.clay)
        Column(modifier = Modifier.weight(1f).padding(start = 14.dp)) {
            Text(
                text = recipe.name,
                style = MaterialTheme.typography.bodyLarge,
                color = colors.ink,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            MonoLabel(
                "${recipe.book_title} — ${recipe.book_author}",
                colour = colors.faint,
                modifier = Modifier.padding(top = 2.dp),
            )
        }
    }
}

@Composable
private fun StateLine(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
        color = CmTheme.colors.muted,
        modifier = Modifier.padding(horizontal = 20.dp, vertical = 32.dp),
    )
}
