"""O pipeline do motor, de ponta a ponta, sem rede e sem banco.

A garantia que este arquivo existe para proteger: uma análise completa sai do
motor sem nenhum provedor de IA, sem chave de API e sem serviço externo.
"""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.engine import pipeline
from app.engine.analyzers.base import AnalyzerResult
from app.engine.findings import FindingCategory
from app.engine.pipeline import AnalysisTimeoutError, analyze_directory, analyze_repository
from app.engine.rules.git_activity import BranchInfo, CommitInfo, GitActivity


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def build_repo(root: Path, arquivos: dict[str, str]) -> Path:
    for caminho, conteudo in arquivos.items():
        destino = root / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")
    return root


PROJETO_PROBLEMATICO = {
    "app.py": "import os\npassword = 'hunter2'\nos.system('ls')\n",
    "requirements.txt": "flask\n",
    "id_rsa": "conteudo-que-nao-deve-ser-lido\n",
}


# --- a garantia central -----------------------------------------------------


def test_analise_completa_sem_nenhum_provedor_de_ia(tmp_path):
    """Nenhuma variável de IA está definida na suíte, por construção do
    conftest. Se o motor precisasse de uma, este teste falharia."""
    report = analyze_directory(build_repo(tmp_path, PROJETO_PROBLEMATICO))

    assert report.findings_count > 0
    assert report.score.overall is not None
    assert report.score.risk_level is not None


def test_o_pipeline_nao_importa_nada_de_ia():
    """Trava de arquitetura: uma importação de IA no pipeline reintroduziria a
    dependência que a migração inteira existe para remover."""
    fonte = Path(pipeline.__file__).read_text(encoding="utf-8")
    assert "app.ai" not in fonte
    assert "ai_provider" not in fonte


def test_todas_as_oito_dimensoes_sao_avaliadas(tmp_path):
    report = analyze_directory(build_repo(tmp_path, PROJETO_PROBLEMATICO))

    avaliadas = {r.category for r in report.results}
    assert avaliadas == set(FindingCategory)
    assert report.score.unevaluated == []


def test_repositorio_vazio_nao_quebra(tmp_path):
    report = analyze_directory(tmp_path)
    assert report.score.overall is not None


# --- resiliência ------------------------------------------------------------


def test_analyzer_que_falha_nao_derruba_os_outros(tmp_path, monkeypatch):
    """Perder sete dimensões porque uma quebrou seria pior para quem pediu a
    análise do que reportar a falha de uma."""

    class AnalyzerQuebrado:
        name = "quebrado"
        category = FindingCategory.SECURITY

        def analyze(self, root, scan):
            raise ValueError("arquivo inesperado")

    original = pipeline.build_analyzers
    monkeypatch.setattr(
        pipeline,
        "build_analyzers",
        lambda activity=None: [AnalyzerQuebrado(), *original(activity)[1:]],
    )

    report = analyze_directory(build_repo(tmp_path, PROJETO_PROBLEMATICO))

    seguranca = next(r for r in report.results if r.analyzer == "quebrado")
    assert seguranca.findings == []
    assert "não avaliada" in seguranca.notes[0]
    # As demais seguiram normalmente.
    assert len(report.results) == len(FindingCategory)


def test_falha_de_analyzer_nao_e_confundida_com_ausencia_de_problema(tmp_path, monkeypatch):
    """A dimensão que falhou não pode sair com nota cheia e nenhuma explicação."""

    class AnalyzerQuebrado:
        name = "quebrado"
        category = FindingCategory.SECURITY

        def analyze(self, root, scan):
            raise ValueError("falhou")

    monkeypatch.setattr(pipeline, "build_analyzers", lambda activity=None: [AnalyzerQuebrado()])
    report = analyze_directory(build_repo(tmp_path, PROJETO_PROBLEMATICO))

    dimensao = report.score.dimension(FindingCategory.SECURITY)
    assert dimensao is not None
    assert dimensao.notes  # a lacuna fica registrada
    assert len(report.score.unevaluated) == len(FindingCategory) - 1


# --- atividade opcional do GitHub -------------------------------------------


def test_sem_atividade_do_github_a_lacuna_vira_nota(tmp_path):
    report = analyze_directory(build_repo(tmp_path, {"app.py": "x = 1\n"}))

    git = next(r for r in report.results if r.category is FindingCategory.GIT)
    assert any("API do GitHub" in nota for nota in git.notes)


def test_com_atividade_do_github_nao_ha_nota_de_lacuna(tmp_path):
    activity = GitActivity(
        default_branch="main",
        branches=[BranchInfo(name="main", protected=True)],
        recent_commits=[CommitInfo(message="feat: algo específico", author="alguem")],
        contributors=["alguem", "outra"],
        merged_pull_requests=3,
    )
    report = analyze_directory(build_repo(tmp_path, {"app.py": "x = 1\n"}), activity)

    git = next(r for r in report.results if r.category is FindingCategory.GIT)
    assert not any("API do GitHub" in nota for nota in git.notes)


# --- timeout ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_interrompe_a_analise(tmp_path, monkeypatch):
    """Um repositório patológico não pode prender o worker indefinidamente."""
    import contextlib

    monkeypatch.setenv("ENGINE_MAX_ANALYSIS_SECONDS", "0")
    get_settings.cache_clear()

    @contextlib.asynccontextmanager
    async def fake_acquire(*args, **kwargs):
        yield tmp_path

    monkeypatch.setattr(pipeline, "acquire_repository", fake_acquire)

    def lento(root, activity=None):
        import time

        time.sleep(0.5)
        return None

    monkeypatch.setattr(pipeline, "analyze_directory", lento)

    with pytest.raises(AnalysisTimeoutError) as exc:
        await analyze_repository(None, "dono/repo", "main")

    assert "segundos" in str(exc.value)


@pytest.mark.asyncio
async def test_analise_bem_sucedida_devolve_o_relatorio(tmp_path, monkeypatch):
    import contextlib

    build_repo(tmp_path, PROJETO_PROBLEMATICO)

    @contextlib.asynccontextmanager
    async def fake_acquire(*args, **kwargs):
        yield tmp_path

    monkeypatch.setattr(pipeline, "acquire_repository", fake_acquire)

    report = await analyze_repository(None, "dono/repo", "main")
    assert isinstance(report.results[0], AnalyzerResult)
    assert report.findings_count > 0
