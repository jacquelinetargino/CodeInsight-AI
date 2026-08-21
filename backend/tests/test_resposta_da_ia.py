"""A resposta do provedor de IA é entrada não confiável.

Não porque o provedor seja hostil, mas porque o texto que ele devolve não é
garantido por contrato nenhum. Duas razões independentes:

1. **O modelo erra sozinho.** `"HIGH"` em vez de `"high"` é o caso clássico, e a
   coluna `suggestions.severity` é um ENUM do Postgres — caixa alta não entra.
2. **O conteúdo do repositório analisado entra no prompt**, e ele é NÃO
   CONFIÁVEL. Não medi que uma injeção dirigida funcione contra um modelo real,
   e por isso não afirmo isso aqui; o ponto é que a resposta não pode ser
   tratada como contrato validado quando parte da entrada que a produziu veio
   de terceiro.

O que acontecia antes, medido gravando de verdade no Postgres:

    severity fora do enum      -> InvalidTextRepresentation
    severity em caixa alta     -> InvalidTextRepresentation
    title com 5000 caracteres  -> StringDataRightTruncation
    file_path com 5000         -> StringDataRightTruncation
    description nula           -> NotNullViolation
    item que não é dict        -> AttributeError
    "suggestions": "texto"     -> AttributeError

E o efeito era desproporcional ao defeito: as sugestões são gravadas numa
transação só, então **uma** malformada levava junto todas as boas. Como
`_enrich_with_ai` engole a exceção de propósito — a análise do motor está
completa e não deve virar falha porque um serviço externo respondeu torto —, o
usuário via a análise concluída e nenhuma sugestão, sem explicação.
"""

import uuid

import pytest
from sqlalchemy import select

from app.ai.base import AIProvider, AIProviderError
from app.core.config import get_settings
from app.core.security import hash_password
from app.models.analysis import Analysis
from app.models.enums import AnalysisStatus, Severity
from app.models.fix_suggestion import FixSuggestion
from app.models.repository import Repository
from app.models.suggestion import Suggestion
from app.models.user import User
from app.services import analysis_service

settings = get_settings()
PREFIX = settings.api_v1_prefix


class ProviderQueDevolve(AIProvider):
    """Devolve exatamente o que o teste mandou, inclusive coisas fora do
    contrato — que é o ponto."""

    name = "roteirizado"

    def __init__(self, resposta) -> None:
        self._resposta = resposta

    async def generate_text(self, system_prompt, user_prompt, max_tokens=4096):  # pragma: no cover
        raise NotImplementedError

    async def generate_json(self, system_prompt, user_prompt, max_tokens=4096):
        return self._resposta


@pytest.fixture
async def analise(db_session) -> Analysis:
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@exemplo.test",
        hashed_password=hash_password("senha-de-teste-bem-comprida"),
        username=uuid.uuid4().hex[:8],
    )
    db_session.add(user)
    await db_session.commit()

    repo = Repository(
        user_id=user.id, github_repo_id=1, full_name="dono/repo", default_branch="main"
    )
    db_session.add(repo)
    await db_session.commit()

    row = Analysis(repository_id=repo.id, status=AnalysisStatus.DONE)
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


async def _gravar(db_session, analise: Analysis, resposta) -> list[Suggestion]:
    await analysis_service.generate_and_persist_suggestions(
        db_session, analise, "dono/repo", {}, ProviderQueDevolve(resposta)
    )
    await db_session.commit()
    resultado = await db_session.execute(
        select(Suggestion).where(Suggestion.analysis_id == analise.id)
    )
    return list(resultado.scalars())


# --- o que derrubava a gravação inteira --------------------------------------


@pytest.mark.parametrize(
    ("nome", "item"),
    [
        ("severidade fora do enum", {"title": "t", "description": "d", "severity": "CATASTROFICO"}),
        ("severidade em caixa alta", {"title": "t", "description": "d", "severity": "HIGH"}),
        ("titulo enorme", {"title": "T" * 5000, "description": "d", "severity": "high"}),
        (
            "caminho enorme",
            {"title": "t", "description": "d", "severity": "high", "file_path": "p" * 5000},
        ),
        ("descricao nula", {"title": "t", "description": None, "severity": "high"}),
        ("severidade nula", {"title": "t", "description": "d", "severity": None}),
        ("severidade numerica", {"title": "t", "description": "d", "severity": 3}),
        ("titulo numerico", {"title": 42, "description": "d", "severity": "high"}),
        ("sem chave de severidade", {"title": "t", "description": "d"}),
        ("code_fix numerico", {"title": "t", "description": "d", "code_fix": 7}),
    ],
)
async def test_sugestao_fora_do_contrato_e_gravada_em_vez_de_derrubar(
    db_session, analise, nome, item
):
    linhas = await _gravar(db_session, analise, {"suggestions": [item]})

    assert len(linhas) == 1, f"{nome}: a sugestão se perdeu"
    assert isinstance(linhas[0].severity, Severity)


async def test_uma_sugestao_ruim_nao_leva_as_boas_junto(db_session, analise):
    """A garantia central. Medido antes da correção: duas sugestões, uma válida
    e uma inválida, **zero** gravadas — porque é uma transação só."""
    linhas = await _gravar(
        db_session,
        analise,
        {
            "suggestions": [
                {"title": "sugestão legítima", "description": "d", "severity": "high"},
                {"title": "t", "description": "d", "severity": "CATASTROFICO"},
                {"title": "outra legítima", "description": "d", "severity": "low"},
            ]
        },
    )

    titulos = {linha.title for linha in linhas}
    assert "sugestão legítima" in titulos
    assert "outra legítima" in titulos
    assert len(linhas) == 3


# --- normalização, item a item -----------------------------------------------


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("high", Severity.HIGH),
        ("HIGH", Severity.HIGH),
        ("High", Severity.HIGH),
        ("  critical  ", Severity.CRITICAL),
        ("low", Severity.LOW),
        ("medium", Severity.MEDIUM),
        ("CATASTROFICO", Severity.MEDIUM),
        ("", Severity.MEDIUM),
        (None, Severity.MEDIUM),
        (3, Severity.MEDIUM),
        (["high"], Severity.MEDIUM),
    ],
)
def test_severidade_normalizada(valor, esperado):
    """Caixa e espaço são a mesma severidade que o modelo quis dizer. O que não
    corresponde a nenhuma cai em MEDIUM — que já era o default da coluna e o
    default deste código quando a chave vem ausente, então não é dado novo
    inventado."""
    assert analysis_service._severidade(valor) is esperado


async def test_titulo_grande_e_truncado_no_limite_da_coluna(db_session, analise):
    linhas = await _gravar(
        db_session, analise, {"suggestions": [{"title": "T" * 5000, "description": "d"}]}
    )

    assert len(linhas[0].title) == analysis_service.TITULO_MAX
    assert linhas[0].title.startswith("TTT"), "truncar tem de preservar o começo"


async def test_caminho_grande_vira_nulo_em_vez_de_truncado(db_session, analise):
    """Caminho truncado é caminho errado: apontaria para um arquivo que não
    existe. Não afirmar nada sobre o arquivo é mais honesto."""
    linhas = await _gravar(
        db_session,
        analise,
        {"suggestions": [{"title": "t", "description": "d", "file_path": "p" * 5000}]},
    )

    assert linhas[0].file_path is None


@pytest.mark.parametrize(
    ("nome", "resposta"),
    [
        ("lista com item que não é dict", {"suggestions": ["só um texto solto"]}),
        ("suggestions como string", {"suggestions": "não é lista"}),
        ("suggestions como número", {"suggestions": 7}),
        ("suggestions ausente", {}),
        ("resposta que não é dict", ["a", "b"]),
        ("item sem título e sem descrição", {"suggestions": [{"severity": "high"}]}),
        ("item vazio", {"suggestions": [{}]}),
    ],
)
async def test_resposta_sem_nada_aproveitavel_grava_zero_sem_estourar(
    db_session, analise, nome, resposta
):
    linhas = await _gravar(db_session, analise, resposta)

    assert linhas == [], nome


async def test_item_ruim_no_meio_nao_descarta_os_bons(db_session, analise):
    linhas = await _gravar(
        db_session,
        analise,
        {"suggestions": [{"title": "boa", "description": "d"}, "lixo", {"title": "outra boa"}]},
    )

    assert {linha.title for linha in linhas} == {"boa", "outra boa"}


# --- a trava do outro lado ----------------------------------------------------


async def test_resposta_bem_formada_continua_gravando_tudo(db_session, analise):
    """Descartar tudo também passaria em quase todos os testes acima."""
    linhas = await _gravar(
        db_session,
        analise,
        {
            "suggestions": [
                {
                    "title": "Adicionar testes",
                    "description": "A cobertura está baixa.",
                    "severity": "high",
                    "file_path": "app/main.py",
                    "code_fix": "def test_x(): ...",
                }
            ]
        },
    )

    (linha,) = linhas
    assert linha.title == "Adicionar testes"
    assert linha.description == "A cobertura está baixa."
    assert linha.severity is Severity.HIGH
    assert linha.file_path == "app/main.py"
    assert linha.code_fix == "def test_x(): ..."


# --- correção: o oposto, e de propósito --------------------------------------


@pytest.mark.parametrize(
    ("nome", "resposta"),
    [
        ("suggested_code nulo", {"current_code": "a", "suggested_code": None, "explanation": "e"}),
        ("suggested_code vazio", {"suggested_code": "", "explanation": "e"}),
        ("suggested_code só espaço", {"suggested_code": "   ", "explanation": "e"}),
        ("campos ausentes", {}),
        ("resposta que não é dict", ["nada"]),
    ],
)
async def test_correcao_sem_codigo_falha_em_vez_de_gravar_vazio(
    db_session, analise, nome, resposta
):
    """Aqui o tratamento é o oposto do das sugestões, e de propósito: sem código
    sugerido não há correção. Antes, a linha era gravada assim mesmo e a rota
    devolvia 201 — a interface mostrava uma correção que não existe."""
    with pytest.raises((AIProviderError, ValueError)):
        await analysis_service.generate_and_persist_fix(
            db_session,
            analise,
            title="t",
            description="d",
            file_path="app.py",
            line=1,
            file_content=None,
            ai_provider=ProviderQueDevolve(resposta),
        )


@pytest.mark.parametrize(
    ("nome", "resposta", "explicacao_esperada"),
    [
        ("explicação como número", {"suggested_code": "x", "explanation": 42}, "42"),
        ("explicação como lista", {"suggested_code": "x", "explanation": ["a"]}, "['a']"),
        ("explicação nula", {"suggested_code": "x", "explanation": None}, ""),
        ("sem explicação", {"suggested_code": "x"}, ""),
    ],
)
async def test_correcao_com_codigo_sobrevive_a_campo_torto(
    db_session, analise, nome, resposta, explicacao_esperada
):
    """Explicação pobre não é motivo para perder a correção — o código sugerido,
    que é o que o usuário pediu, está lá."""
    linha = await analysis_service.generate_and_persist_fix(
        db_session,
        analise,
        title="t",
        description="d",
        file_path="app.py",
        line=1,
        file_content=None,
        ai_provider=ProviderQueDevolve(resposta),
    )
    await db_session.commit()

    assert linha.suggested_code == "x"
    assert linha.explanation == explicacao_esperada


# --- pela API ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_rota_de_correcao_responde_502_quando_a_ia_nao_devolve_codigo(
    client, test_user, authed_client_factory, override_ai_provider, db_session
):
    """502 e não 500: quem falhou foi o serviço a montante. A distinção importa
    para quem lê o log — 500 significaria exceção escapando sem tratamento."""
    repo = Repository(
        user_id=test_user.id, github_repo_id=9, full_name="dono/repo", default_branch="main"
    )
    db_session.add(repo)
    await db_session.commit()
    await db_session.refresh(repo)

    row = Analysis(repository_id=repo.id, status=AnalysisStatus.DONE)
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    override_ai_provider(json_responses=[{"explanation": "sem código nenhum"}])

    resposta = await client.post(
        f"{PREFIX}/analysis/{row.id}/fix",
        json={"title": "achado", "description": "descrição"},
        headers=authed_client_factory(test_user.id),
    )

    assert resposta.status_code == 502, resposta.text

    gravadas = await db_session.execute(
        select(FixSuggestion).where(FixSuggestion.analysis_id == row.id)
    )
    assert list(gravadas.scalars()) == [], "não pode sobrar correção em branco no banco"
