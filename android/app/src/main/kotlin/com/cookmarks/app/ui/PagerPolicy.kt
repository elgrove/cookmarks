package com.cookmarks.app.ui

/**
 * Policy for recipe pagers (MY-210).
 *
 * One tap on a search result used to fire 3 detail + 3 image + 3 Similar
 * Recipes request sets, because the search-result detail pager pre-composed
 * one page either side with beyondViewportPageCount = 1, and every composed
 * page loaded its full content plus its own Similar rail. The reader pager
 * had the same prefetch shape (detail + image only, no Similar rail).
 *
 * The rule now: compose only the visible page (prefetch zero), and load
 * Similar Recipes only for the settled page. Opening a recipe from a result
 * list therefore causes one detail request set (detail + at most one image
 * + one similar).
 *
 * Accepted trade-off: swiping away and back refetches the page (page state
 * is not cached), and a fast fling still loads each transient page it
 * settles on. Prefetch smoothness is sacrificed for request savings.
 */
object PagerPolicy {
    /** Pages composed beyond the viewport on either side. Zero: visible page only. */
    const val BEYOND_VIEWPORT_PAGE_COUNT = 0

    /** True only for the settled page. Guards Similar Recipes loading. */
    fun shouldLoadSimilar(page: Int, settledPage: Int): Boolean = page == settledPage
}
