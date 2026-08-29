package com.cookmarks.app.ui.discover

import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.GameRecipeIds
import com.cookmarks.app.api.ReadingUpdate
import com.cookmarks.app.ui.Feedback
import kotlin.coroutines.cancellation.CancellationException
import kotlin.random.Random
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

data class GameCard(val id: String, val name: String)

sealed interface GameSource {
    data object All : GameSource
    data class Search(val q: String, val keywords: List<String>) : GameSource
    data class Semantic(val q: String) : GameSource
    data class Book(val bookId: String, val title: String) : GameSource
}

object GameDeck {
    const val REFILL_BELOW = 5
    const val PAGE_SIZE = 30

    fun resumeFrom(entries: List<GameCard>, resumeId: String?): List<GameCard> {
        val start = entries.indexOfFirst { it.id == resumeId }
        return if (start < 0) entries else entries.drop(start)
    }

    fun merge(hand: List<GameCard>, fetched: List<GameCard>, spent: Set<String>): List<GameCard> {
        val held = spent.toMutableSet()
        hand.mapTo(held) { it.id }
        return hand + fetched.filter { held.add(it.id) }
    }
}

class DeckController(private val source: GameSource, private val scope: CoroutineScope) {
    var cards by mutableStateOf(listOf<GameCard>())
        private set
    var exhausted by mutableStateOf(false)
        private set
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    private val spent = mutableSetOf<String>()
    private val seed = Random.nextInt(1_000_000)
    private var offset = 0
    private var refilling = false

    fun refill() {
        if (refilling) return
        refilling = true
        loading = true
        error = null
        scope.launch {
            try {
                while (cards.size < GameDeck.REFILL_BELOW && !exhausted) {
                    val batch = nextBatch()
                    if (batch.isEmpty()) {
                        exhausted = true
                        break
                    }
                    val eligible =
                        Api.service.gameEligible(GameRecipeIds(batch.map { it.id })).recipe_ids.toSet()
                    cards = GameDeck.merge(cards, batch.filter { it.id in eligible }, spent)
                    if (source is GameSource.Semantic || source is GameSource.Book) exhausted = true
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                error = e.message ?: "Unknown error"
            } finally {
                loading = false
                refilling = false
            }
        }
    }

    fun swipe(card: GameCard, favourite: Boolean) {
        spent += card.id
        cards = cards.filterNot { it.id == card.id }
        scope.launch {
            try {
                if (favourite) Api.service.toggleFavourite(card.id) else Api.service.dismissRecipe(card.id)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (favourite) {
                    Log.w("DeckController", "favourite not saved", e)
                    Feedback.show("Couldn't favourite recipe")
                } else {
                    Log.w("DeckController", "dismissal not saved", e)
                    Feedback.show("Couldn't dismiss recipe")
                }
            }
        }
        if (source is GameSource.Book) markRead(source.bookId, card.id)
        if (cards.size < GameDeck.REFILL_BELOW) refill()
    }

    private fun markRead(bookId: String, recipeId: String) {
        scope.launch {
            try {
                Api.service.updateReading(bookId, ReadingUpdate(mode = "recipes", recipe_id = recipeId))
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w("DeckController", "reading position not saved", e)
                Feedback.show("Couldn't save reading position")
            }
        }
    }

    private suspend fun nextBatch(): List<GameCard> = when (source) {
        is GameSource.All, is GameSource.Search -> {
            val search = source as? GameSource.Search
            val r = Api.service.searchRecipes(
                q = search?.q.orEmpty(),
                keywords = search?.keywords.orEmpty(),
                seed = seed,
                limit = GameDeck.PAGE_SIZE,
                offset = offset,
                all = source is GameSource.All,
            )
            offset += r.items.size
            r.items.map { GameCard(it.id, it.name) }
        }
        is GameSource.Semantic -> {
            val r = Api.service.semanticSearch(source.q, limit = 100)
            if (!r.available) {
                throw IllegalStateException("No AI provider configured — semantic search is off.")
            }
            r.items.map { GameCard(it.id, it.name) }
        }
        is GameSource.Book -> {
            val entries = Api.service.recipeIndex(source.bookId).map { GameCard(it.id, it.name) }
            GameDeck.resumeFrom(entries, Api.service.book(source.bookId).resume_recipe?.id)
        }
    }
}
