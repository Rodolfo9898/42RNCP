"""POST /reviews: the one-click review, a headless claude on a sanitized copy."""

from fastapi import APIRouter, HTTPException, Request

from terminal.claude.headless import HeadlessReview, ReviewFailed


def review_router(review: HeadlessReview) -> APIRouter:
    router = APIRouter()

    @router.post("/reviews")
    async def run_review(request: Request) -> dict:
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(400, "the body must be JSON") from exc
        try:
            return await review.run(body, request.is_disconnected)
        except ReviewFailed as exc:
            raise HTTPException(exc.status, exc.detail) from exc

    return router
