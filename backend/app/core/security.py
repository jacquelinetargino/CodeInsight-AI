import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet
from itsdangerous import BadSignature, URLSafeTimedSerializer
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


# --- Redefinição de senha -------------------------------------------------------
#
# Token assinado (HMAC com o JWT_SECRET), não guardado no banco. Leva o id do
# usuário e uma impressão do hash de senha atual: trocar a senha muda o hash, e
# todo link emitido antes deixa de valer. É isso que torna o link de uso único
# sem precisar de tabela nem migration.
_RESET_SALT = "password-reset"


def _reset_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.jwt_secret, salt=_RESET_SALT)


def _password_fingerprint(hashed_password: str) -> str:
    return hashlib.sha256(hashed_password.encode()).hexdigest()[:16]


def create_password_reset_token(user_id: str, hashed_password: str) -> str:
    return _reset_serializer().dumps({"sub": user_id, "pw": _password_fingerprint(hashed_password)})


def read_password_reset_token(token: str) -> tuple[str, str] | None:
    """`(user_id, impressão_da_senha)` se a assinatura confere e o prazo não
    venceu; `None` em qualquer outro caso — quem chama não precisa distinguir."""
    max_age = settings.password_reset_expire_minutes * 60
    try:
        data = _reset_serializer().loads(token, max_age=max_age)
    except BadSignature:  # SignatureExpired é subclasse
        return None
    if not isinstance(data, dict):
        return None
    sub, pw = data.get("sub"), data.get("pw")
    if not isinstance(sub, str) or not isinstance(pw, str):
        return None
    return sub, pw


def password_fingerprint_matches(fingerprint: str, hashed_password: str) -> bool:
    return hmac.compare_digest(fingerprint, _password_fingerprint(hashed_password))
