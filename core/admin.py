from django.contrib import admin

from .models import Book, Config, ExtractionReport, Keyword, Recipe, RecipeList, RecipeListItem


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'pubdate', 'calibre_id']
    list_filter = ['author']
    search_fields = ['title', 'author', 'isbn']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(ExtractionReport)
class ExtractionReportAdmin(admin.ModelAdmin):
    list_display = ['book', 'model_name', 'extraction_method', 'recipes_found', 'started_at', 'completed_at', 'cost_usd']
    list_filter = ['provider_name', 'model_name', 'extraction_method', 'started_at', 'completed_at']
    search_fields = ['book__title', 'book__author', 'model_name', 'provider_name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'queued_at', 'started_at', 'completed_at']
    date_hierarchy = 'started_at'
    
    fieldsets = (
        ('Book Information', {
            'fields': ('book',)
        }),
        ('Extraction Details', {
            'fields': ('provider_name', 'model_name', 'extraction_method', 'images_in_separate_chapters', 'images_can_be_matched')
        }),
        ('Timing', {
            'fields': ('queued_at', 'started_at', 'completed_at')
        }),
        ('Results', {
            'fields': ('total_chapters', 'chapters_processed', 'recipes_found', 'errors')
        }),
        ('Usage Metrics', {
            'fields': ('cost_usd', 'input_tokens', 'output_tokens')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Config)
class ConfigAdmin(admin.ModelAdmin):
    list_display = ['ai_provider', 'extraction_rate_limit_per_minute']
    readonly_fields = ['pk']
    
    fieldsets = (
        ('AI Provider Settings', {
            'fields': ('ai_provider', 'api_key')
        }),
        ('Extraction Settings', {
            'fields': ('extraction_rate_limit_per_minute',)
        }),
    )
    
    def has_add_permission(self, request):
        # Only allow one Config instance
        return not Config.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of the singleton Config
        return False


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
