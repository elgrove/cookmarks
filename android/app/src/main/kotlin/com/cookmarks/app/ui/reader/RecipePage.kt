package com.cookmarks.app.ui.reader

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.RecipeDetail
import com.cookmarks.app.ui.components.Loaded
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.NoImagePlate
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme

@Composable
fun RecipePage(recipeId: String) {
    val state by rememberLoad(recipeId) { Api.service.recipe(recipeId) }
    Loaded(state) { recipe -> RecipeContent(recipe) }
}

@Composable
private fun RecipeContent(recipe: RecipeDetail) {
    val colors = CmTheme.colors
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 20.dp),
    ) {
        MonoLabel("${recipe.book_title} — ${recipe.book_author}", colour = colors.faint)
        Text(
            text = recipe.name,
            style = MaterialTheme.typography.displaySmall,
            color = colors.ink,
            modifier = Modifier.padding(top = 8.dp, bottom = 16.dp),
        )
        if (recipe.has_image) {
            AsyncImage(
                model = Api.recipeImageUrl(recipe.id),
                contentDescription = "Image of ${recipe.name}",
                contentScale = ContentScale.FillWidth,
                modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
            )
        } else {
            NoImagePlate(
                name = recipe.name,
                openingLine = recipe.description ?: recipe.instructions.firstOrNull(),
                modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
            )
        }
        if (!recipe.description.isNullOrBlank()) {
            Text(
                text = recipe.description,
                style = MaterialTheme.typography.bodyLarge.copy(fontStyle = FontStyle.Italic),
                color = colors.ink,
                modifier = Modifier.padding(bottom = 16.dp),
            )
        }
        recipe.yields?.let {
            MonoLabel("Yields · $it", modifier = Modifier.padding(bottom = 16.dp))
        }
        if (recipe.ingredients.isNotEmpty()) {
            MonoLabel("Ingredients", colour = colors.clayDeep)
            Column(modifier = Modifier.padding(top = 8.dp, bottom = 20.dp)) {
                recipe.ingredients.forEachIndexed { i, ingredient ->
                    Text(
                        text = ingredient,
                        style = MaterialTheme.typography.bodyMedium,
                        color = colors.ink,
                        modifier = Modifier.padding(vertical = 6.dp),
                    )
                    if (i < recipe.ingredients.lastIndex) HorizontalDivider(color = colors.line)
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
                        MonoLabel("%02d".format(i + 1), colour = colors.clay)
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
        if (recipe.keywords.isNotEmpty()) {
            MonoLabel(recipe.keywords.joinToString("  ·  "), colour = colors.faint)
        }
    }
}
