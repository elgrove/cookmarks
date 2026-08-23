package com.cookmarks.app.ui.discover

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.gestures.draggable
import androidx.compose.foundation.gestures.rememberDraggableState
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.zIndex
import coil.compose.AsyncImage
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.RecipeDetail
import com.cookmarks.app.ui.components.CentredState
import com.cookmarks.app.ui.components.ErrorState
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.reader.RecipeContent
import com.cookmarks.app.ui.theme.CmTheme
import kotlin.math.abs
import kotlinx.coroutines.launch

@Composable
fun GameScreen(source: GameSource, onBack: () -> Unit) {
    val colors = CmTheme.colors
    val scope = rememberCoroutineScope()
    val deck = remember(source) { DeckController(source, scope) }
    LaunchedEffect(deck) { deck.refill() }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth().padding(end = 20.dp),
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back", tint = colors.muted)
            }
            MonoLabel(sourceLabel(source), colour = colors.faint)
        }
        HorizontalDivider(color = colors.line)
        Box(modifier = Modifier.weight(1f).fillMaxWidth()) {
            when {
                deck.cards.isNotEmpty() -> CardStack(deck)
                deck.error != null -> ErrorState(deck.error ?: "", onRetry = { deck.refill() })
                deck.loading -> CentredState { CircularProgressIndicator(color = colors.clay) }
                deck.exhausted -> CentredState {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        MonoLabel("That's everything")
                        Text(
                            text = "No more recipes to play here.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = colors.muted,
                            modifier = Modifier.padding(top = 8.dp),
                        )
                    }
                }
            }
        }
        MonoLabel(
            "← dismiss  ·  favourite →",
            colour = colors.faint,
            modifier = Modifier.align(Alignment.CenterHorizontally).padding(vertical = 10.dp),
        )
    }
}

private fun sourceLabel(source: GameSource): String = when (source) {
    GameSource.All -> "All recipes"
    is GameSource.Search ->
        (listOfNotNull(source.q.takeIf { it.isNotBlank() }?.let { "“$it”" }) + source.keywords)
            .joinToString("  ·  ")
    is GameSource.Semantic -> "✦ ${source.q}"
    is GameSource.Book -> source.title
}

@Composable
private fun CardStack(deck: DeckController) {
    BoxWithConstraints(modifier = Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 16.dp)) {
        val width = constraints.maxWidth.toFloat()
        val visible = deck.cards.take(3)
        visible.asReversed().forEach { card ->
            key(card.id) {
                PlayCard(
                    card = card,
                    width = width,
                    depth = visible.indexOf(card),
                    onSwipe = { favourite -> deck.swipe(card, favourite) },
                )
            }
        }
    }
}

@Composable
private fun PlayCard(card: GameCard, width: Float, depth: Int, onSwipe: (Boolean) -> Unit) {
    val colors = CmTheme.colors
    val onTop = depth == 0
    val scope = rememberCoroutineScope()
    val offsetX = remember { Animatable(0f) }
    val threshold = width * 0.35f
    var settled by remember { mutableStateOf(false) }

    val dragModifier = if (onTop) {
        Modifier.draggable(
            orientation = Orientation.Horizontal,
            state = rememberDraggableState { delta ->
                if (!settled) scope.launch { offsetX.snapTo(offsetX.value + delta) }
            },
            onDragStopped = { velocity ->
                if (settled) return@draggable
                if (abs(offsetX.value) > threshold || abs(velocity) > 4000f) {
                    settled = true
                    val direction = if (abs(offsetX.value) > threshold) offsetX.value else velocity
                    scope.launch {
                        offsetX.animateTo(if (direction > 0f) width * 1.4f else -width * 1.4f, tween(200))
                        onSwipe(direction > 0f)
                    }
                } else {
                    scope.launch { offsetX.animateTo(0f, spring()) }
                }
            },
        )
    } else {
        Modifier
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .zIndex(if (onTop) 1f else 0f)
            .graphicsLayer {
                if (onTop) {
                    translationX = offsetX.value
                    rotationZ = (offsetX.value / width) * 10f
                } else {
                    scaleX = 1f - 0.04f * depth
                    scaleY = 1f - 0.04f * depth
                    translationY = (14 * depth).dp.toPx()
                }
            }
            .then(dragModifier),
    ) {
        GameCardFace(card, flippable = onTop)
        if (onTop) {
            val pull = (abs(offsetX.value) / threshold).coerceIn(0f, 1f)
            if (pull > 0f) {
                Box(
                    modifier = Modifier
                        .matchParentSize()
                        .graphicsLayer { alpha = pull * 0.9f }
                        .background((if (offsetX.value > 0f) colors.clay else colors.muted).copy(alpha = 0.14f)),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = if (offsetX.value > 0f) "FAVOURITE" else "DISMISS",
                        style = MaterialTheme.typography.labelSmall.copy(fontSize = 24.sp, letterSpacing = 4.sp),
                        color = if (offsetX.value > 0f) colors.clayDeep else colors.muted,
                    )
                }
            }
        }
    }
}

@Composable
private fun GameCardFace(card: GameCard, flippable: Boolean) {
    val colors = CmTheme.colors
    var flipped by remember { mutableStateOf(false) }
    val angle by animateFloatAsState(if (flipped) 180f else 0f, tween(350), label = "flip")
    val state by rememberLoad(card.id) { Api.service.recipe(card.id) }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .graphicsLayer {
                rotationY = angle
                cameraDistance = 16f * density
            }
            .background(colors.bg)
            .border(1.dp, colors.lineStrong)
            .clickable(
                interactionSource = remember { MutableInteractionSource() },
                indication = null,
                enabled = flippable,
            ) { flipped = !flipped },
    ) {
        if (angle <= 90f) {
            CardFront(card, state)
        } else {
            Box(modifier = Modifier.fillMaxSize().graphicsLayer { rotationY = 180f }) {
                CardBack(state)
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun CardHeading(recipe: RecipeDetail) {
    val colors = CmTheme.colors
    Text(
        text = recipe.name,
        style = MaterialTheme.typography.displaySmall,
        color = colors.ink,
        modifier = Modifier.padding(bottom = 12.dp),
    )
    if (recipe.keywords.isNotEmpty()) {
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.padding(bottom = 16.dp),
        ) {
            recipe.keywords.forEach { keyword ->
                MonoLabel(
                    keyword,
                    colour = colors.bg,
                    modifier = Modifier
                        .background(colors.clay)
                        .padding(horizontal = 10.dp, vertical = 6.dp),
                )
            }
        }
    }
}

@Composable
private fun CardBack(state: Result<RecipeDetail>?) {
    val colors = CmTheme.colors
    val recipe = state?.getOrNull()
    when {
        recipe == null -> CentredState { CircularProgressIndicator(color = colors.clay) }
        recipe.has_image -> RecipeContent(recipe, controls = false, header = { CardHeading(recipe) })
        else -> Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 24.dp),
        ) {
            CardHeading(recipe)
            Text(
                text = recipe.description?.takeIf { it.isNotBlank() } ?: "No description for this recipe.",
                style = MaterialTheme.typography.bodyLarge.copy(fontStyle = FontStyle.Italic),
                color = if (recipe.description.isNullOrBlank()) colors.muted else colors.ink,
            )
        }
    }
}

@Composable
private fun CardFront(card: GameCard, state: Result<RecipeDetail>?) {
    val colors = CmTheme.colors
    val recipe = state?.getOrNull()
    if (recipe != null && !recipe.has_image) {
        RecipeContent(recipe, controls = false, header = { CardHeading(recipe) })
        return
    }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 24.dp),
    ) {
        if (recipe == null) {
            Text(
                text = card.name,
                style = MaterialTheme.typography.displaySmall,
                color = colors.ink,
                modifier = Modifier.padding(bottom = 12.dp),
            )
            if (state?.isFailure == true) {
                MonoLabel("Couldn't load this recipe — swipe on", colour = colors.muted)
            } else {
                CircularProgressIndicator(color = colors.clay, modifier = Modifier.padding(top = 16.dp))
            }
            return@Column
        }
        CardHeading(recipe)
        AsyncImage(
            model = Api.recipeImageUrl(recipe.id),
            contentDescription = "Image of ${recipe.name}",
            contentScale = ContentScale.FillWidth,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}
