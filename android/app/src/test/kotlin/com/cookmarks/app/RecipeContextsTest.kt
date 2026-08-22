package com.cookmarks.app

import com.cookmarks.app.ui.RecipeContexts
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RecipeContextsTest {
    @Test
    fun round_trips_and_evicts_oldest() {
        val first = RecipeContexts.put(listOf("a", "b"))
        assertEquals(listOf("a", "b"), RecipeContexts.get(first))
        repeat(8) { RecipeContexts.put(listOf("x$it")) }
        assertTrue(RecipeContexts.get(first).isEmpty())
        assertTrue(RecipeContexts.get(null).isEmpty())
        assertTrue(RecipeContexts.get("missing").isEmpty())
    }
}
