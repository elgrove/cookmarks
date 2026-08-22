package com.cookmarks.app.ui.reader

import android.util.Log
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.ReadingUpdate
import com.cookmarks.app.ui.components.Loaded
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.flow.collectLatest

sealed interface PagerSource {
    data class Book(val bookId: String) : PagerSource
    data class RecipeList(val listId: String) : PagerSource
}

@Composable
fun RecipePagerScreen(source: PagerSource, startRecipeId: String?, onBack: () -> Unit) {
    var tick by remember { mutableIntStateOf(0) }
    val state by rememberLoad(source, tick) {
        when (source) {
            is PagerSource.Book ->
                Api.service.recipeIndex(source.bookId).map { it.id to it.name }
            is PagerSource.RecipeList ->
                Api.service.list(source.listId).recipes.map { it.id to it.name }
        }
    }
    Loaded(state, onRetry = { tick++ }) { entries ->
        if (entries.isEmpty()) {
            MonoLabel("Nothing to read", modifier = Modifier.padding(20.dp))
            return@Loaded
        }
        Pager(source, entries, startRecipeId, onBack)
    }
}

@Composable
private fun Pager(
    source: PagerSource,
    entries: List<Pair<String, String>>,
    startRecipeId: String?,
    onBack: () -> Unit,
) {
    val colors = CmTheme.colors
    val start = entries.indexOfFirst { it.first == startRecipeId }.coerceAtLeast(0)
    val pagerState = rememberPagerState(initialPage = start) { entries.size }

    if (source is PagerSource.Book) {
        LaunchedEffect(pagerState) {
            snapshotFlow { pagerState.settledPage }.collectLatest { page ->
                try {
                    Api.service.updateReading(
                        source.bookId,
                        ReadingUpdate(mode = "recipes", recipe_id = entries[page].first),
                    )
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    Log.w("RecipePager", "reading position not saved", e)
                }
            }
        }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .fillMaxWidth()
                .padding(end = 20.dp),
        ) {
            IconButton(onClick = onBack) {
                Icon(
                    Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "Back",
                    tint = colors.muted,
                )
            }
            androidx.compose.foundation.layout.Spacer(modifier = Modifier.weight(1f))
            MonoLabel("${pagerState.currentPage + 1} / ${entries.size}", colour = colors.faint)
        }
        HorizontalDivider(color = colors.line)
        HorizontalPager(
            state = pagerState,
            beyondViewportPageCount = 1,
            modifier = Modifier.weight(1f),
        ) { page ->
            RecipePage(entries[page].first)
        }
    }
}
