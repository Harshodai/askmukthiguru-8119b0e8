"""Notebook router — study notebooks REST API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.dependencies import ServiceContainer, get_container
from services.auth_service import get_current_user_from_supabase

router = APIRouter(tags=["Notebooks"])


class CreateNotebookRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be empty or whitespace only")
        return v


class NotebookItemRequest(BaseModel):
    query: str = Field(..., max_length=10000)
    answer: str = Field(..., max_length=50000)
    citations: list[dict] = []
    source_episode_id: Optional[str] = None


@router.post("/notebooks")
async def create_notebook(
    body: CreateNotebookRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    svc = getattr(container, "notebook_service", None)
    if not svc or not svc.available:
        raise HTTPException(status_code=503, detail="Notebooks are not available at this time.")
    result = await svc.create(user["id"], body.title)
    if not result:
        raise HTTPException(status_code=500, detail="Could not create notebook. Please try again.")
    return result


@router.get("/notebooks")
async def list_notebooks(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    svc = getattr(container, "notebook_service", None)
    if not svc or not svc.available:
        raise HTTPException(status_code=503, detail="Notebooks are not available at this time.")
    return await svc.list(user["id"])


@router.delete("/notebooks/{notebook_id}")
async def delete_notebook(
    notebook_id: str,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    svc = getattr(container, "notebook_service", None)
    if not svc or not svc.available:
        raise HTTPException(status_code=503, detail="Notebooks are not available at this time.")
    if await svc.delete(user["id"], notebook_id):
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Notebook not found")


@router.post("/notebooks/{notebook_id}/items")
async def add_item(
    notebook_id: str,
    body: NotebookItemRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    svc = getattr(container, "notebook_service", None)
    if not svc or not svc.available:
        raise HTTPException(status_code=503, detail="Notebooks are not available at this time.")
    result = await svc.add_item(
        user["id"], notebook_id, body.query, body.answer, body.citations, body.source_episode_id
    )
    if not result:
        raise HTTPException(status_code=500, detail="Could not add item. Please try again.")
    return result


@router.get("/notebooks/{notebook_id}/items")
async def list_items(
    notebook_id: str,
    limit: int = 50,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    svc = getattr(container, "notebook_service", None)
    if not svc or not svc.available:
        raise HTTPException(status_code=503, detail="Notebooks are not available at this time.")
    return await svc.list_items(user["id"], notebook_id, limit=limit)
