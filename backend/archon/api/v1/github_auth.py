import httpx
import structlog
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from archon.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter()

GITHUB_OAUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"


@router.get("/auth/github")
async def github_login():
    """Redirect browser to GitHub OAuth consent page."""
    if not settings.GITHUB_CLIENT_ID:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured (missing GITHUB_CLIENT_ID)")

    params = (
        f"client_id={settings.GITHUB_CLIENT_ID}"
        f"&scope=repo,read:user"
        f"&allow_signup=true"
    )
    return RedirectResponse(url=f"{GITHUB_OAUTH_URL}?{params}")


@router.get("/auth/github/callback")
async def github_callback(code: str = Query(...)):
    """Exchange GitHub OAuth code for an access token and redirect to frontend."""
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )

    if resp.status_code != 200:
        logger.error("github_token_exchange_failed", status=resp.status_code, body=resp.text)
        frontend_error = f"{settings.FRONTEND_URL}/repositories?github_error=token_exchange_failed"
        return RedirectResponse(url=frontend_error)

    data = resp.json()
    access_token = data.get("access_token")

    if not access_token:
        logger.error("github_no_access_token", response=data)
        frontend_error = f"{settings.FRONTEND_URL}/repositories?github_error=no_token"
        return RedirectResponse(url=frontend_error)

    # Redirect to frontend with token — stored client-side in localStorage
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/repositories?github_token={access_token}"
    )


@router.get("/github/repos")
async def list_github_repos(
    token: str = Query(..., description="GitHub OAuth access token"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
):
    """
    List authenticated user's GitHub repositories (including private).
    Returns repos sorted by most recently updated.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{GITHUB_API_URL}/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={
                "sort": "updated",
                "direction": "desc",
                "per_page": per_page,
                "page": page,
                "affiliation": "owner,collaborator,organization_member",
            },
        )

    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired GitHub token")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {resp.status_code}")

    repos = resp.json()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "full_name": r["full_name"],
            "description": r.get("description") or "",
            "private": r["private"],
            "language": r.get("language") or "Unknown",
            "clone_url": r["clone_url"],
            "html_url": r["html_url"],
            "updated_at": r.get("updated_at"),
            "stargazers_count": r.get("stargazers_count", 0),
            "default_branch": r.get("default_branch", "main"),
        }
        for r in repos
    ]
