"""A análise de ponta a ponta, do motor até o banco.

A função `run_repository_analysis` é o coração da migração e até aqui era sempre
substituída por um dublê nos testes — o caminho que decide se o produto funciona
sem IA não tinha cobertura nenhuma.

O que este arquivo prova: uma análise completa é executada e persistida **sem
nenhum provedor de IA configurado**. A suíte não define nenhuma variável de IA,
então se o caminho ainda dependesse de uma, estes testes falhariam.
"""

import contextlib
import uuid
from pathlib import Path

import pytest

from app.engine import pipeline
from app.models.analysis import Analysis, AnalysisResult
from app.models.enums import AnalysisStatus, Dimension
from app.models.repository import Repository
from app.tasks import analysis_tasks

REPO_DE_EXEMPLO = {
    "app.py": "import os\n\n\ndef processar(itens=[]):\n    os.system('ls')\n    return itens\n",
    "requirements.txt": "flask\n",
    "README.md": "# Projeto\n",
}


class _SessionProxy:
    """Entrega a sessão do teste no lugar da fábrica global.

    Sem isso, a task abriria `AsyncSessionLocal()`, que não carrega o
    `search_path` do schema isolado — a escrita cairia em `public`, junto dos
    dados de desenvolvimento.
    """

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


async def _cenario(db_session, tmp_path: Path, monkeypatch, arquivos=None):
    """Monta usuário, repositório e análise, e liga o motor a um diretório local."""
    from app.core.security import hash_password
    from app.models.user import User

    user = User(
        email=f"dono-{uuid.uuid4().hex[:8]}@exemplo.test",
        hashed_password=hash_password("senha-de-teste-bem-comprida"),
        username=f"dono{uuid.uuid4().hex[:8]}",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    repository = Repository(
        user_id=user.id, github_repo_id=42, full_name="dono/repo", default_branch="main"
    )
    db_session.add(repository)
    await db_session.commit()
    await db_session.refresh(repository)

    analysis = Analysis(repository_id=repository.id, status=AnalysisStatus.QUEUED)
    db_session.add(analysis)
    await db_session.commit()
    await db_session.refresh(analysis)

    for caminho, conteudo in (arquivos or REPO_DE_EXEMPLO).items():
        destino = tmp_path / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")

    @contextlib.asynccontextmanager
    async def fake_acquire(*args, **kwargs):
        yield tmp_path

    async def fake_get_repository(access_token, full_name):
        return {"size": 10}

    async def fake_build_git_activity(access_token, full_name, default_branch):
        return None

    monkeypatch.setattr(pipeline, "acquire_repository", fake_acquire)
    monkeypatch.setattr(analysis_tasks.github_service, "get_repository", fake_get_repository)
    monkeypatch.setattr(
        analysis_tasks.github_service, "build_git_activity", fake_build_git_activity
    )
    monkeypatch.setattr(analysis_tasks, "AsyncSessionLocal", lambda: _SessionProxy(db_session))

    return analysis


# --- a garantia central -----------------------------------------------------


@pytest.mark.asyncio
async def test_analise_completa_sem_provedor_de_ia(db_session, tmp_path, monkeypatch):
    analysis = await _cenario(db_session, tmp_path, monkeypatch)

    await analysis_tasks.run_repository_analysis(analysis.id)

    await db_session.refresh(analysis)
    assert analysis.status is AnalysisStatus.DONE
    assert analysis.error_message is None
    assert analysis.overall_score is not None
    assert analysis.finished_at is not None


@pytest.mark.asyncio
async def test_grava_uma_linha_por_dimensao_avaliada(db_session, tmp_path, monkeypatch):
    from sqlalchemy import select

    analysis = await _cenario(db_session, tmp_path, monkeypatch)
    await analysis_tasks.run_repository_analysis(analysis.id)

    linhas = (
        (
            await db_session.execute(
                select(AnalysisResult).where(AnalysisResult.analysis_id == analysis.id)
            )
        )
        .scalars()
        .all()
    )

    assert {linha.dimension for linha in linhas} == set(Dimension)
    assert all(0 <= linha.score <= 100 for linha in linhas)
    assert all(linha.summary for linha in linhas)


@pytest.mark.asyncio
async def test_achados_sao_gravados_no_formato_legado(db_session, tmp_path, monkeypatch):
    """O JSONB precisa continuar legível para quem só conhece os campos antigos."""
    from sqlalchemy import select

    analysis = await _cenario(db_session, tmp_path, monkeypatch)
    await analysis_tasks.run_repository_analysis(analysis.id)

    linha = (
        await db_session.execute(
            select(AnalysisResult).where(
                AnalysisResult.analysis_id == analysis.id,
                AnalysisResult.dimension == Dimension.QUALITY,
            )
        )
    ).scalar_one()

    assert linha.findings
    achado = linha.findings[0]
    for campo in ("title", "description", "suggestion", "severity", "file_path", "line"):
        assert campo in achado
    # E os campos novos do motor.
    for campo in ("rule_id", "confidence", "analyzer"):
        assert campo in achado


@pytest.mark.asyncio
async def test_o_resumo_registra_o_que_nao_foi_avaliado(db_session, tmp_path, monkeypatch):
    """Sem dados da API do GitHub, a lacuna precisa aparecer no resumo — um
    resumo omisso faria "não avaliado" parecer "sem problema"."""
    from sqlalchemy import select

    analysis = await _cenario(db_session, tmp_path, monkeypatch)
    await analysis_tasks.run_repository_analysis(analysis.id)

    linha = (
        await db_session.execute(
            select(AnalysisResult).where(
                AnalysisResult.analysis_id == analysis.id,
                AnalysisResult.dimension == Dimension.GIT,
            )
        )
    ).scalar_one()

    assert "API do GitHub" in linha.summary


# --- a IA é enriquecimento, não requisito -----------------------------------


@pytest.mark.asyncio
async def test_falha_da_ia_nao_invalida_a_analise(db_session, tmp_path, monkeypatch):
    """A análise do motor está completa e gravada. Marcá-la como falha porque um
    serviço externo recusou uma chamada seria descartar trabalho válido."""

    class ProviderQueFalha:
        name = "quebrado"

        async def generate_text(self, *args, **kwargs):
            raise RuntimeError("serviço indisponível")

        async def generate_json(self, *args, **kwargs):
            raise RuntimeError("serviço indisponível")

    analysis = await _cenario(db_session, tmp_path, monkeypatch)
    monkeypatch.setattr(analysis_tasks, "get_optional_ai_provider", lambda: ProviderQueFalha())

    await analysis_tasks.run_repository_analysis(analysis.id)

    await db_session.refresh(analysis)
    assert analysis.status is AnalysisStatus.DONE
    assert analysis.overall_score is not None


# --- falhas de verdade ------------------------------------------------------


@pytest.mark.asyncio
async def test_falha_do_motor_marca_a_analise_como_failed(db_session, tmp_path, monkeypatch):
    analysis = await _cenario(db_session, tmp_path, monkeypatch)

    async def acquire_que_falha(*args, **kwargs):
        raise RuntimeError("repositório grande demais")

    monkeypatch.setattr(analysis_tasks, "analyze_repository", acquire_que_falha)

    await analysis_tasks.run_repository_analysis(analysis.id)

    await db_session.refresh(analysis)
    assert analysis.status is AnalysisStatus.FAILED
    assert "grande demais" in analysis.error_message


@pytest.mark.asyncio
async def test_analise_inexistente_nao_estoura(db_session, monkeypatch):
    monkeypatch.setattr(analysis_tasks, "AsyncSessionLocal", lambda: _SessionProxy(db_session))
    await analysis_tasks.run_repository_analysis(uuid.uuid4())
