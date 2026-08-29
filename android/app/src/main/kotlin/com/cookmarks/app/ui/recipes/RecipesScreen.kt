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
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.KeywordSummary
import com.cookmarks.app.api.RecipeSummary
import com.cookmarks.app.ui.cleanTitle
import com.cookmarks.app.ui.components.ErrorState
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.discover.GameSource
import com.cookmarks.app.ui.theme.CmTheme
import kotlin.coroutines.cancellation.CancellationException
import kotlin.random.Random
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private const val PAGE_SIZE = 30

private object RecipesState {
    var query by mutableStateOf("")
    var semantic by mutableStateOf(false)
    var selected by mutableStateOf(listOf<String>())
    var tick by mutableIntStateOf(0)
    var items by mutableStateOf(listOf<RecipeSummary>())
    var total by mutableIntStateOf(0)
    var facets by mutableStateOf(listOf<KeywordSummary>())
    var semanticUnavailable by mutableStateOf(false)
    var seed by mutableIntStateOf(Random.nextInt(1_000_000))
    var loadedKey: List<Any>? = null
}

@Composable
fun RecipesScreen(onOpenRecipe: (String, List<String>) -> Unit, onPlay: (GameSource) -> Unit) {
    val colors = CmTheme.colors
    val scope = rememberCoroutineScope()
    val st = RecipesState
    var loading by remember { mutableStateOf(false) }
    var loadingMore by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val restingKeywords by rememberLoad(st.tick) { Api.service.keywords() }

    LaunchedEffect(st.query, st.selected, st.semantic, st.tick) {
        val key = listOf(st.query, st.selected, st.semantic, st.tick)
        if (st.loadedKey == key) return@LaunchedEffect
        if (!st.semantic && st.query.isNotEmpty()) delay(300)
        loading = true
        error = null
        st.semanticUnavailable = false
        try {
            if (st.semantic) {
                if (st.query.isBlank()) {
                    st.items = emptyList()
                    st.total = 0
                } else {
                    val r = Api.service.semanticSearch(st.query)
                    st.semanticUnavailable = !r.available
                    st.items = r.items.map {
                        RecipeSummary(it.id, it.name, it.book_id, it.book_title, it.book_author, it.keywords)
                    }
                    st.total = r.total
                }
            } else {
                st.seed = Random.nextInt(1_000_000)
                val r = Api.service.searchRecipes(
                    q = st.query, keywords = st.selected, seed = st.seed, limit = PAGE_SIZE,
                )
                st.items = r.items
                st.total = r.total
                st.facets = r.facets
            }
            st.loadedKey = key
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            error = e.message ?: "Unknown error"
        } finally {
            loading = false
        }
    }

    fun loadMore() {
        if (loadingMore || st.semantic || st.items.size >= st.total) return
        loadingMore = true
        val forQuery = st.query
        val forSelected = st.selected
        val forSeed = st.seed
        scope.launch {
            try {
                val r = Api.service.searchRecipes(
                    q = forQuery, keywords = forSelected, seed = forSeed,
                    limit = PAGE_SIZE, offset = st.items.size,
                )
                if (st.query == forQuery && st.selected == forSelected && st.seed == forSeed) {
                    st.items = (st.items + r.items).distinctBy { it.id }
                    st.total = r.total
                }
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
                    value = st.query,
                    onValueChange = {
                        st.query = it
                        st.semantic = false
                    },
                    placeholder = { Text("Search, or describe a dish") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    keyboardActions = KeyboardActions(onSearch = {
                        st.semantic = false
                        st.tick++
                    }),
                    trailingIcon = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            if (st.query.isNotEmpty()) {
                                IconButton(onClick = {
                                    st.query = ""
                                    st.semantic = false
                                }) {
                                    Icon(
                                        Icons.Filled.Close,
                                        contentDescription = "Clear search",
                                        tint = colors.faint,
                                    )
                                }
                            }
                            IconButton(onClick = {
                                st.semantic = false
                                st.tick++
                            }) {
                                Icon(
                                    Icons.Filled.Search,
                                    contentDescription = "Search",
                                    tint = colors.muted,
                                )
                            }
                            IconButton(
                                onClick = {
                                    if (st.query.isNotBlank()) {
                                        if (st.semantic) st.tick++ else st.semantic = true
                                    }
                                },
                                modifier = Modifier.semantics {
                                    role = Role.Button
                                    selected = st.semantic
                                    stateDescription = if (st.semantic) "active" else "inactive"
                                    contentDescription = "AI search"
                                },
                            ) {
                                Text(
                                    text = "\u2726",
                                    fontSize = 20.sp,
                                    color = if (st.semantic) colors.clay else colors.muted,
                                )
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
            }
        }
        if (!st.semantic) {
            item {
                KeywordChips(
                    resting = restingKeywords?.getOrNull().orEmpty(),
                    facets = st.facets,
                    selected = st.selected,
                    onToggle = { keyword ->
                        st.selected = if (keyword in st.selected) st.selected - keyword else st.selected + keyword
                    },
                )
            }
        }
        when {
            loading && st.items.isEmpty() -> item {
                Box(modifier = Modifier.fillMaxWidth().padding(40.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = colors.clay)
                }
            }
            error != null -> item {
                Box(modifier = Modifier.fillMaxWidth().padding(vertical = 40.dp)) {
                    ErrorState(error ?: "", onRetry = { st.tick++ })
                }
            }
            st.semanticUnavailable -> item {
                StateLine("No AI provider configured — semantic search is off.")
            }
            st.query.isBlank() && st.selected.isEmpty() -> item {
                StateLine("Search, pick a keyword, or describe a dish and press \u2726.")
            }
            st.items.isEmpty() -> item {
                StateLine("No matches.")
            }
            else -> {
                item {
                    Row(
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp),
                    ) {
                        MonoLabel(
                            "${st.total} recipes",
                            colour = colors.faint,
                            modifier = Modifier.padding(vertical = 8.dp),
                        )
                        MonoLabel(
                            "Play in Discover \u2192",
                            colour = colors.clayDeep,
                            modifier = Modifier
                                .clickable(
                                    role = Role.Button,
                                    onClickLabel = "Play in Discover",
                                ) {
                                    onPlay(
                                        if (st.semantic) GameSource.Semantic(st.query)
                                        else GameSource.Search(st.query, st.selected)
                                    )
                                }
                                .padding(vertical = 8.dp),
                        )
                    }
                }
                itemsIndexed(st.items, key = { _, r -> r.id }) { i, recipe ->
                    RecipeRow(recipe, onClick = { onOpenRecipe(recipe.id, st.items.map { it.id }) })
                    if (i < st.items.lastIndex) {
                        HorizontalDivider(color = colors.line, modifier = Modifier.padding(horizontal = 20.dp))
                    }
                }
                if (st.items.size < st.total && !st.semantic) {
                    item {
                        LaunchedEffect(st.items.size) { loadMore() }
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
                    .clickable(
                        role = Role.Checkbox,
                        onClickLabel = if (active) "Remove keyword filter $name" else "Filter by keyword $name",
                    ) { onToggle(name) }
                    .semantics {
                        this.selected = active
                        this.stateDescription = if (active) "selected" else "not selected"
                    }
                    .padding(horizontal = 10.dp, vertical = 6.dp),
            )
        }
    }
}

@Composable
private fun RecipeRow(recipe: RecipeSummary, onClick: () -> Unit) {
    val colors = CmTheme.colors
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(
                role = Role.Button,
                onClickLabel = "Open ${recipe.name}",
                onClick = onClick,
            )
            .padding(horizontal = 20.dp, vertical = 12.dp),
    ) {
        Text(
            text = recipe.name,
            style = MaterialTheme.typography.bodyLarge,
            color = colors.ink,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        MonoLabel(
            "${recipe.book_author} — ${cleanTitle(recipe.book_title)}",
            colour = colors.faint,
            modifier = Modifier.padding(top = 2.dp),
        )
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
