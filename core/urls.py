from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("books/", views.books, name="books"),
    path("book/<uuid:book_id>/", views.book_detail, name="book_detail"),
    path(
        "book/<uuid:book_id>/extract/",
        views.queue_book_for_recipe_extraction,
        name="queue_book_for_recipe_extraction",
    ),
    path("book/<uuid:book_id>/cover/", views.book_cover, name="book_cover"),
    path("book/<uuid:book_id>/clear-images/", views.clear_book_images, name="clear_book_images"),
    path("book/<uuid:book_id>/clear-recipes/", views.clear_book_recipes, name="clear_book_recipes"),
    path("book/<uuid:book_id>/delete/", views.delete_book, name="delete_book"),
    path("recipes/", views.recipes, name="recipes"),
    path("search/", views.search, name="search"),
    path("search/ai-translate/", views.ai_search_translate, name="ai_search_translate"),
    path("recipe/<uuid:recipe_id>/", views.recipe_detail, name="recipe_detail"),
    path(
        "recipe/<uuid:recipe_id>/toggle-favourite/", views.toggle_favourite, name="toggle_favourite"
    ),
    path("recipe/<uuid:recipe_id>/delete/", views.delete_recipe, name="delete_recipe"),
    path(
        "recipe/<uuid:recipe_id>/clear-image/", views.clear_recipe_image, name="clear_recipe_image"
    ),
    path(
        "recipe/image/<uuid:book_id>/<path:image_path>/",
        views.get_recipe_image,
        name="recipe_image",
    ),
    path("lists/", views.recipe_lists, name="recipe_lists"),
    path("list/<uuid:list_id>/", views.recipe_list_detail, name="recipe_list_detail"),
    path("lists/create/", views.create_recipe_list, name="create_recipe_list"),
    path(
        "recipe/<uuid:recipe_id>/create-list-and-add/",
        views.create_list_and_add_recipe,
        name="create_list_and_add_recipe",
    ),
    path("list/<uuid:list_id>/delete/", views.delete_recipe_list, name="delete_recipe_list"),
    path(
        "recipe/<uuid:recipe_id>/add-to-list/<uuid:list_id>/",
        views.add_recipe_to_list,
        name="add_recipe_to_list",
    ),
    path(
        "recipe/<uuid:recipe_id>/remove-from-list/<uuid:list_id>/",
        views.remove_recipe_from_list,
        name="remove_recipe_from_list",
    ),
    path("tasks/", views.tasks, name="tasks"),
    path(
        "tasks/queue-load-books/",
        views.queue_load_books_from_calibre,
        name="load_books_from_calibre",
    ),
    path(
        "tasks/queue-deduplicate-keywords/",
        views.queue_deduplicate_keywords,
        name="deduplicate_keywords",
    ),
    path(
        "tasks/queue-all-extractions/",
        views.queue_all_books_for_recipe_extraction,
        name="queue_all_books_for_extraction",
    ),
    path(
        "tasks/queue-random-extractions/",
        views.queue_random_books_for_recipe_extraction,
        name="queue_random_books_for_extraction",
    ),
    path("config/", views.config, name="config"),
    path("extraction-reports/", views.extraction_reports, name="extraction_reports"),
]
