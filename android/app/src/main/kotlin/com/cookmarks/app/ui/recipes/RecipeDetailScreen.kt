package com.cookmarks.app.ui.recipes

import android.util.Log
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.ListRecipeRef
import com.cookmarks.app.api.RecipeDetail
import com.cookmarks.app.ui.cleanTitle
import com.cookmarks.app.ui.components.Loaded
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.reader.RecipeContent
import com.cookmarks.app.ui.theme.CmTheme
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.launch

@Composable
fun RecipeDetailScreen(
    recipeId: String,
    onBack: () -> Unit,
    onOpenRecipe: (String, List<String>) -> Unit,
    contextIds: List<String> = emptyList(),
) {
    val colors = CmTheme.colors
    val scope = rememberCoroutineScope()
    val ids = remember(recipeId) {
        if (contextIds.size > 1 && recipeId in contextIds) contextIds else listOf(recipeId)
    }
    val pagerState = rememberPagerState(initialPage = ids.indexOf(recipeId)) { ids.size }
    val favourites = remember { mutableStateMapOf<String, Boolean>() }
    val currentId = ids[pagerState.currentPage]
    val favourite = favourites[currentId] == true
    var sheetOpen by remember { mutableStateOf(false) }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth().padding(end = 12.dp),
        ) {
            IconButton(onClick = onBack) {
                Icon(
                    Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "Back",
                    tint = colors.muted,
                )
            }
            if (ids.size > 1) {
                MonoLabel("${pagerState.currentPage + 1} / ${ids.size}", colour = colors.faint)
            }
            Spacer(modifier = Modifier.weight(1f))
            MonoLabel(
                "Lists",
                colour = colors.muted,
                modifier = Modifier.clickable { sheetOpen = true }.padding(12.dp),
            )
            IconButton(onClick = {
                scope.launch {
                    try {
                        favourites[currentId] = Api.service.toggleFavourite(currentId).is_favourite
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        Log.w("RecipeDetail", "favourite toggle failed", e)
                    }
                }
            }) {
                Icon(
                    if (favourite) Icons.Filled.Favorite else Icons.Filled.FavoriteBorder,
                    contentDescription = if (favourite) "Remove from favourites" else "Add to favourites",
                    tint = if (favourite) colors.clay else colors.muted,
                )
            }
        }
        HorizontalDivider(color = colors.line)
        HorizontalPager(
            state = pagerState,
            beyondViewportPageCount = 1,
            modifier = Modifier.weight(1f),
        ) { page ->
            RecipeDetailPage(ids[page], onOpenRecipe, onLoaded = { recipe ->
                if (recipe.id !in favourites) favourites[recipe.id] = recipe.is_favourite
            })
        }
    }
    if (sheetOpen) {
        ListsSheet(currentId, onDismiss = { sheetOpen = false })
    }
}

@Composable
private fun RecipeDetailPage(
    recipeId: String,
    onOpenRecipe: (String, List<String>) -> Unit,
    onLoaded: (RecipeDetail) -> Unit,
) {
    var tick by remember { mutableIntStateOf(0) }
    val state by rememberLoad(recipeId, tick) { Api.service.recipe(recipeId) }
    Loaded(state, onRetry = { tick++ }) { recipe ->
        LaunchedEffect(recipe) { onLoaded(recipe) }
        RecipeContent(recipe) {
            SimilarRail(recipe.id, onOpenRecipe)
        }
    }
}

@Composable
private fun SimilarRail(recipeId: String, onOpenRecipe: (String, List<String>) -> Unit) {
    val colors = CmTheme.colors
    val state by rememberLoad(recipeId) { Api.service.similarRecipes(recipeId) }
    val similar = state?.getOrNull() ?: return
    if (similar.items.isEmpty()) return
    Column(modifier = Modifier.padding(top = 24.dp)) {
        MonoLabel("Similar recipes", colour = colors.clayDeep)
        LazyRow(
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            modifier = Modifier.padding(top = 10.dp),
        ) {
            items(similar.items, key = { it.id }) { recipe ->
                Column(
                    modifier = Modifier
                        .width(180.dp)
                        .border(1.dp, colors.line)
                        .clickable { onOpenRecipe(recipe.id, similar.items.map { it.id }) }
                        .padding(14.dp),
                ) {
                    Text(
                        text = recipe.name,
                        style = MaterialTheme.typography.titleMedium,
                        color = colors.ink,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    MonoLabel(
                        cleanTitle(recipe.book_title),
                        colour = colors.faint,
                        modifier = Modifier.padding(top = 6.dp),
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ListsSheet(recipeId: String, onDismiss: () -> Unit) {
    val colors = CmTheme.colors
    val scope = rememberCoroutineScope()
    var tick by remember { mutableIntStateOf(0) }
    val state by rememberLoad(recipeId, tick) { Api.service.recipeLists(recipeId) }

    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = colors.bg) {
        Column(modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp)) {
            MonoLabel("Add to lists", colour = colors.clayDeep)
            val memberships = state?.getOrNull()
            if (memberships == null) {
                Box(
                    modifier = Modifier.fillMaxWidth().padding(24.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    if (state?.isFailure == true) {
                        MonoLabel("Could not load lists", colour = colors.faint)
                    } else {
                        CircularProgressIndicator(color = colors.clay)
                    }
                }
            } else {
                Column(modifier = Modifier.padding(top = 8.dp, bottom = 24.dp)) {
                    memberships.forEach { membership ->
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    scope.launch {
                                        try {
                                            if (membership.contains) {
                                                Api.service.removeFromList(membership.id, recipeId)
                                                tick++
                                            } else {
                                                Api.service.addToList(
                                                    membership.id,
                                                    ListRecipeRef(recipeId),
                                                )
                                                onDismiss()
                                            }
                                        } catch (e: CancellationException) {
                                            throw e
                                        } catch (e: Exception) {
                                            Log.w("RecipeDetail", "list toggle failed", e)
                                        }
                                    }
                                }
                                .padding(vertical = 4.dp),
                        ) {
                            Checkbox(
                                checked = membership.contains,
                                onCheckedChange = null,
                                colors = CheckboxDefaults.colors(
                                    checkedColor = colors.clay,
                                    uncheckedColor = colors.lineStrong,
                                ),
                            )
                            Text(
                                text = membership.name,
                                style = MaterialTheme.typography.bodyLarge,
                                color = colors.ink,
                                modifier = Modifier.padding(start = 8.dp),
                            )
                        }
                    }
                }
            }
        }
    }
}
