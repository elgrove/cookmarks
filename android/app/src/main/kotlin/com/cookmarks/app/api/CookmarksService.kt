package com.cookmarks.app.api

import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

interface CookmarksService {
    @POST("api/auth/login")
    suspend fun login(@Body body: LoginRequest): AuthMe

    @POST("api/auth/logout")
    suspend fun logout()

    @GET("api/auth/me")
    suspend fun me(): AuthMe

    @GET("api/books")
    suspend fun books(): List<BookSummary>

    @GET("api/books/{id}")
    suspend fun book(@Path("id") id: String): BookDetail

    @GET("api/books/{id}/recipe-index")
    suspend fun recipeIndex(@Path("id") id: String): List<RecipeIndexEntry>

    @PUT("api/books/{id}/reading")
    suspend fun updateReading(@Path("id") id: String, @Body body: ReadingUpdate): ReadingState

    @GET("api/recipes")
    suspend fun searchRecipes(
        @Query("q") q: String = "",
        @Query("keyword") keywords: List<String> = emptyList(),
        @Query("limit") limit: Int = 30,
        @Query("offset") offset: Int = 0,
    ): RecipeSearchResults

    @GET("api/recipes/semantic")
    suspend fun semanticSearch(
        @Query("q") q: String,
        @Query("limit") limit: Int = 30,
    ): SemanticSearchResults

    @GET("api/keywords")
    suspend fun keywords(@Query("limit") limit: Int = 50): List<KeywordSummary>

    @GET("api/recipes/{id}")
    suspend fun recipe(@Path("id") id: String): RecipeDetail

    @GET("api/recipes/{id}/similar")
    suspend fun similarRecipes(@Path("id") id: String): SimilarRecipes

    @POST("api/recipes/{id}/favourite")
    suspend fun toggleFavourite(@Path("id") id: String): FavouriteState

    @GET("api/recipes/{id}/lists")
    suspend fun recipeLists(@Path("id") id: String): List<ListMembership>

    @GET("api/lists")
    suspend fun lists(): List<ListSummary>

    @POST("api/lists")
    suspend fun createList(@Body body: ListCreate): ListSummary

    @GET("api/lists/{id}")
    suspend fun list(@Path("id") id: String): ListDetail

    @POST("api/lists/{id}/recipes")
    suspend fun addToList(@Path("id") id: String, @Body body: ListRecipeRef)

    @DELETE("api/lists/{listId}/recipes/{recipeId}")
    suspend fun removeFromList(@Path("listId") listId: String, @Path("recipeId") recipeId: String)
}
