from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.auth import LoginRequest, TokenResponse
from app.api.v1.deps import get_current_user, get_db
from app.core.hash import verify_password
from app.core.security import create_access_token
from app.db.models import User

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(form_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    email = form_data.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email).limit(1))
    account = result.scalar_one_or_none()
    if not account or not verify_password(form_data.password, account.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверные учетные данные")

    token = create_access_token(subject=account.email, extra={"role": str(account.role.value)})
    return TokenResponse(access_token=token)


@router.get("/me")
async def me(user=Depends(get_current_user)):
    """Возвращает минимум данных о текущей сессии (для UI)."""
    return {"email": user.get("sub"), "role": user.get("role")}
