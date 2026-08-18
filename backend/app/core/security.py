import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
_fernet = Fernet(settings.encryption_key.encode())
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw_password: str) -> str:
    return _pwd_context.hash(raw_password)


def verify_password(raw_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(raw_password, hashed_password)


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """Hash de uma senha aleatória, para conferir contra quando o e-mail não
    existe.

    Sem isso o tempo de resposta do login separa os dois casos: medido, e-mail
    cadastrado respondia em 213 ms (o custo do bcrypt) e e-mail desconhecido em
    0,9 ms, porque o `or` curto-circuitava antes do `verify_password`. Uma
    diferença de 236× é medida pela rede sem esforço nenhum, e transforma o
    login num oráculo de "esta pessoa tem conta aqui".

    A senha é sorteada em vez de fixa para que nenhuma entrada faça o
    `verify_password` retornar verdadeiro por acidente. O hash é calculado uma
    vez por processo (é caro de propósito) e reaproveitado.
    """
    return hash_password(secrets.token_urlsafe(32))


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def encrypt_secret(raw: str) -> str:
    return _fernet.encrypt(raw.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet.decrypt(token.encode()).decode()
