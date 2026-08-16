"""Detector de credenciais.

O teste mais importante deste arquivo é `test_no_full_secret_ever_escapes`: se
alguma vez um segredo completo sair do detector, ele falha.

Os valores usados aqui são sintéticos, montados para casar com os padrões — não
são credenciais reais de lugar nenhum.
"""

import pytest

from app.engine.rules.secrets import (
    MASK_LENGTH,
    SECRET_PATTERNS,
    VISIBLE_PREFIX_CHARS,
    detect_secrets,
    mask_line,
    mask_secret,
)

# Credenciais falsas, cada uma casando com um padrão. O sufixo repetido deixa
# óbvio que são sintéticas.
FAKE = {
    "aws-access-key": "AKIAQQQQQQQQQQQQQQQQ",
    "github-pat-classic": "ghp_" + "a" * 36,
    "anthropic-key": "sk-ant-" + "b" * 30,
    "openai-key": "sk-" + "c" * 30,
    "groq-key": "gsk_" + "d" * 30,
    "google-api-key": "AIza" + "e" * 35,
    "slack-token": "xoxb-" + "1" * 20,
    "stripe-secret": "sk_live_" + "f" * 24,
    "supabase-secret": "sb_secret_" + "g" * 24,
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop",
}


# --- mascaramento -----------------------------------------------------------


def test_mask_keeps_short_prefix_and_hides_the_rest():
    mascarado = mask_secret("sk-abcdefghijklmnop")
    assert mascarado == "sk-a" + "*" * MASK_LENGTH
    assert "efghijklmnop" not in mascarado


def test_mask_hides_short_secrets_entirely():
    """Segredo curto não pode mostrar prefixo: sobraria pouca coisa a adivinhar."""
    assert mask_secret("abc") == "*" * MASK_LENGTH


def test_mask_does_not_reveal_length():
    """Dois segredos de tamanhos muito diferentes produzem máscaras iguais."""
    curto = mask_secret("sk-" + "a" * 10)
    longo = mask_secret("sk-" + "a" * 200)
    assert len(curto) == len(longo)


def test_mask_empty():
    assert mask_secret("") == ""


def test_mask_line_preserves_context():
    linha = '    API_KEY = "sk-abcdefghijklmnop"  # producao'
    mascarada = mask_line(linha, "sk-abcdefghijklmnop")

    assert "API_KEY" in mascarada
    assert "# producao" in mascarada
    assert "abcdefghijklmnop" not in mascarada


# --- garantia central -------------------------------------------------------


@pytest.mark.parametrize(("nome", "segredo"), sorted(FAKE.items()))
def test_no_full_secret_ever_escapes(nome: str, segredo: str):
    """Nenhum campo de nenhuma ocorrência pode conter a credencial inteira."""
    conteudo = f'CONFIG = "{segredo}"'
    ocorrencias = detect_secrets(conteudo)

    assert ocorrencias, f"o padrao {nome} deveria ter detectado"
    for ocorrencia in ocorrencias:
        for valor in vars(ocorrencia).values():
            assert segredo not in str(valor), f"{nome}: segredo vazou em {valor!r}"


def test_masked_evidence_keeps_only_the_prefix():
    segredo = FAKE["groq-key"]
    (ocorrencia,) = [m for m in detect_secrets(f"KEY={segredo}") if m.pattern_name == "groq-key"]

    assert segredo[:VISIBLE_PREFIX_CHARS] in ocorrencia.masked_evidence
    assert segredo[VISIBLE_PREFIX_CHARS:] not in ocorrencia.masked_evidence


# --- detecção por padrão ----------------------------------------------------


@pytest.mark.parametrize(("nome", "segredo"), sorted(FAKE.items()))
def test_each_pattern_detects_its_own_secret(nome: str, segredo: str):
    nomes = {m.pattern_name for m in detect_secrets(f'X = "{segredo}"')}
    assert nome in nomes


def test_detects_private_key_header():
    conteudo = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n"
    nomes = {m.pattern_name for m in detect_secrets(conteudo)}
    assert "private-key" in nomes


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://usuario:senhareal@host:5432/banco",
        "postgresql+asyncpg://usuario:senhareal@host:5432/banco",
        "mongodb://admin:senhareal@cluster",
        "redis://default:senhareal@cache:6379",
    ],
)
def test_detects_database_url_with_credentials(url: str):
    ocorrencias = detect_secrets(f'DATABASE_URL = "{url}"')
    assert any(m.pattern_name == "database-url-with-password" for m in ocorrencias)


def test_ignores_database_url_without_credentials():
    ocorrencias = detect_secrets('DATABASE_URL = "postgresql://localhost:5432/banco"')
    assert not any(m.pattern_name == "database-url-with-password" for m in ocorrencias)


def test_detects_generic_assignment():
    ocorrencias = detect_secrets('password = "umaSenhaQualquer123"')
    assert any(m.pattern_name == "generic-assignment" for m in ocorrencias)


# --- falsos positivos -------------------------------------------------------


@pytest.mark.parametrize(
    "linha",
    [
        'password = ""',
        'API_KEY = "changeme"',
        'SECRET = "your-secret-here"',
        'token = "xxxxxxxxxx"',
        'api_key = "replace-with-your-key"',
        'password = "placeholder"',
        'SECRET_KEY = "TODO"',
        "AI_API_KEY=",
    ],
)
def test_placeholders_are_not_reported(linha: str):
    """Sem isso o detector acusaria o `.env.example` de qualquer projeto."""
    assert detect_secrets(linha) == []


def test_prose_is_not_reported():
    texto = "Configure a variável API_KEY com a chave do seu provedor antes de subir."
    assert detect_secrets(texto) == []


# --- localização e formato --------------------------------------------------


def test_reports_correct_line_number():
    conteudo = "\n".join(["import os", "", f'KEY = "{FAKE["groq-key"]}"', "print(KEY)"])
    (ocorrencia,) = [m for m in detect_secrets(conteudo) if m.pattern_name == "groq-key"]
    assert ocorrencia.line == 3


def test_multiple_secrets_across_lines():
    conteudo = f'A = "{FAKE["aws-access-key"]}"\nB = "{FAKE["github-pat-classic"]}"'
    nomes = {m.pattern_name for m in detect_secrets(conteudo)}
    assert {"aws-access-key", "github-pat-classic"} <= nomes


def test_empty_content_returns_nothing():
    assert detect_secrets("") == []


def test_specific_patterns_outrank_generic_assignment():
    """Prefixo proprietário é quase certeza; atribuição genérica erra bastante —
    a confiança precisa refletir isso."""
    por_nome = {p.name: p.confidence for p in SECRET_PATTERNS}
    assert por_nome["aws-access-key"] > por_nome["generic-assignment"]
    assert por_nome["generic-assignment"] < 0.7


def test_all_patterns_have_description_and_valid_confidence():
    for padrao in SECRET_PATTERNS:
        assert padrao.description
        assert 0.0 < padrao.confidence <= 1.0


def test_pattern_names_are_unique():
    nomes = [p.name for p in SECRET_PATTERNS]
    assert len(nomes) == len(set(nomes))


def test_detector_is_deterministic():
    conteudo = f'KEY = "{FAKE["openai-key"]}"'
    primeiro = detect_secrets(conteudo)
    segundo = detect_secrets(conteudo)
    assert primeiro == segundo


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://codeinsight:changeme@postgres:5432/codeinsight",
        "postgres://user:your-password-here@host/db",
        "mysql://root:example@localhost/app",
    ],
)
def test_database_url_with_placeholder_password_is_not_reported(url: str):
    """`.env.example` de qualquer projeto tem URL de banco com senha de exemplo."""
    assert detect_secrets(f"DATABASE_URL={url}") == []


def test_database_url_evidence_masks_only_the_password():
    """Host e usuário são contexto útil; só a senha precisa sumir."""
    url = "postgresql://appuser:s3nh4Sup3rSecreta@db.exemplo.com:5432/producao"
    (ocorrencia,) = detect_secrets(f"DATABASE_URL={url}")

    assert "appuser" in ocorrencia.masked_evidence
    assert "db.exemplo.com" in ocorrencia.masked_evidence
    assert "s3nh4Sup3rSecreta" not in ocorrencia.masked_evidence


# --- calibragem do detector de credenciais -----------------------------------


def test_interpolacao_de_variavel_nao_e_credencial():
    """`${POSTGRES_PASSWORD}` é a ausência de uma credencial fixa, não uma.

    O docker-compose deste projeto era acusado por seguir exatamente a prática
    recomendada.
    """
    for valor in [
        "DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/app",
        "DATABASE_URL: postgresql://user:$DB_PASSWORD@db:5432/app",
        "url: postgresql://user:{{ db_password }}@db:5432/app",
        "url: postgresql://user:<sua-senha>@db:5432/app",
    ]:
        assert detect_secrets(valor) == [], valor


def test_exemplo_de_documentacao_nao_e_credencial():
    """`user:pass@host` e `USUARIO:SENHA@host` são a forma canônica de escrever
    um exemplo de string de conexão."""
    for valor in [
        "postgresql+asyncpg://user:pass@host:5432/db",
        "postgresql+asyncpg://USUARIO:SENHA@localhost:5432/codeinsight",
    ]:
        assert detect_secrets(valor) == [], valor


def test_evidencia_ja_mascarada_nao_e_reportada():
    """A saída do próprio detector acaba citada em documentação e em teste.
    Reencontrá-la seria o detector se acusando a si mesmo."""
    assert detect_secrets('API_KEY = "sk-1********"') == []


def test_credencial_de_verdade_continua_sendo_detectada():
    """A trava contra o excesso de tolerância: afrouxar o detector até ele parar
    de acusar é tão ruim quanto o falso positivo."""
    achados = detect_secrets("DATABASE_URL=postgresql://admin:R7pQ2xL9vNm4@prod.exemplo.com/app")
    assert achados
    assert "R7pQ2xL9vNm4" not in achados[0].masked_evidence
