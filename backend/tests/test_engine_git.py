"""Analyzer de Git.

Duas garantias verificadas aqui: nenhum comando `git` é executado, e o conteúdo
de arquivo sensível nunca é lido nem reportado — só o caminho.
"""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.engine.analyzers.git import (
    LOW_QUALITY_MESSAGE_RATIO,
    MIN_COMMITS_FOR_JUDGEMENT,
    GitAnalyzer,
)
from app.engine.findings import FindingCategory
from app.engine.rules.git_activity import (
    LARGE_BINARY_BYTES,
    BranchInfo,
    CommitInfo,
    GitActivity,
    classify_sensitive_file,
    is_low_quality_message,
)
from app.engine.rules.git_rules import GIT_RULES, register_git_rules
from app.engine.rules.registry import RuleRegistry
from app.engine.scanner import scan_repository


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def build_repo(root: Path, arquivos: dict[str, str | bytes]) -> Path:
    for caminho, conteudo in arquivos.items():
        destino = root / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(conteudo, bytes):
            destino.write_bytes(conteudo)
        else:
            destino.write_text(conteudo, encoding="utf-8")
    return root


def run(root: Path, activity: GitActivity | None = None):
    return GitAnalyzer(activity=activity).analyze(root, scan_repository(root))


def rule_ids(resultado) -> set[str]:
    return {f.rule_id for f in resultado.findings}


def make_activity(**overrides) -> GitActivity:
    base = {
        "default_branch": "main",
        "branches": [BranchInfo("main", protected=True)],
        "recent_commits": [
            CommitInfo(f"feat: adiciona funcionalidade {i}", "alice") for i in range(10)
        ],
        "contributors": ["alice", "bob"],
        "merged_pull_requests": 5,
    }
    return GitActivity(**{**base, **overrides})


# --- classificação de arquivo sensível --------------------------------------


@pytest.mark.parametrize(
    ("caminho", "categoria"),
    [
        ("id_rsa", "chave privada"),
        ("deploy/id_ed25519", "chave privada"),
        ("cert.pem", "certificado ou chave"),
        ("server.key", "certificado ou chave"),
        ("keystore.jks", "certificado ou chave"),
        (".npmrc", "credencial de ferramenta"),
        (".pypirc", "credencial de ferramenta"),
        ("aws/credentials", "credencial de nuvem"),
        ("service-account.json", "credencial de nuvem"),
        ("dados.sqlite3", "banco de dados local"),
    ],
)
def test_classifies_sensitive_files(caminho: str, categoria: str):
    assert classify_sensitive_file(caminho) == categoria


@pytest.mark.parametrize(
    "caminho",
    ["app.py", "README.md", "src/key_handler.py", "docs/pem-guide.md", "package.json"],
)
def test_does_not_flag_ordinary_files(caminho: str):
    """`key_handler.py` e `pem-guide.md` contêm as palavras mas não são credenciais."""
    assert classify_sensitive_file(caminho) is None


# --- qualidade de mensagem --------------------------------------------------


@pytest.mark.parametrize(
    "mensagem", ["wip", "fix", "update", "asdf", "...", "teste", "ajuste", "Minor"]
)
def test_recognizes_low_quality_messages(mensagem: str):
    assert is_low_quality_message(mensagem)


@pytest.mark.parametrize(
    "mensagem",
    [
        "feat: adiciona autenticação por token",
        "fix: corrige cálculo de score quando não há achados",
        "Remove dependência não utilizada do build",
    ],
)
def test_recognizes_informative_messages(mensagem: str):
    assert not is_low_quality_message(mensagem)


def test_only_the_first_line_is_judged():
    """Resumo ruim com corpo detalhado ainda dificulta ler o histórico."""
    assert is_low_quality_message("wip\n\nDescrição longa e detalhada do que mudou.")


# --- catálogo ---------------------------------------------------------------


def test_catalog_is_well_formed():
    for regra in GIT_RULES:
        assert regra.category is FindingCategory.GIT
        assert regra.description and regra.recommendation


def test_catalog_registers_without_duplicates():
    reg = RuleRegistry()
    register_git_rules(reg)
    assert len(reg) == len(GIT_RULES)


# --- arquivos versionados ---------------------------------------------------


def test_reports_sensitive_file(tmp_path):
    build_repo(tmp_path, {"deploy/id_rsa": "-----BEGIN PRIVATE KEY-----\n"})
    assert "GIT-001" in rule_ids(run(tmp_path))


def test_sensitive_file_content_is_never_reported(tmp_path):
    """A garantia central: o achado traz o caminho, nunca o conteúdo."""
    conteudo = "CHAVE-PRIVADA-QUE-NAO-PODE-VAZAR-EM-HIPOTESE-ALGUMA"
    build_repo(tmp_path, {"id_rsa": conteudo})

    for achado in run(tmp_path).findings:
        assert conteudo not in (achado.evidence or "")
        assert conteudo not in achado.description
        assert conteudo not in achado.title


def test_reports_oversized_file(tmp_path):
    """Regressão: arquivos acima do teto de análise eram descartados pelo
    scanner antes de qualquer analyzer vê-los, e GIT-002 nunca disparava.

    Usa tamanho real, sem mexer em limite: o valor do limiar faz parte do que
    está sendo verificado."""
    build_repo(tmp_path, {"assets/video.bin": b"\x00" * (LARGE_BINARY_BYTES + 1024)})

    achados = [f for f in run(tmp_path).findings if f.rule_id == "GIT-002"]
    assert [f.file_path for f in achados] == ["assets/video.bin"]
    assert "MB" in (achados[0].evidence or "")


def test_file_above_analysis_limit_but_small_is_not_reported(tmp_path, monkeypatch):
    """Passar do teto de análise não é, por si, problema de repositório.

    Um asset de poucos megabytes é grande demais para analisar e pequeno demais
    para inchar o histórico: reportá-lo seria falso positivo."""
    monkeypatch.setenv("ENGINE_MAX_FILE_BYTES", "1024")
    get_settings.cache_clear()

    build_repo(tmp_path, {"assets/logo.bin": b"\x00" * 4096})
    assert "GIT-002" not in rule_ids(run(tmp_path))


def test_oversized_file_is_never_read(tmp_path):
    """O arquivo é inventariado por metadado; o conteúdo não é aberto."""
    sentinela = b"CONTEUDO-QUE-NAO-PODE-SER-LIDO"
    repeticoes = LARGE_BINARY_BYTES // len(sentinela) + 100
    build_repo(tmp_path, {"grande.bin": sentinela * repeticoes})

    for achado in run(tmp_path).findings:
        assert sentinela.decode() not in (achado.evidence or "")


def test_oversized_sensitive_file_is_reported_once(tmp_path):
    """Uma chave privada enorme é um achado, não dois: vazar credencial é o
    problema, o tamanho é detalhe."""
    build_repo(tmp_path, {"id_rsa": "x" * (LARGE_BINARY_BYTES + 1024)})
    achados = [f for f in run(tmp_path).findings if f.file_path == "id_rsa"]

    assert len(achados) == 1
    assert achados[0].rule_id == "GIT-001"


def test_small_binary_is_clean(tmp_path):
    build_repo(tmp_path, {"icone.png": b"\x89PNG\r\n\x1a\n\x00pequeno"})
    assert "GIT-002" not in rule_ids(run(tmp_path))


def test_clean_repository(tmp_path):
    build_repo(tmp_path, {"app.py": "x = 1\n", "README.md": "# Projeto\n"})
    assert run(tmp_path, make_activity()).findings == []


# --- atividade opcional -----------------------------------------------------


def test_absent_activity_becomes_a_note_not_silence(tmp_path):
    """Sem dados da API, metade da análise não aconteceu — e isso precisa
    aparecer, para o score não tratar 'não avaliado' como 'sem problema'."""
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    resultado = run(tmp_path)

    assert resultado.notes
    assert "não avaliada" in resultado.notes[0]


def test_absent_activity_still_checks_files(tmp_path):
    build_repo(tmp_path, {"id_rsa": "chave"})
    assert "GIT-001" in rule_ids(run(tmp_path))


def test_reports_unprotected_default_branch(tmp_path):
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    atividade = make_activity(branches=[BranchInfo("main", protected=False)])
    assert "GIT-003" in rule_ids(run(tmp_path, atividade))


def test_protected_branch_is_clean(tmp_path):
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    assert "GIT-003" not in rule_ids(run(tmp_path, make_activity()))


def test_reports_single_contributor(tmp_path):
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    atividade = make_activity(contributors=["alice"])
    assert "GIT-004" in rule_ids(run(tmp_path, atividade))


def test_new_repository_is_not_judged_for_single_author(tmp_path):
    """Repositório recém-criado com poucos commits não diz nada sobre continuidade."""
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    atividade = make_activity(
        contributors=["alice"],
        recent_commits=[CommitInfo("feat: inicial", "alice")],
    )
    assert "GIT-004" not in rule_ids(run(tmp_path, atividade))


def test_reports_low_quality_history(tmp_path):
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    commits = [CommitInfo("wip", "alice") for _ in range(8)]
    commits += [CommitInfo("feat: algo real", "alice") for _ in range(2)]
    assert "GIT-005" in rule_ids(run(tmp_path, make_activity(recent_commits=commits)))


def test_good_history_is_clean(tmp_path):
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    assert "GIT-005" not in rule_ids(run(tmp_path, make_activity()))


def test_reports_absence_of_pull_requests(tmp_path):
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    assert "GIT-006" in rule_ids(run(tmp_path, make_activity(merged_pull_requests=0)))


def test_few_commits_are_not_judged(tmp_path):
    """Sem amostra suficiente, nem histórico nem ausência de PR são avaliados."""
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    atividade = make_activity(
        recent_commits=[CommitInfo("wip", "alice")],
        merged_pull_requests=0,
    )
    achados = rule_ids(run(tmp_path, atividade))

    assert "GIT-005" not in achados
    assert "GIT-006" not in achados


def test_empty_activity_does_not_crash(tmp_path):
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    resultado = run(tmp_path, GitActivity())
    assert isinstance(resultado.findings, list)


# --- segurança e determinismo -----------------------------------------------


def test_no_git_command_is_executed(tmp_path, monkeypatch):
    import os
    import subprocess

    def explode(*args, **kwargs):  # pragma: no cover - só falha se for chamado
        raise AssertionError("nenhum comando git pode ser executado")

    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(subprocess, "Popen", explode)
    monkeypatch.setattr(os, "system", explode)

    build_repo(tmp_path, {"id_rsa": "chave", "app.py": "x = 1\n"})
    assert run(tmp_path, make_activity()).findings


def test_no_network_access(tmp_path, monkeypatch):
    import socket

    def explode(*args, **kwargs):  # pragma: no cover - só falha se for chamado
        raise AssertionError("o analyzer nao pode acessar a rede")

    monkeypatch.setattr(socket.socket, "connect", explode)
    monkeypatch.setattr(socket, "create_connection", explode)

    build_repo(tmp_path, {"app.py": "x = 1\n"})
    run(tmp_path, make_activity())


def test_is_deterministic(tmp_path):
    build_repo(tmp_path, {"id_rsa": "chave", "app.py": "x = 1\n"})
    atividade = make_activity(branches=[BranchInfo("main", protected=False)])

    assert [f.id for f in run(tmp_path, atividade).findings] == [
        f.id for f in run(tmp_path, atividade).findings
    ]


def test_findings_carry_metadata(tmp_path):
    build_repo(tmp_path, {"id_rsa": "chave"})
    (achado,) = [f for f in run(tmp_path).findings if f.rule_id == "GIT-001"]

    assert achado.category is FindingCategory.GIT
    assert achado.analyzer == "git"
    assert achado.file_path == "id_rsa"
    assert achado.recommendation


def test_thresholds_are_documented():
    assert 0 < LOW_QUALITY_MESSAGE_RATIO < 1
    assert MIN_COMMITS_FOR_JUDGEMENT > 0


def test_analyzes_this_project():
    """Este repositório não deve ter arquivo sensível versionado."""
    raiz = Path(__file__).parent.parent.parent
    resultado = GitAnalyzer().analyze(raiz, scan_repository(raiz))

    assert "GIT-001" not in {f.rule_id for f in resultado.findings}
