"""As rotas de autenticação são as únicas abertas ao público — e não tinham
proteção nenhuma contra abuso.

Três defeitos medidos antes da correção, todos em `POST /auth/login` ou
`POST /auth/register`:

1. **Adivinhação de senha ilimitada.** 60 tentativas seguidas contra a mesma
   conta responderam 401 e nenhuma 429. As duas rotas caras de análise tinham
   limite desde o PR 31; as de autenticação, não.
2. **Oráculo de tempo.** E-mail cadastrado respondia em 213 ms (o custo do
   bcrypt), e-mail desconhecido em 0,9 ms — 236x de diferença, porque o `or`
   curto-circuitava antes de conferir a senha. Dava para descobrir quem tem
   conta sem acertar senha nenhuma.
3. **Senha truncada em silêncio.** O cadastro aceitava até 128 caracteres, mas
   o bcrypt só usa os primeiros 72 bytes: `"A"*72 + qualquer coisa` casava com
   o hash de `"A"*72`.

Cada teste aqui falha se a proteção correspondente for removida.
"""

import statistics
import time

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.security import dummy_password_hash, hash_password, verify_password
from app.models.user import User
from app.schemas.user import BCRYPT_MAX_PASSWORD_BYTES

settings = get_settings()
PREFIX = settings.api_v1_prefix

SENHA_VALIDA = "correct-horse-battery-staple"


# --- 1. limite de taxa --------------------------------------------------------


@pytest.mark.asyncio
async def test_login_e_limitado(client: AsyncClient, test_user):
    """10/minuto por IP. Sem isso, adivinhar senha é só uma questão de tempo."""
    codigos = [
        (
            await client.post(
                f"{PREFIX}/auth/login",
                json={"email": test_user.email, "password": f"tentativa-{i}"},
            )
        ).status_code
        for i in range(13)
    ]

    assert 429 in codigos, f"o limite de 10/minute nunca disparou: {codigos}"
    assert (
        codigos.index(429) >= 10
    ), f"limitou cedo demais, na tentativa {codigos.index(429) + 1}: {codigos}"


@pytest.mark.asyncio
async def test_registro_e_limitado(client: AsyncClient):
    """5/minuto por IP: criar conta é barato para quem abusa e caro para quem
    hospeda (cada uma grava no banco e paga um hash de bcrypt)."""
    codigos = [
        (
            await client.post(
                f"{PREFIX}/auth/register",
                json={
                    "email": f"pessoa{i}@example.com",
                    "password": SENHA_VALIDA,
                    "username": f"pessoa{i}",
                },
            )
        ).status_code
        for i in range(8)
    ]

    assert 429 in codigos, f"o limite de 5/minute nunca disparou: {codigos}"
    assert (
        codigos.index(429) >= 5
    ), f"limitou cedo demais, no registro {codigos.index(429) + 1}: {codigos}"


@pytest.mark.asyncio
async def test_uso_normal_do_login_nao_e_barrado(client: AsyncClient, test_user):
    """A proteção não pode atrapalhar quem erra a senha duas vezes e acerta na
    terceira."""
    for _ in range(2):
        errada = await client.post(
            f"{PREFIX}/auth/login",
            json={"email": test_user.email, "password": "esqueci"},
        )
        assert errada.status_code == 401

    certa = await client.post(
        f"{PREFIX}/auth/login",
        json={"email": test_user.email, "password": SENHA_VALIDA},
    )
    assert certa.status_code == 200, certa.text


# --- 2. oráculo de tempo ------------------------------------------------------


@pytest.mark.asyncio
async def test_login_nao_revela_email_cadastrado_pelo_tempo(client: AsyncClient, test_user):
    """Antes da correção a razão medida entre os dois casos era ~236x. O teto de
    4x aqui é folgado de propósito: o que ele precisa pegar é a volta do
    curto-circuito, que reintroduz uma diferença de duas ordens de grandeza.
    Medir tempo em CI é ruidoso, e um limite apertado viraria teste instável.

    O `dummy_password_hash` é aquecido antes de medir: ele custa um bcrypt
    inteiro na primeira chamada, e essa chamada cairia na primeira amostra.
    """
    dummy_password_hash()

    # Só três amostras de cada: cada uma custa um bcrypt (~210 ms), e o que se
    # mede aqui é diferença de ordem de grandeza, não de poucos por cento.
    async def mediana_ms(email: str) -> float:
        amostras = []
        for _ in range(3):
            inicio = time.perf_counter()
            resposta = await client.post(
                f"{PREFIX}/auth/login",
                json={"email": email, "password": "senha-que-nao-e-a-certa"},
            )
            amostras.append((time.perf_counter() - inicio) * 1000)
            assert resposta.status_code == 401
        return statistics.median(amostras)

    cadastrado = await mediana_ms(test_user.email)
    desconhecido = await mediana_ms("ninguem-tem-esta-conta@example.com")

    razao = max(cadastrado, desconhecido) / max(min(cadastrado, desconhecido), 0.001)
    assert razao < 4, (
        f"o tempo de resposta separa os dois casos: e-mail cadastrado "
        f"{cadastrado:.1f} ms, desconhecido {desconhecido:.1f} ms (razão {razao:.0f}x)"
    )


def test_dummy_hash_e_estavel_e_nao_casa_com_nada():
    """Precisa ser o mesmo hash em todas as chamadas (senão cada login pagaria
    um bcrypt de geração a mais) e não pode validar nenhuma senha."""
    assert dummy_password_hash() == dummy_password_hash()
    assert not verify_password("", dummy_password_hash())
    assert not verify_password(SENHA_VALIDA, dummy_password_hash())


# --- 3. senha truncada --------------------------------------------------------


def test_bcrypt_realmente_trunca_em_72_bytes():
    """Este é o fato que justifica a validação — se um dia deixar de valer, o
    limite pode ser afrouxado."""
    referencia = hash_password("A" * BCRYPT_MAX_PASSWORD_BYTES)
    assert verify_password("A" * BCRYPT_MAX_PASSWORD_BYTES + "sufixo-ignorado", referencia)


@pytest.mark.asyncio
async def test_registro_recusa_senha_maior_que_o_bcrypt_usa(client: AsyncClient):
    resposta = await client.post(
        f"{PREFIX}/auth/register",
        json={
            "email": "frase-senha@example.com",
            "password": "A" * (BCRYPT_MAX_PASSWORD_BYTES + 1),
            "username": "frase",
        },
    )
    assert resposta.status_code == 422, resposta.text
    assert "72 bytes" in resposta.text


@pytest.mark.asyncio
async def test_o_limite_e_em_bytes_e_nao_em_caracteres(client: AsyncClient):
    """40 caracteres acentuados são 80 bytes em UTF-8. Contar caracteres deixaria
    passar exatamente a senha que o bcrypt trunca."""
    senha = "ç" * 40
    assert len(senha) < BCRYPT_MAX_PASSWORD_BYTES < len(senha.encode("utf-8"))

    resposta = await client.post(
        f"{PREFIX}/auth/register",
        json={"email": "acentos@example.com", "password": senha, "username": "acentos"},
    )
    assert resposta.status_code == 422, resposta.text


@pytest.mark.asyncio
async def test_senha_no_limite_e_aceita(client: AsyncClient):
    resposta = await client.post(
        f"{PREFIX}/auth/register",
        json={
            "email": "no-limite@example.com",
            "password": "A" * BCRYPT_MAX_PASSWORD_BYTES,
            "username": "limite",
        },
    )
    assert resposta.status_code == 201, resposta.text


@pytest.mark.asyncio
async def test_login_de_conta_antiga_com_senha_longa_continua_funcionando(
    client: AsyncClient, db_session
):
    """O teto vale no cadastro, não na conferência: quem criou conta antes da
    validação não pode ficar trancado do lado de fora."""
    longa = "A" * 100
    db_session.add(
        User(
            email="conta-antiga@example.com",
            hashed_password=hash_password(longa),
            username="antiga",
        )
    )
    await db_session.commit()

    resposta = await client.post(
        f"{PREFIX}/auth/login",
        json={"email": "conta-antiga@example.com", "password": longa},
    )
    assert resposta.status_code == 200, resposta.text
