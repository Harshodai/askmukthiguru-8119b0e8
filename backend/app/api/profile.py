"""User spiritual profile routes."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import ServiceContainer, get_container
from app.schemas import ProfileUpdate
from services.auth_service import get_current_user_from_supabase
from services.user_profile_service import LanguagePreference, SpiritualLevel

router = APIRouter(tags=["Profile"])


@router.get("/profile")
async def get_profile_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    """Fetch the authenticated user's spiritual profile."""
    if not container.user_profile:
        raise HTTPException(status_code=501, detail="Profile features are not available at this time.")

    profile = await container.user_profile.get_or_create_profile(user["id"])
    return asdict(profile)


@router.put("/profile")
async def update_profile_endpoint(
    profile_data: ProfileUpdate,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    """Update user preferences and spiritual level."""
    if not container.user_profile:
        raise HTTPException(status_code=501, detail="Profile features are not available at this time.")

    profile = await container.user_profile.get_or_create_profile(user["id"])

    if profile_data.preferred_language is not None:
        profile.preferred_language = LanguagePreference(profile_data.preferred_language)
    if profile_data.spiritual_level is not None:
        profile.spiritual_level = SpiritualLevel(profile_data.spiritual_level)
    if profile_data.topics_of_interest is not None:
        profile.topics_of_interest = profile_data.topics_of_interest
    if profile_data.codemix_preference is not None:
        profile.codemix_preference = profile_data.codemix_preference

    await container.user_profile.update_profile(profile)
    return asdict(profile)
