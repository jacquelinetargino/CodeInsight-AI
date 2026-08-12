from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import TokenResponse, UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    users = UserRepository(db)
    if await users.get_by_email(payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail já cadastrado")

    user = await users.create(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        username=payload.username,
    )
    await db.commit()
    await db.refresh(user)

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=UserRead.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    users = UserRepository(db)
    user = await users.get_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuário desativado")

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=UserRead.model_validate(user))


@router.post("/logout")
async def logout() -> dict:
    # JWT é stateless: não há sessão no servidor para invalidar. "Logout" aqui
    # significa o cliente descartar o token guardado localmente. O endpoint
    # existe por simetria da API (e como ponto de extensão futuro, caso um
    # blocklist de tokens revogados venha a ser necessário).
    return {"ok": True}


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
