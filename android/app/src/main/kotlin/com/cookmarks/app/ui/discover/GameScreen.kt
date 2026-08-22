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
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.zIndex
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.RecipeDetail
import com.cookmarks.app.ui.cleanTitle
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
            "← dismiss for good  ·  favourite →",
            colour = colors.faint,
            modifier = Modifier.align(Alignment.CenterHorizontally).padding(vertical = 10.dp),
        )
    }
}

private fun sourceLabel(source: GameSource): String = when (source) {
    GameSource.All -> "Everything"
    is GameSource.Search -> source.keyword ?: "“${source.q}”"
    is GameSource.Semantic -> "✦ ${source.q}"
    is GameSource.Book -> "This book"
}

@Composable
private fun CardStack(deck: DeckController) {
    BoxWithConstraints(modifier = Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 16.dp)) {
        val width = constraints.maxWidth.toFloat()
        val top = deck.cards.first()
        deck.cards.take(3).asReversed().forEach { card ->
            key(card.id) {
                PlayCard(
                    card = card,
                    width = width,
                    onTop = card.id == top.id,
                    onSwipe = { favourite -> deck.swipe(card, favourite) },
                )
            }
        }
    }
}

@Composable
private fun PlayCard(card: GameCard, width: Float, onTop: Boolean, onSwipe: (Boolean) -> Unit) {
    val colors = CmTheme.colors
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
                    val direction = if (offsetX.value != 0f) offsetX.value else velocity
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
                    scaleX = 0.96f
                    scaleY = 0.96f
                    translationY = 14.dp.toPx()
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
                val recipe = state?.getOrNull()
                if (recipe == null) {
                    CentredState { CircularProgressIndicator(color = colors.clay) }
                } else {
                    RecipeContent(recipe)
                }
            }
        }
    }
}

@Composable
private fun CardFront(card: GameCard, state: Result<RecipeDetail>?) {
    val colors = CmTheme.colors
    val recipe = state?.getOrNull()
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 24.dp),
    ) {
        if (recipe != null) {
            MonoLabel("${cleanTitle(recipe.book_title)} — ${recipe.book_author}", colour = colors.faint)
        }
        Text(
            text = recipe?.name ?: card.name,
            style = MaterialTheme.typography.displaySmall,
            color = colors.ink,
            modifier = Modifier.padding(top = 8.dp, bottom = 12.dp),
        )
        when {
            state?.isFailure == true -> {
                MonoLabel("Couldn't load this recipe — swipe on", colour = colors.muted)
                return@Column
            }
            recipe == null -> {
                CircularProgressIndicator(color = colors.clay, modifier = Modifier.padding(top = 16.dp))
                return@Column
            }
        }
        checkNotNull(recipe)
        if (recipe.keywords.isNotEmpty()) {
            MonoLabel(
                recipe.keywords.joinToString("  ·  "),
                colour = colors.clayDeep,
                modifier = Modifier.padding(bottom = 16.dp),
            )
        }
        if (recipe.ingredients.isNotEmpty()) {
            MonoLabel("Ingredients")
            Column(modifier = Modifier.padding(top = 8.dp)) {
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
        Spacer(modifier = Modifier.padding(8.dp))
        MonoLabel("Tap for the full recipe", colour = colors.faint)
    }
}
