import json
import logging
import random
import zipfile
from datetime import date, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Case, Count, Q, Sum, Value, When
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django_q.tasks import async_task

from core.services.ai import GeminiProvider, OpenRouterProvider
from core.services.embeddings import search_recipes as vector_search_recipes
from core.services.calibre import refresh_single_book_from_calibre
from core.services.extraction import app as extraction_app
from core.tasks import save_recipes_from_graph_state

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

logger = logging.getLogger(__name__)


def home(request):
    books = list(Book.objects.all())
    has_books = len(books) > 0
    has_recipes = Recipe.objects.exists()
    is_configured = Config.is_configured()
    books_count = len(books)

    book_of_the_day = None
    if has_books:
        today = date.today()
        seed = int(today.strftime("%Y%m%d"))
        random.seed(seed)
        book_of_the_day = random.choice(books)

    context = {
        "has_books": has_books,
        "has_recipes": has_recipes,
        "is_configured": is_configured,
        "book_of_the_day": book_of_the_day,
        "books_count": books_count,
    }
    return render(request, "core/home.html", context)


def books(request):
    books = Book.objects.annotate(recipe_count=Count("recipes"))

    search = request.GET.get("search", "")
    if search:
        books = books.filter(title__icontains=search) | books.filter(author__icontains=search)

    selected_authors = request.GET.getlist("selected_authors[]")
    if selected_authors:
        books = books.filter(author__in=selected_authors)

    has_recipes = request.GET.get("has_recipes", "")
    if has_recipes:
        books = books.filter(recipe_count__gte=1)

    sort_by = request.GET.get("sort", "random")
    if sort_by == "title":
        books = books.order_by("title")
    elif sort_by == "author":
        books = books.order_by("author", "title")
    elif sort_by == "recipes":
        books = books.order_by("-recipe_count", "title")
    elif sort_by == "recent":
        books = books.order_by("-calibre_added_at", "title")
    elif sort_by == "random":
        has_recipes_order = Case(
            When(recipe_count__gte=1, then=Value(0)),
            default=Value(1),
        )
        books = books.order_by(has_recipes_order, "?")
    else:
        books = books.order_by("-calibre_added_at", "title")

    authors = Book.objects.values_list("author", flat=True).distinct().order_by("author")

    paginator = Paginator(books, 60)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "books": page_obj,
        "page_obj": page_obj,
        "search": search,
        "selected_authors": selected_authors,
        "has_recipes": has_recipes,
        "sort_by": sort_by,
        "authors": authors,
    }

    return render(request, "core/books.html", context)


def book_cover(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    cover_path = book.get_cover_image_path()

    if not cover_path.exists():
        raise Http404("Cover image not found")

    return FileResponse(open(cover_path, "rb"), content_type="image/jpeg")


def book_detail(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    all_recipes = book.recipes.prefetch_related("keywords").all()

    recipe_ids = list(all_recipes.values_list("id", flat=True))
    if len(recipe_ids) > 6:
        sample_ids = random.sample(recipe_ids, 6)
        sample_recipes = all_recipes.filter(id__in=sample_ids)
    else:
        sample_recipes = all_recipes

    all_lists = RecipeList.objects.all()

    config = Config.get_solo()
    available_models = []
    if config.ai_provider:
        provider_map = {
            "OPENROUTER": OpenRouterProvider,
            "GEMINI": GeminiProvider,
        }
        provider_class = provider_map.get(config.ai_provider)
        if provider_class:
            model_attrs = [
                "IMAGE_MATCH_MODEL",
                "EXTRACT_MANY_PER_FILE_MODEL",
                "EXTRACT_ONE_PER_FILE_MODEL",
                "EXTRACT_BLOCKS_MODEL",
                "DEDUPLICATE_MODEL",
            ]
            models = set()
            for attr in model_attrs:
                model = getattr(provider_class, attr, None)
                if model and model != NotImplemented:
                    models.add(model)
            available_models = sorted(models)

    first_recipe = all_recipes.order_by("order").first()

    context = {
        "book": book,
        "recipes": all_recipes,
        "sample_recipes": sample_recipes,
        "all_lists": all_lists,
        "available_models": available_models,
        "first_recipe": first_recipe,
    }

    return render(request, "core/book_detail.html", context)


def queue_book_for_recipe_extraction(request, book_id):
    if request.method == "POST":
        book = get_object_or_404(Book, id=book_id)
        extraction_method = request.POST.get("extraction_method") or None
        model_name = request.POST.get("model_name") or None
        config = Config.get_solo()

        existing = book.extraction_reports.filter(started_at__isnull=True).exists()
        if not existing:
            extraction = ExtractionReport.objects.create(
                book=book,
                provider_name=config.ai_provider,
                extraction_method=extraction_method,
                model_name=model_name,
            )
            async_task("core.tasks.extract_recipes_from_book", book.id, str(extraction.id))
        else:
            async_task("core.tasks.extract_recipes_from_book", book.id)
        messages.success(request, f"Queued recipe extraction for {book.title}")

        referer = request.META.get("HTTP_REFERER", "")
        if "tasks" in referer:
            return redirect("tasks")
        return redirect("book_detail", book_id=book_id)

    referer = request.META.get("HTTP_REFERER", "")
    if "tasks" in referer:
        return redirect("tasks")
    return redirect("book_detail", book_id=book_id)


def clear_book_images(request, book_id):
    if request.method == "POST":
        book = get_object_or_404(Book, id=book_id)
        updated_count = book.recipes.update(image="")
        messages.success(
            request,
            f"Removed images from {updated_count} recipe{'s' if updated_count != 1 else ''}.",
        )
    return redirect("book_detail", book_id=book_id)


def clear_book_recipes(request, book_id):
    if request.method == "POST":
        book = get_object_or_404(Book, id=book_id)
        deleted_count, _ = book.recipes.all().delete()
        messages.success(
            request,
            f"Removed {deleted_count} recipe{'s' if deleted_count != 1 else ''} from this book.",
        )
    return redirect("book_detail", book_id=book_id)


def generate_book_embeddings(request, book_id):
    if request.method == "POST":
        book = get_object_or_404(Book, id=book_id)
        recipe_count = book.recipes.count()
        if recipe_count > 0:
            async_task("core.tasks.generate_book_embeddings_task", book.id)
            messages.success(
                request,
                f"Queued embedding generation for {recipe_count} recipes from {book.clean_title}",
            )
        else:
            messages.warning(request, "No recipes to generate embeddings for.")
    return redirect("book_detail", book_id=book_id)


def refresh_book_metadata(request, book_id):
    if request.method == "POST":
        book = get_object_or_404(Book, id=book_id)
        try:
            refresh_single_book_from_calibre(book)
            messages.success(request, f'Updated metadata for "{book.clean_title}" from Calibre.')
        except Exception as e:
            messages.error(request, f"Failed to update metadata: {e!s}")
    return redirect("book_detail", book_id=book_id)


def delete_book(request, book_id):
    if request.method == "POST":
        book = get_object_or_404(Book, id=book_id)
        title = book.clean_title
        book.delete()
        messages.success(request, f'Deleted "{title}" and all associated recipes.')
        return redirect("books")
    return redirect("book_detail", book_id=book_id)


def recipes(request):
    recipes_qs = Recipe.objects.select_related("book").prefetch_related("keywords")
    has_searched = False
    filters = []
    group_logic = request.GET.get("group_logic", "or")
    vector_search_ids = None

    vector_ids_param = request.GET.get("vector_ids", "").strip()
    if vector_ids_param:
        vector_search_ids = vector_ids_param.split(",")
        has_searched = True

    query = request.GET.get("q", "").strip()

    book_id = request.GET.get("book")
    selected_book = None
    if book_id:
        try:
            selected_book = Book.objects.get(id=book_id)
            recipes_qs = recipes_qs.filter(book=selected_book)
            has_searched = True
        except Book.DoesNotExist:
            pass

    selected_lists = request.GET.getlist("selected_lists[]")
    list_id = request.GET.get("list")
    if list_id and list_id not in selected_lists:
        selected_lists.append(list_id)

    selected_keywords = request.GET.getlist("selected_keywords[]")
    if selected_keywords:
        for keyword_name in selected_keywords:
            recipes_qs = recipes_qs.filter(keywords__name__iexact=keyword_name)
        has_searched = True

    filter_fields = request.GET.getlist("filter_field[]")
    filter_ops = request.GET.getlist("filter_op[]")
    filter_values = request.GET.getlist("filter_value[]")
    filter_groups = request.GET.getlist("filter_group[]")
    filter_logics = request.GET.getlist("filter_logic[]")

    if filter_fields and filter_values:
        groups_dict = {}
        for field, op, value, group_idx, logic in zip(
            filter_fields, filter_ops, filter_values, filter_groups, filter_logics, strict=False
        ):
            if value.strip():
                group_key = int(group_idx) if group_idx.isdigit() else 0
                if group_key not in groups_dict:
                    groups_dict[group_key] = {"logic": logic, "conditions": []}
                groups_dict[group_key]["conditions"].append(
                    {"field": field, "op": op, "value": value.strip()}
                )
        filters = [groups_dict[k] for k in sorted(groups_dict.keys())]

    # M2M fields need chained .filter() calls for AND logic
    m2m_fields = {f.name for f in Recipe._meta.get_fields() if f.many_to_many}

    field_map = {
        f.name: f.name
        for f in Recipe._meta.get_fields()
        if hasattr(f, "get_internal_type") and f.get_internal_type() == "TextField"
    }
    for f in Recipe._meta.get_fields():
        if f.many_to_many:
            field_map[f.name] = f"{f.name}__name"
    field_map.update(
        {
            "author": "book__author",
            "book": "book__title",
        }
    )

    def apply_condition(field, op, value):
        db_field = field_map.get(field, field)

        if op == "contains":
            return Q(**{f"{db_field}__icontains": value})
        elif op == "not_contains":
            return ~Q(**{f"{db_field}__icontains": value})
        elif op == "equals":
            return Q(**{f"{db_field}__iexact": value})
        elif op == "starts":
            return Q(**{f"{db_field}__istartswith": value})
        return Q()

    def is_positive_m2m_condition(condition):
        return condition["field"] in m2m_fields and condition["op"] in (
            "contains",
            "equals",
            "starts",
        )

    # Build query
    combined_q = Q()
    chained_m2m_filters = []
    any_search = False

    if query:
        any_search = True
        has_searched = True
        quick_q = (
            Q(name__icontains=query)
            | Q(ingredients__icontains=query)
            | Q(instructions__icontains=query)
            | Q(keywords__name__icontains=query)
            | Q(book__author__icontains=query)
            | Q(book__title__icontains=query)
        )
        combined_q &= quick_q

    if selected_lists:
        has_searched = True
        any_search = True
        recipes_qs = recipes_qs.filter(recipe_lists__id__in=selected_lists)

    if filters:
        has_searched = True
        any_search = True
        group_queries = []

        for group in filters:
            if group["logic"] == "and":
                m2m_conditions = [c for c in group["conditions"] if is_positive_m2m_condition(c)]
                other_conditions = [
                    c for c in group["conditions"] if not is_positive_m2m_condition(c)
                ]

                group_q = Q()
                for condition in other_conditions:
                    cond_q = apply_condition(
                        condition["field"], condition["op"], condition["value"]
                    )
                    group_q &= cond_q

                for condition in m2m_conditions:
                    chained_m2m_filters.append(
                        apply_condition(condition["field"], condition["op"], condition["value"])
                    )

                if group_q:
                    group_queries.append(group_q)
            else:
                group_q = Q()
                for condition in group["conditions"]:
                    cond_q = apply_condition(
                        condition["field"], condition["op"], condition["value"]
                    )
                    group_q |= cond_q
                if group_q:
                    group_queries.append(group_q)

        if group_queries:
            final_filter_q = group_queries[0]
            for gq in group_queries[1:]:
                if group_logic == "and":
                    final_filter_q &= gq
                else:
                    final_filter_q |= gq
            combined_q &= final_filter_q

    if any_search or vector_search_ids:
        recipes_qs = recipes_qs.filter(combined_q)
        for m2m_q in chained_m2m_filters:
            recipes_qs = recipes_qs.filter(m2m_q)
        if vector_search_ids:
            recipes_qs = recipes_qs.filter(id__in=vector_search_ids)
        recipes_qs = recipes_qs.distinct()

    if vector_search_ids:
        default_sort = "relevance"
    elif selected_book:
        default_sort = "order"
    elif len(selected_lists) == 1:
        default_sort = "list_order"
    else:
        default_sort = "recent"

    sort_by = request.GET.get("sort", default_sort)
    if sort_by == "relevance" and vector_search_ids:
        id_to_position = {vid: idx for idx, vid in enumerate(vector_search_ids)}
        recipes_list = list(recipes_qs)
        recipes_list.sort(key=lambda r: id_to_position.get(str(r.id), 9999))
        recipes_qs = recipes_list
    elif sort_by == "name":
        recipes_qs = recipes_qs.order_by("name")
    elif sort_by == "recent":
        recipes_qs = recipes_qs.order_by("-created_at")
    elif sort_by == "author":
        recipes_qs = recipes_qs.order_by("book__author", "book__title", "name")
    elif sort_by == "book":
        recipes_qs = recipes_qs.order_by("book__title", "order")
    elif sort_by == "order":
        recipes_qs = recipes_qs.order_by("book", "order")
    elif sort_by == "list_order" and len(selected_lists) == 1:
        recipes_qs = recipes_qs.order_by("list_items__id")
    elif sort_by == "random":
        recipes_qs = recipes_qs.order_by("?")
    else:
        recipes_qs = recipes_qs.order_by("name")

    if not has_searched:
        recipes_qs = Recipe.objects.none()

    all_books = Book.objects.filter(recipes__isnull=False).distinct().order_by("title")
    all_authors = (
        Book.objects.filter(recipes__isnull=False)
        .values_list("author", flat=True)
        .distinct()
        .order_by("author")
    )
    all_keywords = Keyword.objects.annotate(recipe_count=Count("recipes")).order_by("-recipe_count")
    all_lists = RecipeList.objects.all()

    paginator = Paginator(recipes_qs, 30)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    if selected_book and not query and not filters and not selected_lists:
        recipe_context_params = f"context=book&book_id={selected_book.id}"
    elif len(selected_lists) == 1 and not query and not filters:
        recipe_context_params = f"context=list&list_id={selected_lists[0]}"
    elif sort_by != "random":
        params = ["context=search"]
        if query:
            params.append(f"q={query}")
        if vector_ids_param:
            params.append(f"vector_ids={vector_ids_param}")
        if sort_by:
            params.append(f"sort={sort_by}")
        if group_logic:
            params.append(f"group_logic={group_logic}")
        if selected_book:
            params.append(f"book={selected_book.id}")
        for kw in selected_keywords:
            params.append(f"selected_keywords[]={kw}")
        for lid in selected_lists:
            params.append(f"selected_lists[]={lid}")
        for field, op, value, group_idx, logic in zip(
            filter_fields, filter_ops, filter_values, filter_groups, filter_logics, strict=False
        ):
            if value.strip():
                params.append(f"filter_field[]={field}")
                params.append(f"filter_op[]={op}")
                params.append(f"filter_value[]={value}")
                params.append(f"filter_group[]={group_idx}")
                params.append(f"filter_logic[]={logic}")
        recipe_context_params = "&".join(params)
    else:
        recipe_context_params = "context=book"

    context = {
        "recipes": page_obj,
        "query": query,
        "filters": filters,
        "group_logic": group_logic,
        "sort_by": sort_by,
        "has_searched": has_searched,
        "recipe_context_params": recipe_context_params,
        "selected_lists": selected_lists,
        "selected_keywords": selected_keywords,
        "selected_book": selected_book,
        "all_books": all_books,
        "all_authors": all_authors,
        "all_keywords": all_keywords,
        "all_lists": all_lists,
        "vector_ids": vector_ids_param,
    }

    return render(request, "core/recipes.html", context)


def recipe_detail(request, recipe_id):
    recipe = get_object_or_404(Recipe, id=recipe_id)

    if request.method == "POST":
        form = RecipeKeywordsForm(request.POST)
        if form.is_valid():
            keyword_string = form.cleaned_data["keywords"]
            keyword_names = [name.strip() for name in keyword_string.split(",") if name.strip()]

            keywords = []
            for name in keyword_names:
                keyword, _ = Keyword.objects.get_or_create(name=name)
                keywords.append(keyword)

            recipe.keywords.set(keywords)
            messages.success(request, "Keywords updated successfully.")
            return redirect("recipe_detail", recipe_id=recipe.id)
    else:
        keyword_string = ", ".join([k.name for k in recipe.keywords.all()])
        form = RecipeKeywordsForm(initial={"keywords": keyword_string})

    recipe_lists = recipe.recipe_lists.all()
    all_lists = RecipeList.objects.all()
    available_lists = all_lists.exclude(id__in=recipe_lists.values_list("id", flat=True))

    favourites = RecipeList.get_favourites()
    is_favourite = RecipeListItem.objects.filter(recipe=recipe, recipe_list=favourites).exists()

    # Context-aware navigation
    nav_context = request.GET.get("context", "book")
    previous_recipe = None
    next_recipe = None
    context_params = ""
    breadcrumb_context = None

    if nav_context == "list":
        # Navigate within a recipe list
        list_id = request.GET.get("list_id")
        if list_id:
            try:
                recipe_list = RecipeList.objects.get(id=list_id)
                # Get ordered recipe IDs in this list
                list_items = (
                    RecipeListItem.objects.filter(recipe_list=recipe_list)
                    .select_related("recipe")
                    .order_by("id")
                )
                recipe_ids = [item.recipe_id for item in list_items]

                if recipe.id in recipe_ids:
                    idx = recipe_ids.index(recipe.id)
                    if idx > 0:
                        previous_recipe = Recipe.objects.get(id=recipe_ids[idx - 1])
                    if idx < len(recipe_ids) - 1:
                        next_recipe = Recipe.objects.get(id=recipe_ids[idx + 1])

                context_params = f"context=list&list_id={list_id}"
                breadcrumb_context = {
                    "type": "list",
                    "list": recipe_list,
                }
            except RecipeList.DoesNotExist:
                # Fall back to book context
                nav_context = "book"

    elif nav_context == "search":
        # Navigate within search results - rebuild the query using unified filter format
        search = request.GET.get("q", "")
        selected_lists = request.GET.getlist("selected_lists[]")
        sort_by = request.GET.get("sort", "name")
        group_logic = request.GET.get("group_logic", "and")

        # Advanced filter params (unified format used by both recipes and search pages)
        filter_fields = request.GET.getlist("filter_field[]")
        filter_ops = request.GET.getlist("filter_op[]")
        filter_values = request.GET.getlist("filter_value[]")
        filter_groups = request.GET.getlist("filter_group[]")
        filter_logics = request.GET.getlist("filter_logic[]")

        # Rebuild the recipe queryset
        recipes_qs = Recipe.objects.select_related("book").prefetch_related("keywords").all()

        # Apply quick search
        if search:
            recipes_qs = recipes_qs.filter(
                Q(name__icontains=search)
                | Q(ingredients__icontains=search)
                | Q(instructions__icontains=search)
                | Q(keywords__name__icontains=search)
                | Q(book__author__icontains=search)
                | Q(book__title__icontains=search)
            ).distinct()

        # Apply list filter (still passed separately)
        if selected_lists:
            recipes_qs = recipes_qs.filter(recipe_lists__id__in=selected_lists).distinct()

        # Apply advanced filter groups
        if filter_fields and filter_values:
            m2m_fields = {f.name for f in Recipe._meta.get_fields() if f.many_to_many}

            field_map = {
                f.name: f.name
                for f in Recipe._meta.get_fields()
                if hasattr(f, "get_internal_type") and f.get_internal_type() == "TextField"
            }
            for f in Recipe._meta.get_fields():
                if f.many_to_many:
                    field_map[f.name] = f"{f.name}__name"
            field_map.update(
                {
                    "author": "book__author",
                    "book": "book__title",
                }
            )

            def apply_condition(field, op, value):
                db_field = field_map.get(field, field)
                if op == "contains":
                    return Q(**{f"{db_field}__icontains": value})
                elif op == "not_contains":
                    return ~Q(**{f"{db_field}__icontains": value})
                elif op == "equals":
                    return Q(**{f"{db_field}__iexact": value})
                elif op == "starts":
                    return Q(**{f"{db_field}__istartswith": value})
                return Q()

            def is_positive_m2m_condition(condition):
                return condition["field"] in m2m_fields and condition["op"] in (
                    "contains",
                    "equals",
                    "starts",
                )

            groups_dict = {}
            for field, op, value, group_idx, logic in zip(
                filter_fields, filter_ops, filter_values, filter_groups, filter_logics, strict=False
            ):
                if value.strip():
                    group_key = int(group_idx) if group_idx.isdigit() else 0
                    if group_key not in groups_dict:
                        groups_dict[group_key] = {"logic": logic, "conditions": []}
                    groups_dict[group_key]["conditions"].append(
                        {"field": field, "op": op, "value": value.strip()}
                    )

            if groups_dict:
                group_queries = []
                chained_m2m_filters = []

                for group in [groups_dict[k] for k in sorted(groups_dict.keys())]:
                    if group["logic"] == "and":
                        # Separate M2M positive conditions for chaining
                        m2m_conditions = [
                            c for c in group["conditions"] if is_positive_m2m_condition(c)
                        ]
                        other_conditions = [
                            c for c in group["conditions"] if not is_positive_m2m_condition(c)
                        ]

                        group_q = Q()
                        for condition in other_conditions:
                            cond_q = apply_condition(
                                condition["field"], condition["op"], condition["value"]
                            )
                            group_q &= cond_q

                        for condition in m2m_conditions:
                            chained_m2m_filters.append(
                                apply_condition(
                                    condition["field"], condition["op"], condition["value"]
                                )
                            )

                        if group_q:
                            group_queries.append(group_q)
                    else:
                        # OR logic: combine all conditions
                        group_q = Q()
                        for condition in group["conditions"]:
                            cond_q = apply_condition(
                                condition["field"], condition["op"], condition["value"]
                            )
                            group_q |= cond_q
                        if group_q:
                            group_queries.append(group_q)

                if group_queries:
                    final_filter_q = group_queries[0]
                    for gq in group_queries[1:]:
                        if group_logic == "and":
                            final_filter_q &= gq
                        else:
                            final_filter_q |= gq
                    recipes_qs = recipes_qs.filter(final_filter_q)

                # Chain M2M filters for proper AND semantics
                for m2m_q in chained_m2m_filters:
                    recipes_qs = recipes_qs.filter(m2m_q)

                recipes_qs = recipes_qs.distinct()

        # Apply sorting
        if sort_by == "name":
            recipes_qs = recipes_qs.order_by("name")
        elif sort_by == "book":
            recipes_qs = recipes_qs.order_by("book__title", "order")
        elif sort_by == "author":
            recipes_qs = recipes_qs.order_by("book__author", "book__title", "order")
        elif sort_by == "order":
            recipes_qs = recipes_qs.order_by("book", "order")
        elif sort_by == "recent":
            recipes_qs = recipes_qs.order_by("-created_at")
        elif sort_by == "list_order" and len(selected_lists) == 1:
            recipes_qs = recipes_qs.order_by("list_items__id")
        elif sort_by == "relevance":
            recipes_qs = recipes_qs.order_by("name")
        else:
            # Random sort or invalid - can't reliably navigate, fall back to book
            nav_context = "book"
            recipes_qs = None

        if recipes_qs is not None:
            recipe_ids = list(recipes_qs.values_list("id", flat=True))

            if recipe.id in recipe_ids:
                idx = recipe_ids.index(recipe.id)
                if idx > 0:
                    previous_recipe = Recipe.objects.get(id=recipe_ids[idx - 1])
                if idx < len(recipe_ids) - 1:
                    next_recipe = Recipe.objects.get(id=recipe_ids[idx + 1])

            # Build context params for navigation links (unified format)
            params = ["context=search"]
            if search:
                params.append(f"q={search}")
            if sort_by:
                params.append(f"sort={sort_by}")
            if group_logic:
                params.append(f"group_logic={group_logic}")
            for list_id in selected_lists:
                params.append(f"selected_lists[]={list_id}")
            for field, op, value, group_idx, logic in zip(
                filter_fields, filter_ops, filter_values, filter_groups, filter_logics, strict=False
            ):
                if value.strip():
                    params.append(f"filter_field[]={field}")
                    params.append(f"filter_op[]={op}")
                    params.append(f"filter_value[]={value}")
                    params.append(f"filter_group[]={group_idx}")
                    params.append(f"filter_logic[]={logic}")
            context_params = "&".join(params)

            breadcrumb_context = {
                "type": "search",
            }

    # Default to book context
    if nav_context == "book" or (
        previous_recipe is None and next_recipe is None and nav_context != "list"
    ):
        if nav_context == "book":
            previous_recipe = recipe.get_previous_in_book()
            next_recipe = recipe.get_next_in_book()
            context_params = "context=book"
            breadcrumb_context = {
                "type": "book",
                "book": recipe.book,
            }

    template_context = {
        "recipe": recipe,
        "book": recipe.book,
        "previous_recipe": previous_recipe,
        "next_recipe": next_recipe,
        "recipe_lists": recipe_lists,
        "available_lists": available_lists,
        "form": form,
        "is_favourite": is_favourite,
        "favourites_list": favourites,
        "nav_context": nav_context,
        "context_params": context_params,
        "breadcrumb_context": breadcrumb_context,
    }

    if request.headers.get("HX-Request"):
        return render(request, "core/recipe_detail_content.html", template_context)

    return render(request, "core/recipe_detail.html", template_context)


def toggle_favourite(request, recipe_id):
    if request.method == "POST":
        recipe = get_object_or_404(Recipe, id=recipe_id)
        favourites = RecipeList.get_favourites()

        existing = RecipeListItem.objects.filter(recipe=recipe, recipe_list=favourites).first()
        if existing:
            existing.delete()
            is_favourite = False
        else:
            RecipeListItem.objects.create(recipe=recipe, recipe_list=favourites)
            is_favourite = True

        if request.headers.get("HX-Request"):
            return render(
                request,
                "core/partials/favourite_button.html",
                {
                    "recipe": recipe,
                    "is_favourite": is_favourite,
                },
            )

        return redirect("recipe_detail", recipe_id=recipe_id)

    return redirect("recipe_detail", recipe_id=recipe_id)


def delete_recipe(request, recipe_id):
    if request.method == "POST":
        recipe = get_object_or_404(Recipe, id=recipe_id)
        book_id = recipe.book.id
        recipe_name = recipe.name
        recipe.delete()
        messages.success(request, f'Deleted recipe "{recipe_name}".')
        return redirect("book_detail", book_id=book_id)
    return redirect("recipe_detail", recipe_id=recipe_id)


def clear_recipe_image(request, recipe_id):
    if request.method == "POST":
        recipe = get_object_or_404(Recipe, id=recipe_id)
        recipe.image = ""
        recipe.save()
        messages.success(request, "Image removed from recipe.")
    return redirect("recipe_detail", recipe_id=recipe_id)


def recipe_lists(request):
    lists = RecipeList.objects.annotate(recipe_count=Count("recipes")).all()

    search = request.GET.get("search", "")
    if search:
        lists = lists.filter(name__icontains=search)

    context = {
        "lists": lists,
        "search": search,
    }

    return render(request, "core/recipe_lists.html", context)


def recipe_list_detail(request, list_id):
    get_object_or_404(RecipeList, id=list_id)
    return redirect(f"/recipes/?list={list_id}")


def create_recipe_list(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()

        if name:
            recipe_list = RecipeList.objects.create(name=name)
            messages.success(request, f'Created list "{recipe_list.name}"')
            return redirect("recipe_list_detail", list_id=recipe_list.id)
        else:
            messages.error(request, "List name is required")

    return redirect("recipe_lists")


def create_list_and_add_recipe(request, recipe_id):
    if request.method == "POST":
        recipe = get_object_or_404(Recipe, id=recipe_id)
        name = request.POST.get("name", "").strip()

        if name:
            recipe_list = RecipeList.objects.create(name=name)
            RecipeListItem.objects.create(recipe=recipe, recipe_list=recipe_list)
            messages.success(
                request, f'Created list "{recipe_list.name}" and added "{recipe.name}"'
            )
        else:
            messages.error(request, "List name is required")

    return redirect(request.META.get("HTTP_REFERER", "recipe_detail"), recipe_id=recipe_id)


def add_recipe_to_list(request, recipe_id, list_id):
    if request.method == "POST":
        recipe = get_object_or_404(Recipe, id=recipe_id)
        recipe_list = get_object_or_404(RecipeList, id=list_id)

        _, created = RecipeListItem.objects.get_or_create(recipe=recipe, recipe_list=recipe_list)

        if created:
            messages.success(request, f'Added "{recipe.name}" to "{recipe_list.name}"')
        else:
            messages.info(request, f'"{recipe.name}" is already in "{recipe_list.name}"')

    return redirect(request.META.get("HTTP_REFERER", "recipe_lists"))


def remove_recipe_from_list(request, recipe_id, list_id):
    if request.method == "POST":
        recipe = get_object_or_404(Recipe, id=recipe_id)
        recipe_list = get_object_or_404(RecipeList, id=list_id)

        deleted_count, _ = RecipeListItem.objects.filter(
            recipe=recipe, recipe_list=recipe_list
        ).delete()

        if deleted_count > 0:
            messages.success(request, f'Removed "{recipe.name}" from "{recipe_list.name}"')
        else:
            messages.warning(request, f'"{recipe.name}" was not in "{recipe_list.name}"')

    return redirect(request.META.get("HTTP_REFERER", "recipe_lists"))


def delete_recipe_list(request, list_id):
    if request.method == "POST":
        recipe_list = get_object_or_404(RecipeList, id=list_id)
        list_name = recipe_list.name
        recipe_list.delete()
        messages.success(request, f'Deleted list "{list_name}"')

    return redirect("recipe_lists")


def tasks(request):
    books = Book.objects.all().order_by("title")
    books_with_recipes = Book.objects.annotate(recipe_count=Count("recipes")).filter(
        recipe_count__gt=0
    )

    context = {
        "books": books,
        "books_with_recipes": books_with_recipes,
    }

    return render(request, "core/tasks.html", context)


def queue_load_books_from_calibre(request):
    if request.method == "POST":
        try:
            async_task("core.tasks.load_books_from_calibre_task")
            messages.success(request, "Load books task has been queued successfully.")
        except Exception as e:
            messages.error(request, f"Error queuing load books task: {e!s}")

        return redirect("tasks")

    return redirect("tasks")


def queue_deduplicate_keywords(request):
    if request.method == "POST":
        try:
            async_task("core.tasks.deduplicate_keywords_task")
            messages.success(request, "Deduplicate keywords task has been queued successfully.")
        except Exception as e:
            messages.error(request, f"Error queuing deduplicate keywords task: {e!s}")

        return redirect("tasks")

    return redirect("tasks")


def queue_all_books_for_recipe_extraction(request):
    if request.method == "POST":
        extraction_method = request.POST.get("extraction_method", None)
        config = Config.get_solo()

        books = Book.objects.all().order_by("-calibre_id")
        count = books.count()
        for book in books:
            existing = book.extraction_reports.filter(started_at__isnull=True).exists()
            if not existing:
                extraction = ExtractionReport.objects.create(
                    book=book,
                    provider_name=config.ai_provider,
                    extraction_method=extraction_method,
                )
                async_task(
                    "core.tasks.extract_recipes_from_book",
                    book.id,
                    str(extraction.id),
                    group="queue_all_extractions",
                )
            else:
                queued = book.extraction_reports.filter(started_at__isnull=True).first()
                if queued:
                    async_task(
                        "core.tasks.extract_recipes_from_book",
                        book.id,
                        str(queued.id),
                        group="queue_all_extractions",
                    )
                else:
                    async_task(
                        "core.tasks.extract_recipes_from_book",
                        book.id,
                        group="queue_all_extractions",
                    )

        messages.success(request, f"Queued {count} books for extraction.")
        return redirect("tasks")

    return redirect("tasks")


def queue_random_books_for_recipe_extraction(request):
    if request.method == "POST":
        try:
            count = int(request.POST.get("count", 10))
        except ValueError:
            count = 10

        extraction_method = request.POST.get("extraction_method", None)
        count = max(1, min(count, 1000))
        all_books = list(
            Book.objects.annotate(recipe_count=Count("recipes")).filter(recipe_count=0)
        )
        if not all_books:
            messages.warning(request, "No books found to queue for extraction.")
            return redirect("tasks")

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
                async_task(
                    "core.tasks.extract_recipes_from_book",
                    book.id,
                    str(extraction.id),
                    group="queue_random_extractions",
                )
            else:
                queued = book.extraction_reports.filter(started_at__isnull=True).first()
                if queued:
                    async_task(
                        "core.tasks.extract_recipes_from_book",
                        book.id,
                        str(queued.id),
                        group="queue_random_extractions",
                    )
                else:
                    async_task(
                        "core.tasks.extract_recipes_from_book",
                        book.id,
                        group="queue_random_extractions",
                    )

        messages.success(request, f"Queued {len(chosen)} random books for extraction.")
        return redirect("tasks")

    return redirect("tasks")


def config(request):
    config_obj = Config.get_solo()

    if request.method == "POST":
        form = ConfigForm(request.POST, instance=config_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Configuration saved successfully.")
            return redirect("config")
    else:
        form = ConfigForm(instance=config_obj)

    context = {
        "form": form,
        "config": config_obj,
    }
    return render(request, "core/config.html", context)


def extraction_reports(request):
    total_books = Book.objects.count()
    total_recipes = Recipe.objects.count()
    processed_books = (
        Book.objects.annotate(recipe_count=Count("recipes")).filter(recipe_count__gt=0).count()
    )

    fourteen_days_ago = now() - timedelta(days=14)

    # Annotate extraction reports with image count
    extraction_reports = (
        ExtractionReport.objects.select_related("book")
        .filter(created_at__gte=fourteen_days_ago)
        .annotate(
            image_count=Count(
                "book__recipes",
                filter=Q(book__recipes__image__isnull=False) & ~Q(book__recipes__image=""),
            )
        )
        .order_by("-completed_at")[:100]
    )

    # Calculate total cost from extraction reports
    total_cost = (
        ExtractionReport.objects.filter(
            created_at__gte=fourteen_days_ago, cost_usd__isnull=False
        ).aggregate(Sum("cost_usd"))["cost_usd__sum"]
        or 0
    )

    config = Config.get_solo()

    context = {
        "total_books": total_books,
        "total_recipes": total_recipes,
        "processed_books": processed_books,
        "total_cost": round(float(total_cost), 2),
        "extraction_reports": extraction_reports,
        "config": config,
    }
    return render(request, "core/extraction_reports.html", context)


def get_recipe_image(request, book_id, image_path):
    book = get_object_or_404(Book, pk=book_id)
    epub_path = book.get_epub_path()

    if not epub_path or not epub_path.exists():
        raise Http404("EPUB file not found.")

    try:
        with zipfile.ZipFile(epub_path, "r") as epub:
            image_data = epub.read(image_path)
            return HttpResponse(image_data, content_type="image/jpeg")
    except KeyError:
        raise Http404(f"Image '{image_path}' not found in EPUB.")


def ai_search(request):
    try:
        data = json.loads(request.body)
        prompt = data.get("prompt", "").strip()
        limit = data.get("limit", 1000)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not prompt:
        return JsonResponse({"error": "Prompt is required"}, status=400)

    try:
        recipes = vector_search_recipes(prompt, limit=limit)
        recipe_ids = [str(r.id) for r in recipes]
        return JsonResponse({"recipe_ids": recipe_ids})
    except Exception as e:
        logger.exception("Vector search failed")
        return JsonResponse(
            {"error": f"AI search failed: {e!s}"},
            status=500,
        )


def resume_extraction(request, report_id):
    if request.method != "POST":
        return redirect("extraction_reports")

    report = get_object_or_404(ExtractionReport, id=report_id)

    if report.status != "review":
        messages.warning(request, "This extraction is not awaiting review.")
        return redirect("extraction_reports")

    human_response = request.POST.get("response")

    if human_response not in ["has_images", "no_images"]:
        messages.error(request, "Invalid response.")
        return redirect("extraction_reports")

    try:
        graph_config = {"configurable": {"thread_id": report.thread_id}}

        extraction_app.update_state(
            graph_config, {"human_response": human_response}, as_node="await_human"
        )

        result = extraction_app.invoke(input=None, config=graph_config)

        report.refresh_from_db()

        if report.status == "done":
            book = Book.objects.get(id=report.book_id)
            raw_recipes = result.get("raw_recipes", [])
            created_count = save_recipes_from_graph_state(book, report, raw_recipes)
            messages.success(
                request, f"Extraction resumed and completed. Saved {created_count} recipes."
            )
        else:
            messages.info(request, f"Extraction resumed with status: {report.status}")

    except Exception as e:
        logger.error(f"Error resuming extraction: {e}")
        messages.error(request, f"Error resuming extraction: {e}")

    return redirect("extraction_reports")
