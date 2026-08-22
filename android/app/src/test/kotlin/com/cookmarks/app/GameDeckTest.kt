package com.cookmarks.app

import com.cookmarks.app.ui.discover.GameCard
import com.cookmarks.app.ui.discover.GameDeck
import org.junit.Assert.assertEquals
import org.junit.Test

class GameDeckTest {
    private fun card(id: String) = GameCard(id, "Recipe $id")

    @Test
    fun merge_appends_new_cards_in_order() {
        val hand = listOf(card("a"), card("b"))
        val merged = GameDeck.merge(hand, listOf(card("c"), card("d")), emptySet())
        assertEquals(listOf("a", "b", "c", "d"), merged.map { it.id })
    }

    @Test
    fun merge_drops_cards_already_in_hand() {
        val hand = listOf(card("a"))
        val merged = GameDeck.merge(hand, listOf(card("a"), card("b")), emptySet())
        assertEquals(listOf("a", "b"), merged.map { it.id })
    }

    @Test
    fun merge_drops_spent_cards() {
        val merged = GameDeck.merge(emptyList(), listOf(card("a"), card("b")), setOf("a"))
        assertEquals(listOf("b"), merged.map { it.id })
    }

    @Test
    fun merge_dedupes_within_the_fetched_batch() {
        val merged = GameDeck.merge(emptyList(), listOf(card("a"), card("a"), card("b")), emptySet())
        assertEquals(listOf("a", "b"), merged.map { it.id })
    }
}
