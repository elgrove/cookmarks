"""Recipe queryset building shared between list and detail navigation."""

from typing import Literal

from django.db.models import Q, QuerySet

from core.models import Recipe

M2M_FIELDS = {f.name for f in Recipe._meta.get_fields() if f.many_to_many}


def _field_map() -> dict[str, str]:
    m = {
        f.name: f.name
        for f in Recipe._meta.get_fields()
        if hasattr(f, "get_internal_type") and f.get_internal_type() == "TextField"
    }
    for f in Recipe._meta.get_fields():
        if f.many_to_many:
            m[f.name] = f"{f.name}__name"
    m.update({"author": "book__author", "book": "book__title"})
    return m


FIELD_MAP = _field_map()


def _apply_condition(field: str, op: str, value: str) -> Q:
    db_field = FIELD_MAP.get(field, field)
    if op == "contains":
        return Q(**{f"{db_field}__icontains": value})
    if op == "not_contains":
        return ~Q(**{f"{db_field}__icontains": value})
    if op == "equals":
        return Q(**{f"{db_field}__iexact": value})
    if op == "starts":
        return Q(**{f"{db_field}__istartswith": value})
    return Q()


def _is_positive_m2m(condition: dict) -> bool:
    return condition["field"] in M2M_FIELDS and condition["op"] in (
        "contains",
        "equals",
        "starts",
    )


def build_recipe_queryset(
    *,
    q: str = "",
    book_id=None,
    selected_lists: list | None = None,
    selected_keywords: list[str] | None = None,
    filters: list[dict] | None = None,
    group_logic: Literal["and", "or"] = "or",
    vector_search_ids: list[str] | None = None,
    sort: str = "",
) -> tuple[QuerySet | list, bool]:
    """Return (queryset_or_list, has_searched).

    Mirrors the search logic in the legacy recipes view. Returns a list when
    ordering by vector relevance (because relevance is computed in Python).
    """
    qs = Recipe.objects.select_related("book").prefetch_related("keywords").all()
    selected_lists = selected_lists or []
    selected_keywords = selected_keywords or []
    filters = filters or []
    has_searched = False

    if book_id:
        qs = qs.filter(book_id=book_id)
        has_searched = True

    if selected_keywords:
        for keyword_name in selected_keywords:
            qs = qs.filter(keywords__name__iexact=keyword_name)
        has_searched = True

    combined_q = Q()
    chained_m2m: list[Q] = []
    any_search = False

    if q:
        any_search = True
        has_searched = True
        combined_q &= (
            Q(name__icontains=q)
            | Q(ingredients__icontains=q)
            | Q(instructions__icontains=q)
            | Q(keywords__name__icontains=q)
            | Q(book__author__icontains=q)
            | Q(book__title__icontains=q)
        )

    if selected_lists:
        has_searched = True
        any_search = True
        qs = qs.filter(recipe_lists__id__in=selected_lists)

    if filters:
        # Group conditions by `group` index
        has_searched = True
        any_search = True
        groups: dict[int, dict] = {}
        for cond in filters:
            value = (cond.get("value") or "").strip()
            if not value:
                continue
            group_key = int(cond.get("group") or 0)
            if group_key not in groups:
                groups[group_key] = {"logic": cond.get("logic", "or"), "conditions": []}
            groups[group_key]["conditions"].append(
                {"field": cond["field"], "op": cond.get("op", "contains"), "value": value}
            )

        group_qs: list[Q] = []
        for group in (groups[k] for k in sorted(groups)):
            if group["logic"] == "and":
                m2m_conds = [c for c in group["conditions"] if _is_positive_m2m(c)]
                other_conds = [c for c in group["conditions"] if not _is_positive_m2m(c)]
                gq = Q()
                for c in other_conds:
                    gq &= _apply_condition(c["field"], c["op"], c["value"])
                for c in m2m_conds:
                    chained_m2m.append(_apply_condition(c["field"], c["op"], c["value"]))
                if gq:
                    group_qs.append(gq)
            else:
                gq = Q()
                for c in group["conditions"]:
                    gq |= _apply_condition(c["field"], c["op"], c["value"])
                if gq:
                    group_qs.append(gq)

        if group_qs:
            final = group_qs[0]
            for gq in group_qs[1:]:
                final = final & gq if group_logic == "and" else final | gq
            combined_q &= final

    if any_search or vector_search_ids:
        qs = qs.filter(combined_q)
        for m2m_q in chained_m2m:
            qs = qs.filter(m2m_q)
        if vector_search_ids:
            qs = qs.filter(id__in=vector_search_ids)
        qs = qs.distinct()

    # Default sort
    if not sort:
        if vector_search_ids:
            sort = "relevance"
        elif book_id:
            sort = "order"
        elif len(selected_lists) == 1:
            sort = "list_order"
        else:
            sort = "recent"

    if sort == "relevance" and vector_search_ids:
        id_to_pos = {vid: idx for idx, vid in enumerate(vector_search_ids)}
        recipes = list(qs)
        recipes.sort(key=lambda r: id_to_pos.get(str(r.id), 9999))
        return recipes, has_searched

    if sort == "name":
        qs = qs.order_by("name")
    elif sort == "recent":
        qs = qs.order_by("-created_at")
    elif sort == "author":
        qs = qs.order_by("book__author", "book__title", "name")
    elif sort == "book":
        qs = qs.order_by("book__title", "order")
    elif sort == "order":
        qs = qs.order_by("book", "order")
    elif sort == "list_order" and len(selected_lists) == 1:
        qs = qs.order_by("list_items__id")
    elif sort == "random":
        qs = qs.order_by("?")
    else:
        qs = qs.order_by("name")

    return qs, has_searched
