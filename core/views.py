import random
import zipfile
from datetime import date, timedelta

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django_q.tasks import async_task

from .forms import ConfigForm, RecipeKeywordsForm
from .models import (
    Book,
    Config,
    ExtractionReport,
    Keyword,
    Recipe,
    RecipeList,
    RecipeListItem,
)


def home(request):
    books = list(Book.objects.all())
    has_books = len(books) > 0
    has_recipes = Recipe.objects.exists()
    is_configured = Config.is_configured()
    books_count = len(books)
    
    book_of_the_day = None
    if has_books:
        today = date.today()
        seed = int(today.strftime('%Y%m%d'))
        random.seed(seed)
        book_of_the_day = random.choice(books)
    
    context = {
        'has_books': has_books,
        'has_recipes': has_recipes,
        'is_configured': is_configured,
        'book_of_the_day': book_of_the_day,
        'books_count': books_count,
    }
    return render(request, 'core/home.html', context)


def books(request):
    books = Book.objects.annotate(recipe_count=Count('recipes'))
    
    search = request.GET.get('search', '')
    if search:
        books = books.filter(title__icontains=search) | books.filter(author__icontains=search)
    
    selected_authors = request.GET.getlist('selected_authors[]')
    if selected_authors:
        books = books.filter(author__in=selected_authors)
    
    has_recipes = request.GET.get('has_recipes', '')
    if has_recipes:
        books = books.filter(recipe_count__gte=1)
    
    sort_by = request.GET.get('sort', 'random')
    if sort_by == 'title':
        books = books.order_by('title')
    elif sort_by == 'author':
        books = books.order_by('author', 'title')
    elif sort_by == 'recipes':
        books = books.order_by('-recipe_count', 'title')
    elif sort_by == 'random':
        books = books.order_by('?')
    else:
        books = books.order_by('-calibre_id')
    
    authors = Book.objects.values_list('author', flat=True).distinct().order_by('author')
    
    paginator = Paginator(books, 30)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'books': page_obj,
        'page_obj': page_obj,
        'search': search,
        'selected_authors': selected_authors,
        'has_recipes': has_recipes,
        'sort_by': sort_by,
        'authors': authors,
    }
    
    return render(request, 'core/books.html', context)


def book_cover(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    cover_path = book.get_cover_image_path()
    
    if not cover_path.exists():
        raise Http404("Cover image not found")
    
    return FileResponse(open(cover_path, 'rb'), content_type='image/jpeg')


def book_detail(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    all_recipes = book.recipes.all()
    
    # Get a random sample of up to 6 recipes
    recipe_ids = list(all_recipes.values_list('id', flat=True))
    if len(recipe_ids) > 6:
        sample_ids = random.sample(recipe_ids, 6)
        sample_recipes = all_recipes.filter(id__in=sample_ids)
    else:
        sample_recipes = all_recipes
    
    all_lists = RecipeList.objects.all()
    
    context = {
        'book': book,
        'recipes': all_recipes,
        'sample_recipes': sample_recipes,
        'all_lists': all_lists,
    }
    
    return render(request, 'core/book_detail.html', context)


def queue_book_for_recipe_extraction(request, book_id):
    if request.method == 'POST':
        book = get_object_or_404(Book, id=book_id)
        extraction_method = request.POST.get('extraction_method', None)
        config = Config.get_solo()
        
        existing = book.extraction_reports.filter(started_at__isnull=True).exists()
        if not existing:
            extraction = ExtractionReport.objects.create(
                book=book,
                provider_name=config.ai_provider,
                extraction_method=extraction_method,
            )
            async_task('core.tasks.extract_recipes_from_book', book.id, str(extraction.id))
        else:
            # already queued — pass the existing queued extraction report id to the worker
            queued = book.extraction_reports.filter(started_at__isnull=True).first()
            if queued:
                async_task('core.tasks.extract_recipes_from_book', book.id, str(queued.id))
            else:
                async_task('core.tasks.extract_recipes_from_book', book.id)
        messages.success(request, f"Queued recipe extraction for {book.title}")
        
        referer = request.META.get('HTTP_REFERER', '')
        if 'tasks' in referer:
            return redirect('tasks')
        return redirect('book_detail', book_id=book_id)
    
    referer = request.META.get('HTTP_REFERER', '')
    if 'tasks' in referer:
        return redirect('tasks')
    return redirect('book_detail', book_id=book_id)


def recipes(request):
    recipes = Recipe.objects.select_related('book').prefetch_related('keywords').all()
    
    search = request.GET.get('search', '')
    if search:
        recipes = recipes.filter(name__icontains=search) | recipes.filter(description__icontains=search)
    
    selected_books = request.GET.getlist('selected_books[]')
    if selected_books:
        recipes = recipes.filter(book__id__in=selected_books)
    
    selected_authors = request.GET.getlist('selected_authors[]')
    if selected_authors:
        recipes = recipes.filter(book__author__in=selected_authors)
    
    selected_keywords = request.GET.getlist('selected_keywords[]')
    if selected_keywords:
        recipes = recipes.filter(keywords__name__in=selected_keywords).distinct()
    
    book_id = request.GET.get('book')
    if book_id:
        recipes = recipes.filter(book__id=book_id)
        default_sort = 'order'
    else:
        default_sort = 'random'
    
    sort_by = request.GET.get('sort', default_sort)
    if sort_by == 'order':
        recipes = recipes.order_by('book', 'order')
    elif sort_by == 'name':
        recipes = recipes.order_by('name')
    elif sort_by == 'book':
        recipes = recipes.order_by('book__title', 'order')
    elif sort_by == 'author':
        recipes = recipes.order_by('book__author', 'book__title', 'order')
    elif sort_by == 'random':
        recipes = recipes.order_by('?')
    else:
        recipes = recipes.order_by('?')
    
    all_books = Book.objects.filter(recipes__isnull=False).distinct().order_by('title')
    all_authors = Book.objects.filter(recipes__isnull=False).values_list('author', flat=True).distinct().order_by('author')
    all_keywords = Keyword.objects.all()
    
    paginator = Paginator(recipes, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'recipes': page_obj,
        'page_obj': page_obj,
        'search': search,
        'selected_books': selected_books,
        'selected_authors': selected_authors,
        'selected_keywords': selected_keywords,
        'sort_by': sort_by,
        'all_books': all_books,
        'all_authors': all_authors,
        'all_keywords': all_keywords,
    }
    
    return render(request, 'core/recipes.html', context)


def recipe_detail(request, recipe_id):
    recipe = get_object_or_404(Recipe, id=recipe_id)

    if request.method == 'POST':
        form = RecipeKeywordsForm(request.POST)
        if form.is_valid():
            keyword_string = form.cleaned_data['keywords']
            keyword_names = [name.strip() for name in keyword_string.split(',') if name.strip()]
            
            keywords = []
            for name in keyword_names:
                keyword, _ = Keyword.objects.get_or_create(name=name)
                keywords.append(keyword)
                
            recipe.keywords.set(keywords)
            messages.success(request, 'Keywords updated successfully.')
            return redirect('recipe_detail', recipe_id=recipe.id)
    else:
        keyword_string = ", ".join([k.name for k in recipe.keywords.all()])
        form = RecipeKeywordsForm(initial={'keywords': keyword_string})
    
    image_on_left = int(recipe.id) % 2 == 0
    if not recipe.image:
        image_on_left = False

    recipe_lists = recipe.recipe_lists.all()
    all_lists = RecipeList.objects.all()
    available_lists = all_lists.exclude(id__in=recipe_lists.values_list('id', flat=True))

    context = {
        'recipe': recipe,
        'book': recipe.book,
        'image_on_left': image_on_left,
        'previous_recipe': recipe.get_previous_in_book(),
        'next_recipe': recipe.get_next_in_book(),
        'recipe_lists': recipe_lists,
        'available_lists': available_lists,
        'form': form,
    }
    
    return render(request, 'core/recipe_detail.html', context)


def recipe_lists(request):
    lists = RecipeList.objects.annotate(recipe_count=Count('recipes')).all()
    
    search = request.GET.get('search', '')
    if search:
        lists = lists.filter(name__icontains=search)
    
    context = {
        'lists': lists,
        'search': search,
    }
    
    return render(request, 'core/recipe_lists.html', context)


def recipe_list_detail(request, list_id):
    recipe_list = get_object_or_404(RecipeList, id=list_id)
    list_items = RecipeListItem.objects.filter(recipe_list=recipe_list).select_related('recipe__book')
    
    context = {
        'recipe_list': recipe_list,
        'list_items': list_items,
    }
    
    return render(request, 'core/recipe_list_detail.html', context)


def create_recipe_list(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        
        if name:
            recipe_list = RecipeList.objects.create(name=name)
            messages.success(request, f'Created list "{recipe_list.name}"')
            return redirect('recipe_list_detail', list_id=recipe_list.id)
        else:
            messages.error(request, 'List name is required')
    
    return redirect('recipe_lists')


def add_recipe_to_list(request, recipe_id, list_id):
    if request.method == 'POST':
        recipe = get_object_or_404(Recipe, id=recipe_id)
        recipe_list = get_object_or_404(RecipeList, id=list_id)
        
        _, created = RecipeListItem.objects.get_or_create(
            recipe=recipe,
            recipe_list=recipe_list
        )
        
        if created:
            messages.success(request, f'Added "{recipe.name}" to "{recipe_list.name}"')
        else:
            messages.info(request, f'"{recipe.name}" is already in "{recipe_list.name}"')
    
    return redirect(request.META.get('HTTP_REFERER', 'recipe_lists'))


def remove_recipe_from_list(request, recipe_id, list_id):
    if request.method == 'POST':
        recipe = get_object_or_404(Recipe, id=recipe_id)
        recipe_list = get_object_or_404(RecipeList, id=list_id)
        
        deleted_count, _ = RecipeListItem.objects.filter(
            recipe=recipe,
            recipe_list=recipe_list
        ).delete()
        
        if deleted_count > 0:
            messages.success(request, f'Removed "{recipe.name}" from "{recipe_list.name}"')
        else:
            messages.warning(request, f'"{recipe.name}" was not in "{recipe_list.name}"')
    
    return redirect(request.META.get('HTTP_REFERER', 'recipe_lists'))


def delete_recipe_list(request, list_id):
    if request.method == 'POST':
        recipe_list = get_object_or_404(RecipeList, id=list_id)
        list_name = recipe_list.name
        recipe_list.delete()
        messages.success(request, f'Deleted list "{list_name}"')
    
    return redirect('recipe_lists')


def tasks(request):
    books = Book.objects.all().order_by('title')
    books_with_recipes = Book.objects.annotate(recipe_count=Count('recipes')).filter(recipe_count__gt=0)
    
    context = {
        'books': books,
        'books_with_recipes': books_with_recipes,
    }
    
    return render(request, 'core/tasks.html', context)


def queue_load_books_from_calibre(request):
    if request.method == 'POST':
        try:
            async_task('core.tasks.load_books_from_calibre_task')
            messages.success(request, 'Load books task has been queued successfully.')
        except Exception as e:
            messages.error(request, f'Error queuing load books task: {str(e)}')
        
        return redirect('tasks')
    
    return redirect('tasks')


def queue_all_books_for_recipe_extraction(request):
    if request.method == 'POST':
        extraction_method = request.POST.get('extraction_method', None)
        config = Config.get_solo()
        
        books = Book.objects.all().order_by('-calibre_id')
        count = books.count()
        for book in books:
            existing = book.extraction_reports.filter(started_at__isnull=True).exists()
            if not existing:
                extraction = ExtractionReport.objects.create(
                    book=book,
                    provider_name=config.ai_provider,
                    extraction_method=extraction_method,
                )
                async_task('core.tasks.extract_recipes_from_book', book.id, str(extraction.id), group='queue_all_extractions')
            else:
                queued = book.extraction_reports.filter(started_at__isnull=True).first()
                if queued:
                    async_task('core.tasks.extract_recipes_from_book', book.id, str(queued.id), group='queue_all_extractions')
                else:
                    async_task('core.tasks.extract_recipes_from_book', book.id, group='queue_all_extractions')

        messages.success(request, f"Queued {count} books for extraction.")
        return redirect('tasks')

    return redirect('tasks')


def queue_random_books_for_recipe_extraction(request):
    if request.method == 'POST':
        try:
            count = int(request.POST.get('count', 10))
        except ValueError:
            count = 10

        extraction_method = request.POST.get('extraction_method', None)
        count = max(1, min(count, 1000))
        all_books = list(Book.objects.all())
        if not all_books:
            messages.warning(request, 'No books found to queue for extraction.')
            return redirect('tasks')

        if count >= len(all_books):
            chosen = all_books
        else:
            chosen = random.sample(all_books, count)

        config = Config.get_solo()
        for book in chosen:
            existing = book.extraction_reports.filter(started_at__isnull=True).exists()
            if not existing:
                extraction = ExtractionReport.objects.create(
                    book=book,
                    provider_name=config.ai_provider,
                    extraction_method=extraction_method,
                )
                async_task('core.tasks.extract_recipes_from_book', book.id, str(extraction.id), group='queue_random_extractions')
            else:
                queued = book.extraction_reports.filter(started_at__isnull=True).first()
                if queued:
                    async_task('core.tasks.extract_recipes_from_book', book.id, str(queued.id), group='queue_random_extractions')
                else:
                    async_task('core.tasks.extract_recipes_from_book', book.id, group='queue_random_extractions')

        messages.success(request, f"Queued {len(chosen)} random books for extraction.")
        return redirect('tasks')

    return redirect('tasks')


def config(request):
    config_obj = Config.get_solo()
    
    if request.method == 'POST':
        form = ConfigForm(request.POST, instance=config_obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Configuration saved successfully.')
            return redirect('config')
    else:
        form = ConfigForm(instance=config_obj)
    
    context = {
        'form': form,
        'config': config_obj,
    }
    return render(request, 'core/config.html', context)


def extraction_reports(request):
    total_books = Book.objects.count()
    total_recipes = Recipe.objects.count()
    processed_books = Book.objects.annotate(recipe_count=Count('recipes')).filter(recipe_count__gt=0).count()

    fourteen_days_ago = now() - timedelta(days=14)
    extraction_reports = ExtractionReport.objects.select_related('book').filter(created_at__gte=fourteen_days_ago)[:100]

    config = Config.get_solo()

    context = {
        'total_books': total_books,
        'total_recipes': total_recipes,
        'processed_books': processed_books,
        'extraction_reports': extraction_reports,
        'config': config,
    }
    return render(request, 'core/extraction_reports.html', context)


def get_recipe_image(request, book_id, image_path):
    book = get_object_or_404(Book, pk=book_id)
    epub_path = book.get_epub_path()

    if not epub_path or not epub_path.exists():
        raise Http404("EPUB file not found.")

    try:
        with zipfile.ZipFile(epub_path, 'r') as epub:
            image_data = epub.read(image_path)
            return HttpResponse(image_data, content_type='image/jpeg')
    except KeyError:
        raise Http404(f"Image '{image_path}' not found in EPUB.")
