package com.cookmarks.app

import com.cookmarks.app.ui.cleanTitle
import com.cookmarks.app.ui.titleSubtitle
import org.junit.Assert.assertEquals
import org.junit.Test

class TitlesTest {
    @Test
    fun clean_title_drops_the_calibre_subtitle() {
        assertEquals("Persiana", cleanTitle("Persiana: Recipes from the Middle East & Beyond"))
        assertEquals("Persiana", cleanTitle("Persiana"))
    }

    @Test
    fun subtitle_is_the_remainder_with_further_colons_softened() {
        assertEquals("Japanese Soul Food", titleSubtitle("Nanban: Japanese Soul Food"))
        assertEquals("", titleSubtitle("Nanban"))
        assertEquals("A — B", titleSubtitle("T: A: B"))
    }
}
