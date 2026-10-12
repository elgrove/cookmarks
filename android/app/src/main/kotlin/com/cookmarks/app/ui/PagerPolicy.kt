package com.cookmarks.app.ui

/**
 * Policy for recipe pagers (MY-210).
 *
 * One tap on a search result used to fire 3 detail + 3 image + 3 Similar
 * Recipes request sets, because both [HorizontalPager][androidx.compose.foundation.pager.HorizontalPager]
 * instances pre-composed one page either side, and every composed page loaded
 * its full content plus its own Similar rail.
 *
 * The rule now: compose only the visible page, and load Similar Recipes only
 * for the settled page. Opening a recipe from a result list therefore causes
 * one detail request set (detail + at most one image + one similar).
 */
object PagerPolicy {
    /** Pages composed beyond the viewport on either side. Zero: visible page only. */
    const val BEYOND_VIEWPORT_PAGE_COUNT = 0

    /** True only for the settled, visible page. Guards Similar Recipes loading. */
    fun shouldLoadSimilar(page: Int, settledPage: Int): Boolean = page == settledPage
}
