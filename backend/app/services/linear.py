import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_API_URL = "https://api.linear.app/graphql"
_TIMEOUT = 15

_ISSUE_CREATE_MUTATION = """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue {
      identifier
      url
    }
  }
}
"""


class LinearError(Exception):
    """Raised when a ticket cannot be filed to Linear."""


def linear_configured() -> bool:
    """Whether a ticket can be filed: an API key and a target team are both set."""
    return bool(settings.linear_api_key and settings.linear_team_id)


def create_issue(title: str, description: str) -> dict[str, str]:
    """Create a Linear issue in the configured project and return its identifier and url.

    Raises LinearError if Linear is not configured or the API call fails.
    """
    if not linear_configured():
        raise LinearError("Linear integration is not configured")

    issue_input: dict[str, str] = {
        "teamId": settings.linear_team_id,
        "title": title,
        "description": description,
    }
    if settings.linear_project_id:
        issue_input["projectId"] = settings.linear_project_id

    try:
        response = httpx.post(
            _API_URL,
            headers={
                "Authorization": settings.linear_api_key,
                "Content-Type": "application/json",
            },
            json={"query": _ISSUE_CREATE_MUTATION, "variables": {"input": issue_input}},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Linear request failed: %s", exc)
        raise LinearError("Could not reach Linear") from exc

    body = response.json()
    if body.get("errors"):
        logger.error("Linear returned errors: %s", body["errors"])
        raise LinearError("Linear rejected the ticket")

    result = body.get("data", {}).get("issueCreate", {})
    if not result.get("success") or not result.get("issue"):
        raise LinearError("Linear did not create the issue")

    return result["issue"]
