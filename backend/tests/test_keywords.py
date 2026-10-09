from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.recipe import Keyword
from app.services.keywords import get_or_create_keyword, get_or_create_keywords


def test_keyword_model_normalises_case_and_whitespace() -> None:
    keyword = Keyword(name="  Crème   BRÛLÉE  ")

    assert keyword.name == "crème brûlée"


def test_get_or_create_keyword_reuses_the_normalised_identity(session: Session) -> None:
    first = get_or_create_keyword(session, "  Spring   Onion ")
    second = get_or_create_keyword(session, "SPRING ONION")

    assert first is second
    assert first.name == "spring onion"
    assert session.scalar(select(func.count()).select_from(Keyword)) == 4


def test_get_or_create_keywords_drops_normalised_duplicates(session: Session) -> None:
    keywords = get_or_create_keywords(
        session,
        ["Spring Onion", " spring   onion ", "SPRING ONION"],
    )

    assert [keyword.name for keyword in keywords] == ["spring onion"]


def test_keyword_filter_accepts_legacy_mixed_case_links(client: TestClient) -> None:
    response = client.get("/api/recipes", params={"keyword": "PASTA"})

    assert response.status_code == 200
    assert response.json()["total"] == 1
