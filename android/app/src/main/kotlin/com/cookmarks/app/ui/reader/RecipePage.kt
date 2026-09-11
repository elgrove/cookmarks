package com.cookmarks.app.ui.reader

import android.util.Log
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.RecipeDetail
import com.cookmarks.app.ui.Feedback
import com.cookmarks.app.ui.cleanTitle
import com.cookmarks.app.ui.components.Loaded
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.recipes.RecipeListsSheet
import com.cookmarks.app.ui.theme.CmTheme
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.launch

@Composable
fun RecipePage(recipeId: String) {
    var tick by remember { mutableIntStateOf(0) }
    val state by rememberLoad(recipeId, tick) { Api.service.recipe(recipeId) }
    var listsOpen by remember { mutableStateOf(false) }
    Loaded(state, onRetry = { tick++ }) { recipe ->
        RecipeContent(
            recipe = recipe,
            actions = { ReaderRecipeActions(recipe, onOpenLists = { listsOpen = true }) },
        )
        if (listsOpen) {
            RecipeListsSheet(recipe.id, onDismiss = { listsOpen = false })
        }
    }
}

@Composable
fun RecipeContent(
    recipe: RecipeDetail,
    controls: Boolean = true,
    header: @Composable ColumnScope.() -> Unit = { RecipeHeading(recipe) },
    actions: (@Composable RowScope.() -> Unit)? = null,
    after: @Composable ColumnScope.() -> Unit = {},
) {
    val colors = CmTheme.colors
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 20.dp),
    ) {
        header()
        if (recipe.yields != null || actions != null) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
            ) {
                recipe.yields?.let {
                    MonoLabel("Yields · $it", modifier = Modifier.weight(1f))
                }
                actions?.invoke(this)
            }
        }
        val hasDescription = !recipe.description.isNullOrBlank()
        if (controls && (hasDescription || recipe.has_image)) {
            if (hasDescription) {
                Text(
                    text = recipe.description.orEmpty(),
                    style = MaterialTheme.typography.bodyLarge,
                    color = colors.ink,
                    modifier = Modifier.padding(vertical = 8.dp),
                )
            }
            if (recipe.has_image) {
                AsyncImage(
                    model = Api.recipeImageUrl(recipe.id),
                    contentDescription = "Image of ${recipe.name}",
                    contentScale = ContentScale.FillWidth,
                    modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                )
            }
            Spacer(modifier = Modifier.height(10.dp))
        }
        if (recipe.ingredients_verbatim.isNotEmpty()) {
            MonoLabel("Ingredients", colour = colors.clayDeep)
            Column(modifier = Modifier.padding(top = 8.dp, bottom = 20.dp)) {
                recipe.ingredients_verbatim.forEachIndexed { i, line ->
                    Text(
                        text = line.text,
                        style = MaterialTheme.typography.bodyMedium,
                        color = colors.ink,
                        modifier = Modifier.padding(vertical = 6.dp),
                    )
                    if (i < recipe.ingredients_verbatim.lastIndex) HorizontalDivider(color = colors.line)
                }
            }
        }
        if (recipe.instructions.isNotEmpty()) {
            MonoLabel("Method", colour = colors.clayDeep)
            Column(
                verticalArrangement = Arrangement.spacedBy(14.dp),
                modifier = Modifier.padding(top = 10.dp, bottom = 20.dp),
            ) {
                recipe.instructions.forEachIndexed { i, step ->
                    Row {
                        MonoLabel((i + 1).toString().padStart(2, '0'), colour = colors.clay)
                        Text(
                            text = step,
                            style = MaterialTheme.typography.bodyLarge,
                            color = colors.ink,
                            modifier = Modifier.padding(start = 12.dp),
                        )
                    }
                }
            }
        }
        after()
    }
}

@Composable
private fun RecipeHeading(recipe: RecipeDetail) {
    val colors = CmTheme.colors
    MonoLabel("${cleanTitle(recipe.book_title)} — ${recipe.book_author}", colour = colors.faint)
    Text(
        text = recipe.name,
        style = MaterialTheme.typography.displaySmall,
        color = colors.ink,
        modifier = Modifier.padding(top = 8.dp, bottom = 16.dp),
    )
    if (recipe.keywords.isNotEmpty()) {
        MonoLabel(
            recipe.keywords.joinToString(" · "),
            colour = colors.clayDeep,
            modifier = Modifier.padding(bottom = 8.dp),
        )
    }
}

@Composable
private fun RowScope.ReaderRecipeActions(recipe: RecipeDetail, onOpenLists: () -> Unit) {
    val colors = CmTheme.colors
    val scope = rememberCoroutineScope()
    var favourite by remember(recipe.id) { mutableStateOf(recipe.is_favourite) }

    IconButton(
        onClick = {
            scope.launch {
                val previous = favourite
                favourite = !previous
                try {
                    favourite = Api.service.toggleFavourite(recipe.id).is_favourite
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    Log.w("RecipePage", "favourite toggle failed", e)
                    favourite = previous
                    Feedback.show("Couldn't update favourite")
                }
            }
        },
    ) {
        Icon(
            if (favourite) Icons.Filled.Favorite else Icons.Filled.FavoriteBorder,
            contentDescription = if (favourite) "Remove from favourites" else "Add to favourites",
            tint = if (favourite) colors.clay else colors.muted,
        )
    }
    Text(
        text = "LISTS +",
        style = MaterialTheme.typography.labelSmall,
        color = colors.muted,
        modifier = Modifier
            .border(1.dp, colors.lineStrong)
            .clickable(
                role = Role.Button,
                onClickLabel = "Add to lists",
                onClick = onOpenLists,
            )
            .padding(horizontal = 12.dp, vertical = 10.dp),
    )
}
