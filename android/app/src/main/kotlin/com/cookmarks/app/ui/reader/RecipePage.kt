package com.cookmarks.app.ui.reader

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.RecipeDetail
import com.cookmarks.app.ui.cleanTitle
import com.cookmarks.app.ui.components.Loaded
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme

@Composable
fun RecipePage(recipeId: String) {
    var tick by remember { mutableIntStateOf(0) }
    val state by rememberLoad(recipeId, tick) { Api.service.recipe(recipeId) }
    Loaded(state, onRetry = { tick++ }) { recipe -> RecipeContent(recipe) }
}

@Composable
fun RecipeContent(
    recipe: RecipeDetail,
    controls: Boolean = true,
    header: @Composable ColumnScope.() -> Unit = { RecipeHeading(recipe) },
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
        val hasDescription = !recipe.description.isNullOrBlank()
        if (controls && (hasDescription || recipe.has_image)) {
            var showDescription by remember(recipe.id) { mutableStateOf(false) }
            var showPhoto by remember(recipe.id) { mutableStateOf(false) }
            Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                if (hasDescription) {
                    MonoLabel(
                        if (showDescription) "Hide description" else "Show description",
                        colour = colors.clay,
                        modifier = Modifier
                            .clickable(
                                role = Role.Button,
                                onClickLabel = if (showDescription) "Hide description" else "Show description",
                            ) { showDescription = !showDescription }
                            .semantics {
                                stateDescription = if (showDescription) "expanded" else "collapsed"
                            }
                            .padding(vertical = 6.dp),
                    )
                }
                if (recipe.has_image) {
                    MonoLabel(
                        if (showPhoto) "Hide photo" else "Show photo",
                        colour = colors.clay,
                        modifier = Modifier
                            .clickable(
                                role = Role.Button,
                                onClickLabel = if (showPhoto) "Hide photo" else "Show photo",
                            ) { showPhoto = !showPhoto }
                            .semantics {
                                stateDescription = if (showPhoto) "expanded" else "collapsed"
                            }
                            .padding(vertical = 6.dp),
                    )
                }
            }
            if (showDescription && hasDescription) {
                Text(
                    text = recipe.description.orEmpty(),
                    style = MaterialTheme.typography.bodyLarge.copy(fontStyle = FontStyle.Italic),
                    color = colors.ink,
                    modifier = Modifier.padding(vertical = 8.dp),
                )
            }
            if (showPhoto) {
                AsyncImage(
                    model = Api.recipeImageUrl(recipe.id),
                    contentDescription = "Image of ${recipe.name}",
                    contentScale = ContentScale.FillWidth,
                    modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                )
            }
            Spacer(modifier = Modifier.height(10.dp))
        }
        recipe.yields?.let {
            MonoLabel("Yields · $it", modifier = Modifier.padding(bottom = 16.dp))
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
}
