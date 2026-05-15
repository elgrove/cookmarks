from django.db.models import Count
from ninja import Router

from core.api.schemas import KeywordOut
from core.models import Keyword

router = Router()


@router.get("", response=list[KeywordOut])
def list_keywords(request):
    qs = Keyword.objects.annotate(recipe_count=Count("recipes")).order_by("-recipe_count")
    return [{"id": k.id, "name": k.name, "recipe_count": k.recipe_count} for k in qs]
