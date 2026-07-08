from typing import Optional

from pydantic import BaseModel, EmailStr

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/waitlist", tags=["Waitlist"])


class WaitlistSignup(BaseModel):
    email: EmailStr
    name: Optional[str] = None


class WaitlistResponse(BaseModel):
    message: str


@router.post("/", response_model=WaitlistResponse, status_code=501)
async def signup_waitlist(payload: WaitlistSignup):
    """Placeholder — waitlist signup is a future feature.

    Accepts email and optional name but returns 501 Not Implemented.
    """
    raise HTTPException(
        status_code=501,
        detail={
            "message": "Waitlist feature not yet implemented.",
            "hint": "See docs/marketing_strategy.md for future plans.",
        },
    )


if __name__ == "__main__":
    print("Waitlist endpoint stub — POST /api/waitlist")
    print("Returns 501 Not Implemented.")
