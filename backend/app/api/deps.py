import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Não autenticado")

    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido ou expirado")

    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido") from exc

    user = await UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário não encontrado ou inativo")
    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """O usuário do Bearer, ou `None` sem token ou com token inválido — para
    rotas que funcionam anônimas e mudam de comportamento quando há sessão."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
