import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    dummy_password_hash,
    hash_password,
    password_fingerprint_matches,
    read_password_reset_token,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserRead,
)
from app.services.email_service import send_password_reset_email

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


# Mesma resposta exista ou não a conta: diferenciar transformaria a rota num
# oráculo de "este e-mail tem cadastro" — o mesmo cuidado do login.
FORGOT_PASSWORD_MESSAGE = (
    "Se houver uma conta com este e-mail, enviamos um link para redefinir a senha."
)
INVALID_RESET_LINK_MESSAGE = "Link inválido ou expirado. Peça um novo."


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    if not settings.email_configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "A recuperação de senha por e-mail não está configurada neste servidor.",
        )

    user = await UserRepository(db).get_by_email(payload.email)
    if user is not None and user.is_active:
        token = create_password_reset_token(str(user.id), user.hashed_password)
        reset_url = f"{settings.public_frontend_url}/reset-password?token={token}"
        # Em segundo plano: o tempo de resposta não pode depender de haver
        # e-mail para enviar, nem a resposta de o provedor aceitar o envio.
        background_tasks.add_task(
            send_password_reset_email, to=user.email, username=user.username, reset_url=reset_url
        )

    return {"message": FORGOT_PASSWORD_MESSAGE}


@router.post("/reset-password")
@limiter.limit("10/minute")
async def reset_password(
    request: Request, payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    lido = read_password_reset_token(payload.token)
    if lido is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_RESET_LINK_MESSAGE)
    user_id, fingerprint = lido

    try:
        user = await UserRepository(db).get_by_id(uuid.UUID(user_id))
    except ValueError:
        user = None
    # A impressão da senha no token só confere com o hash ATUAL: depois de uma
    # redefinição, o mesmo link (ou qualquer outro emitido antes) não vale mais.
    if (
        user is None
        or not user.is_active
        or not password_fingerprint_matches(fingerprint, user.hashed_password)
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_RESET_LINK_MESSAGE)

    user.hashed_password = hash_password(payload.new_password)
    await db.commit()
    return {"message": "Senha redefinida. Entre com a nova senha."}


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
