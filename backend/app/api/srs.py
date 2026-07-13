"""SRS Spaced Repetition active recall flashcard routes."""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import ServiceContainer, get_container
from services.auth_service import get_current_user_from_supabase
from services.srs_service import SRSService

router = APIRouter(tags=["SRS"])

class ReviewRequest(BaseModel):
    card_id: str
    rating: int

class GenerateRequest(BaseModel):
    notebook_item_id: str
    query: str
    answer: str

@router.get("/srs/due")
async def get_due_cards(
    limit: int = 20,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    """Retrieve due flashcards for the current user."""
    srs_service = SRSService(container.supabase_client, container.ollama)
    return await srs_service.list_due_cards(user["id"], limit=limit)

@router.post("/srs/review")
async def review_card(
    req: ReviewRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    """Submit a card review rating (0-5) to update its SM-2 scheduling."""
    srs_service = SRSService(container.supabase_client, container.ollama)
    card = await srs_service.review_card(req.card_id, req.rating)
    if not card:
        raise HTTPException(status_code=400, detail="Failed to process card review")
    return card

@router.post("/srs/generate")
async def generate_cards(
    req: GenerateRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    """Generate 2 flashcards from a saved study notebook item."""
    srs_service = SRSService(container.supabase_client, container.ollama)
    cards = await srs_service.generate_cards_from_notebook_item(
        user["id"],
        query=req.query,
        answer=req.answer,
        source_id=req.notebook_item_id
    )
    return {"cards_generated": len(cards), "cards": cards}
