from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import (
    create_access_token,
    dummy_password_hash,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import TokenResponse, UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request, payload: UserCreate, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
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
@limiter.limit("10/minute")
async def login(
    request: Request, payload: UserLogin, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    users = UserRepository(db)
    user = await users.get_by_email(payload.email)

    # A conferência acontece nos dois casos, inclusive quando o e-mail não
    # existe: o custo do bcrypt é o que iguala os tempos de resposta. Escrever
    # `user is None or not verify_password(...)` curto-circuitava e devolvia o
    # 401 do e-mail desconhecido em 0,9 ms contra 213 ms do cadastrado — ver
    # `dummy_password_hash`.
    hash_conferido = user.hashed_password if user is not None else dummy_password_hash()
    senha_confere = verify_password(payload.password, hash_conferido)

    if user is None or not senha_confere:
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
