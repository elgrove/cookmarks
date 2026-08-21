package com.cookmarks.app.api

import kotlinx.serialization.Serializable

@Serializable
data class LoginRequest(val username: String, val password: String)

@Serializable
data class AuthMe(
    val id: String,
    val username: String,
    val is_admin: Boolean,
    val auth_mode: String,
)

@Serializable
data class BookSummary(
    val id: String,
    val title: String,
    val author: String,
    val recipe_count: Int,
    val progress: Double?,
    val has_cover: Boolean,
    val pubdate: String?,
    val keywords: List<String>,
)

@Serializable
data class RecipeNeighbour(val id: String, val name: String)

@Serializable
data class ReadingState(
    val mode: String,
    val fraction: Double,
    val anchor: RecipeNeighbour?,
    val location: String?,
    val finished: Boolean,
)

@Serializable
data class RecipeRow(val id: String, val name: String, val keywords: List<String>)

@Serializable
data class BookDetail(
    val id: String,
    val title: String,
    val author: String,
    val isbn: String?,
    val pubdate: String?,
    val description: String,
    val recipe_count: Int,
    val has_cover: Boolean,
    val has_epub: Boolean,
    val added: String?,
    val keywords: List<String>,
    val recipes: List<RecipeRow>,
    val queued: Boolean,
    val reading: ReadingState?,
    val resume_recipe: RecipeNeighbour?,
)

@Serializable
data class ReadingUpdate(
    val mode: String,
    val recipe_id: String? = null,
    val location: String? = null,
)

@Serializable
data class RecipeIndexEntry(
    val id: String,
    val name: String,
    val is_favourite: Boolean,
    val epub_cfi: String?,
)

@Serializable
data class RecipeSummary(
    val id: String,
    val name: String,
    val book_id: String,
    val book_title: String,
    val book_author: String,
    val keywords: List<String>,
)

@Serializable
data class KeywordSummary(val name: String, val recipe_count: Int)

@Serializable
data class RecipeSearchResults(
    val total: Int,
    val items: List<RecipeSummary>,
    val facets: List<KeywordSummary> = emptyList(),
)

@Serializable
data class SemanticResult(
    val id: String,
    val name: String,
    val book_id: String,
    val book_title: String,
    val book_author: String,
    val keywords: List<String>,
    val distance: Double,
)

@Serializable
data class SemanticSearchResults(
    val available: Boolean,
    val query: String,
    val total: Int,
    val items: List<SemanticResult> = emptyList(),
)

@Serializable
data class RecipeDetail(
    val id: String,
    val book_id: String,
    val book_title: String,
    val book_author: String,
    val book_has_cover: Boolean,
    val name: String,
    val description: String?,
    val ingredients: List<String>,
    val instructions: List<String>,
    val yields: String?,
    val keywords: List<String>,
    val has_image: Boolean,
    val is_favourite: Boolean,
    val context: String,
    val in_book: Boolean?,
    val previous: RecipeNeighbour?,
    val next: RecipeNeighbour?,
)

@Serializable
data class SimilarRecipes(val basis: String, val items: List<RecipeSummary>)

@Serializable
data class ListSummary(
    val id: String,
    val name: String,
    val is_default: Boolean,
    val recipe_count: Int,
)

@Serializable
data class ListDetail(
    val id: String,
    val name: String,
    val is_default: Boolean,
    val recipe_count: Int,
    val recipes: List<RecipeSummary>,
)

@Serializable
data class ListMembership(
    val id: String,
    val name: String,
    val is_default: Boolean,
    val contains: Boolean,
)

@Serializable
data class FavouriteState(val is_favourite: Boolean)

@Serializable
data class ListCreate(val name: String)

@Serializable
data class ListRecipeRef(val recipe_id: String)
