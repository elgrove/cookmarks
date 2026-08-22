package com.cookmarks.app.ui

object RecipeContexts {
    private val contexts = LinkedHashMap<String, List<String>>()
    private var next = 0

    fun put(ids: List<String>): String {
        val key = (next++).toString()
        contexts[key] = ids
        while (contexts.size > 8) contexts.remove(contexts.keys.first())
        return key
    }

    fun get(key: String?): List<String> = key?.let { contexts[it] }.orEmpty()
}
