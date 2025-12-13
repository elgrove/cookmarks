from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('books/', views.books, name='books'),
    path('book/<uuid:book_id>/', views.book_detail, name='book_detail'),
    path('book/<uuid:book_id>/extract/', views.queue_book_for_recipe_extraction, name='queue_book_for_recipe_extraction'),
    path('book/<uuid:book_id>/cover/', views.book_cover, name='book_cover'),
    path('recipes/', views.recipes, name='recipes'),
    path('recipe/<uuid:recipe_id>/', views.recipe_detail, name='recipe_detail'),
    path('recipe/image/<uuid:book_id>/<path:image_path>/', views.get_recipe_image, name='recipe_image'),
    path('lists/', views.recipe_lists, name='recipe_lists'),
    path('list/<uuid:list_id>/', views.recipe_list_detail, name='recipe_list_detail'),
    path('lists/create/', views.create_recipe_list, name='create_recipe_list'),
    path('list/<uuid:list_id>/delete/', views.delete_recipe_list, name='delete_recipe_list'),
    path('recipe/<uuid:recipe_id>/add-to-list/<uuid:list_id>/', views.add_recipe_to_list, name='add_recipe_to_list'),
    path('recipe/<uuid:recipe_id>/remove-from-list/<uuid:list_id>/', views.remove_recipe_from_list, name='remove_recipe_from_list'),
    path('tasks/', views.tasks, name='tasks'),
    path('tasks/queue-load-books/', views.queue_load_books_from_calibre, name='load_books_from_calibre'),
    path('tasks/queue-all-extractions/', views.queue_all_books_for_recipe_extraction, name='queue_all_books_for_extraction'),
    path('tasks/queue-random-extractions/', views.queue_random_books_for_recipe_extraction, name='queue_random_books_for_extraction'),
    path('config/', views.config, name='config'),
    path('extraction-reports/', views.extraction_reports, name='extraction_reports'),
]
