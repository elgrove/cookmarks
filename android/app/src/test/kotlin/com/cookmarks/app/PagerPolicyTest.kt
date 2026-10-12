package com.cookmarks.app

import com.cookmarks.app.ui.PagerPolicy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * MY-210: one tap on a recipe from a result list must cause one detail
 * request set, not three.
 *
 * The pager policy is the seam that guarantees this: only the visible page
 * is composed, and only the settled page loads Similar Recipes. These tests
 * pin that policy so a future prefetch bump fails loudly.
 */
class PagerPolicyTest {
    @Test
    fun prefetch_is_zero_so_only_the_visible_page_composes() {
        assertEquals(0, PagerPolicy.BEYOND_VIEWPORT_PAGE_COUNT)
    }

    @Test
    fun similar_loads_only_for_the_settled_page() {
        assertTrue(PagerPolicy.shouldLoadSimilar(page = 20, settledPage = 20))
        assertFalse(PagerPolicy.shouldLoadSimilar(page = 19, settledPage = 20))
        assertFalse(PagerPolicy.shouldLoadSimilar(page = 21, settledPage = 20))
    }

    @Test
    fun opening_item_21_of_60_loads_one_similar_set() {
        val settled = 20
        val loaders = (0 until 60).count { PagerPolicy.shouldLoadSimilar(it, settled) }
        assertEquals(1, loaders)
    }

    @Test
    fun settling_on_a_new_page_moves_the_single_similar_load() {
        assertTrue(PagerPolicy.shouldLoadSimilar(page = 21, settledPage = 21))
        assertFalse(PagerPolicy.shouldLoadSimilar(page = 20, settledPage = 21))
    }
}
