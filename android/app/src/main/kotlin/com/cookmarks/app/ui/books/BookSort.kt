package com.cookmarks.app.ui.books

import com.cookmarks.app.api.BookSummary

enum class BookSort(val label: String) {
    ADDED("Added"),
    TITLE("Title"),
    AUTHOR("Author"),
}

fun arrangeBooks(books: List<BookSummary>, query: String, sort: BookSort): List<BookSummary> {
    val q = query.trim().lowercase()
    val filtered = if (q.isEmpty()) books else books.filter {
        it.title.lowercase().contains(q) || it.author.lowercase().contains(q)
    }
    return when (sort) {
        BookSort.ADDED -> filtered
        BookSort.TITLE -> filtered.sortedBy { it.title.lowercase() }
        BookSort.AUTHOR -> filtered.sortedWith(
            compareBy({ it.author.lowercase() }, { it.title.lowercase() })
        )
    }
}
