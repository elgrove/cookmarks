from django.contrib import admin

from .models import Book, Keyword, Recipe, RecipeList, RecipeListItem


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'pubdate', 'calibre_id']
    list_filter = ['author']
    search_fields = ['title', 'author', 'isbn']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Keyword)
class KeywordAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ['name', 'book', 'order']
    list_filter = ['book', 'keywords']
    search_fields = ['name', 'book__title', 'book__author']
    filter_horizontal = ['keywords']
    readonly_fields = ['id', 'created_at', 'updated_at']


class RecipeListItemInline(admin.TabularInline):
    model = RecipeListItem
    extra = 1
    readonly_fields = ['created_at']


@admin.register(RecipeList)
class RecipeListAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    inlines = [RecipeListItemInline]
