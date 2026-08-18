import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    username: str
    is_active: bool


# O bcrypt só considera os primeiros 72 BYTES da senha e descarta o resto sem
# avisar. Medido: `verify_password("A"*72 + "sufixo-totalmente-diferente", h)`
# casa com o hash de `"A"*72`. O limite anterior de 128 caracteres, então,
# prometia uma força que o algoritmo não entregava — quem escolhesse uma
# frase-senha de 100 caracteres tinha 72 protegendo a conta e 28 decorativos.
#
# São BYTES, não caracteres: uma senha de 40 caracteres acentuados passa de 72
# bytes em UTF-8 e seria truncada do mesmo jeito.
BCRYPT_MAX_PASSWORD_BYTES = 72


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    username: str = Field(min_length=2, max_length=255)

    @field_validator("password")
    @classmethod
    def _cabe_no_bcrypt(cls, v: str) -> str:
        tamanho = len(v.encode("utf-8"))
        if tamanho > BCRYPT_MAX_PASSWORD_BYTES:
            raise ValueError(
                f"A senha passa de {BCRYPT_MAX_PASSWORD_BYTES} bytes "
                f"(esta tem {tamanho}). O algoritmo de hash ignora o que "
                "excede, então aceitar seria prometer uma proteção que não "
                "existe. Use uma senha mais curta — acentos e emoji contam "
                "mais de um byte."
            )
        return v


class UserLogin(BaseModel):
    email: EmailStr
    # Sem o teto de 72 bytes de propósito: contas criadas antes da validação
    # acima podem ter senha mais longa, e recusar aqui as trancaria para fora.
    # O bcrypt trunca na conferência exatamente como truncou no cadastro, então
    # elas continuam entrando. O teto largo existe só para não aceitar corpo de
    # tamanho arbitrário.
    password: str = Field(max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
