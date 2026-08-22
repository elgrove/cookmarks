package com.cookmarks.app

import com.cookmarks.app.api.BookSummary
import com.cookmarks.app.ui.books.BookSort
import com.cookmarks.app.ui.books.arrangeBooks
import org.junit.Assert.assertEquals
import org.junit.Test

class BookSortTest {
    private fun book(title: String, author: String) = BookSummary(
        id = title,
        title = title,
        author = author,
        recipe_count = 0,
        progress = null,
        has_cover = false,
        pubdate = null,
        keywords = emptyList(),
    )

    private val books = listOf(
        book("Salt, Fat, Acid, Heat", "Samin Nosrat"),
        book("Made in India", "Meera Sodha"),
        book("apples galore", "Zed Cook"),
    )

    @Test
    fun added_keeps_server_order() {
        assertEquals(books, arrangeBooks(books, "", BookSort.ADDED))
    }

    @Test
    fun title_sort_is_case_insensitive() {
        val titles = arrangeBooks(books, "", BookSort.TITLE).map { it.title }
        assertEquals(listOf("apples galore", "Made in India", "Salt, Fat, Acid, Heat"), titles)
    }

    @Test
    fun author_sort_orders_by_author_then_title() {
        val authors = arrangeBooks(books, "", BookSort.AUTHOR).map { it.author }
        assertEquals(listOf("Meera Sodha", "Samin Nosrat", "Zed Cook"), authors)
    }

    @Test
    fun queue_sort_filters_to_queued_books_in_queue_order() {
        val queue = listOf("apples galore", "Salt, Fat, Acid, Heat")
        val titles = arrangeBooks(books, "", BookSort.QUEUE, queue).map { it.title }
        assertEquals(queue, titles)
    }

    @Test
    fun filter_matches_title_or_author_case_insensitively() {
        assertEquals(1, arrangeBooks(books, "sodha", BookSort.ADDED).size)
        assertEquals(1, arrangeBooks(books, "SALT", BookSort.ADDED).size)
        assertEquals(0, arrangeBooks(books, "zzz", BookSort.ADDED).size)
    }
}
