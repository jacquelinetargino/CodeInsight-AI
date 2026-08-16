"""Scanner: percurso, limites, contenção na raiz e integração com a aquisição.

Nenhum teste toca a rede nem executa nada do repositório analisado.
"""

import gzip
import io
import os
import tarfile
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.engine import acquisition
from app.engine.acquisition import acquire_repository
from app.engine.models import FileInfo, RepositoryScan
from app.engine.scanner import ScanError, scan_repository


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _can_symlink() -> bool:
    """Criar symlink no Windows exige privilégio (WinError 1314). Condicionar o
    skip à capacidade real, e não à plataforma, faz os testes rodarem em qualquer
    máquina onde symlinks funcionem — inclusive Windows com Modo de
    Desenvolvedor."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        alvo = base / "alvo"
        alvo.write_text("x", encoding="utf-8")
        try:
            os.symlink(alvo, base / "link")
        except (OSError, NotImplementedError):
            return False
    return True


requires_symlinks = pytest.mark.skipif(
    not _can_symlink(), reason="ambiente não permite criar symlinks (no CI Linux, roda)"
)


def write(root: Path, relative: str, content: str | bytes = "x") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


# --- casos básicos ----------------------------------------------------------


def test_empty_repository(tmp_path: Path):
    scan = scan_repository(tmp_path)
    assert scan.file_count == 0
    assert scan.total_bytes == 0
    assert scan.languages == {}
    assert scan.truncated is False
    assert scan.primary_language is None


def test_rejects_non_directory(tmp_path: Path):
    arquivo = write(tmp_path, "solto.py")
    with pytest.raises(ScanError, match="não é um diretório"):
        scan_repository(arquivo)


def test_regular_files_are_inventoried(tmp_path: Path):
    write(tmp_path, "app.py", "print(1)")
    write(tmp_path, "README.md", "# Projeto")

    scan = scan_repository(tmp_path)

    assert scan.file_count == 2
    assert {f.path for f in scan.files} == {"README.md", "app.py"}
    assert scan.total_bytes > 0


def test_multiple_languages_are_counted_by_bytes(tmp_path: Path):
    write(tmp_path, "grande.py", "x" * 500)
    write(tmp_path, "pequeno.js", "y" * 10)

    scan = scan_repository(tmp_path)

    assert scan.languages["Python"] == 500
    assert scan.languages["JavaScript"] == 10
    assert scan.primary_language == "Python"


def test_unknown_extension_and_no_extension(tmp_path: Path):
    write(tmp_path, "dados.xyz")
    write(tmp_path, "LICENSE")

    scan = scan_repository(tmp_path)

    assert scan.file_count == 2
    assert all(f.language is None for f in scan.files)
    assert scan.languages == {}


def test_hidden_files_are_inventoried(tmp_path: Path):
    write(tmp_path, ".gitignore", "*.pyc")
    write(tmp_path, ".github/workflows/ci.yml", "on: push")

    scan = scan_repository(tmp_path)
    caminhos = {f.path for f in scan.files}

    assert ".gitignore" in caminhos
    assert ".github/workflows/ci.yml" in caminhos


def test_nested_structure(tmp_path: Path):
    write(tmp_path, "a/b/c/d/fundo.py", "print(1)")

    scan = scan_repository(tmp_path)

    assert scan.file_count == 1
    assert scan.files[0].path == "a/b/c/d/fundo.py"


def test_unicode_filenames(tmp_path: Path):
    write(tmp_path, "relatório/análise_ção.py", "print('olá')")

    scan = scan_repository(tmp_path)

    assert scan.files[0].path == "relatório/análise_ção.py"
    assert scan.files[0].language == "Python"


# --- caminhos ---------------------------------------------------------------


def test_paths_are_relative_and_posix(tmp_path: Path):
    write(tmp_path, "src/pacote/modulo.py", "print(1)")

    scan = scan_repository(tmp_path)
    caminho = scan.files[0].path

    assert caminho == "src/pacote/modulo.py"
    assert "\\" not in caminho  # normalizado mesmo no Windows
    assert not Path(caminho).is_absolute()
    assert str(tmp_path) not in caminho  # nada do caminho absoluto vaza


def test_output_is_sorted_and_deterministic(tmp_path: Path):
    for nome in ("z.py", "a.py", "m.py"):
        write(tmp_path, nome, "print(1)")

    primeiro = [f.path for f in scan_repository(tmp_path).files]
    segundo = [f.path for f in scan_repository(tmp_path).files]

    assert primeiro == sorted(primeiro)
    assert primeiro == segundo


# --- diretórios ignorados ---------------------------------------------------


def test_ignored_directories_are_pruned(tmp_path: Path):
    write(tmp_path, "app.py", "print(1)")
    write(tmp_path, "node_modules/pkg/index.js", "1")
    write(tmp_path, ".git/config", "[core]")
    write(tmp_path, "__pycache__/app.cpython-312.pyc", "x")
    write(tmp_path, ".venv/lib/site.py", "x")

    scan = scan_repository(tmp_path)

    assert {f.path for f in scan.files} == {"app.py"}


# --- symlinks ---------------------------------------------------------------


@requires_symlinks
def test_symlink_inside_root_is_not_followed(tmp_path: Path):
    write(tmp_path, "real.py", "print(1)")
    os.symlink(tmp_path / "real.py", tmp_path / "link.py")

    scan = scan_repository(tmp_path)

    assert {f.path for f in scan.files} == {"real.py"}


@requires_symlinks
def test_symlink_escaping_root_is_not_followed(tmp_path: Path):
    """Um link apontando para fora da raiz não pode virar item do inventário."""
    fora = tmp_path.parent / "segredo_fora.txt"
    fora.write_text("conteudo sensivel", encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    write(repo, "app.py", "print(1)")
    os.symlink(fora, repo / "vazamento.txt")

    scan = scan_repository(repo)

    assert {f.path for f in scan.files} == {"app.py"}
    assert all("segredo_fora" not in f.path for f in scan.files)


@requires_symlinks
def test_symlinked_directory_is_not_descended(tmp_path: Path):
    externo = tmp_path.parent / "arvore_externa"
    (externo / "sub").mkdir(parents=True, exist_ok=True)
    (externo / "sub" / "invasor.py").write_text("print('fora')", encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    write(repo, "app.py", "print(1)")
    os.symlink(externo, repo / "linkdir")

    scan = scan_repository(repo)

    assert {f.path for f in scan.files} == {"app.py"}


def test_path_outside_root_is_rejected(tmp_path: Path, monkeypatch):
    """Contenção na raiz: mesmo que a listagem devolvesse um caminho de fora,
    ele é descartado em vez de entrar no inventário."""
    repo = tmp_path / "repo"
    repo.mkdir()
    write(repo, "app.py", "print(1)")
    intruso = tmp_path / "intruso.py"
    intruso.write_text("print('fora')", encoding="utf-8")

    from app.engine.acquisition import DiscoveredFiles

    monkeypatch.setattr(
        "app.engine.scanner.discover_files",
        lambda root: DiscoveredFiles(analyzable=[repo / "app.py", intruso]),
    )

    scan = scan_repository(repo)

    assert {f.path for f in scan.files} == {"app.py"}


# --- limites ----------------------------------------------------------------


def test_file_count_limit_marks_truncated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ENGINE_MAX_FILES", "3")
    get_settings.cache_clear()

    for i in range(10):
        write(tmp_path, f"f{i}.py", "print(1)")

    scan = scan_repository(tmp_path)

    assert scan.file_count == 3
    assert scan.truncated is True
    assert "arquivos" in (scan.truncation_reason or "")


def test_individual_size_limit_skips_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ENGINE_MAX_FILE_BYTES", "100")
    get_settings.cache_clear()

    write(tmp_path, "pequeno.py", "x" * 10)
    write(tmp_path, "enorme.py", "x" * 5000)

    scan = scan_repository(tmp_path)

    assert {f.path for f in scan.files} == {"pequeno.py"}


def test_total_size_limit_marks_truncated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ENGINE_MAX_FILE_BYTES", "10000")
    monkeypatch.setenv("ENGINE_MAX_UNCOMPRESSED_BYTES", "1500")
    get_settings.cache_clear()

    for i in range(10):
        write(tmp_path, f"f{i}.py", "x" * 1000)

    scan = scan_repository(tmp_path)

    assert scan.total_bytes <= 1500
    assert scan.truncated is True
    assert "bytes totais" in (scan.truncation_reason or "")


# --- binários ---------------------------------------------------------------


def test_binary_files_are_inventoried_but_not_classified(tmp_path: Path):
    write(tmp_path, "imagem.png", b"\x89PNG\r\n\x1a\n\x00\x00dados")
    write(tmp_path, "app.py", "print(1)")

    scan = scan_repository(tmp_path)
    por_caminho = {f.path: f for f in scan.files}

    assert por_caminho["imagem.png"].is_binary is True
    assert por_caminho["imagem.png"].language is None
    assert por_caminho["imagem.png"].is_analyzable_text is False
    assert por_caminho["app.py"].is_analyzable_text is True
    assert "PNG" not in scan.languages


# --- modelos ----------------------------------------------------------------


def test_primary_language_ties_break_deterministically():
    scan = RepositoryScan(root="/tmp/x", languages={"Python": 100, "Go": 100})
    assert scan.primary_language == scan.primary_language == "Go"


def test_file_info_defaults():
    info = FileInfo(path="a.py", size_bytes=10)
    assert info.language is None
    assert info.is_binary is False


# --- integração com a aquisição do PR 03 ------------------------------------


def _tar_gz(entries: list[tuple[str, str]]) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for nome, conteudo in entries:
            data = conteudo.encode()
            info = tarfile.TarInfo(nome)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return gzip.compress(raw.getvalue())


async def test_scans_repository_from_acquisition(monkeypatch):
    """Integração: o diretório que `acquire_repository` entrega é exatamente o
    que o scanner consome — sem rede, com download falsificado."""
    tar = _tar_gz(
        [
            ("owner-repo-abc123/app.py", "print('ola')"),
            ("owner-repo-abc123/src/index.ts", "export const x = 1;"),
            ("owner-repo-abc123/README.md", "# Projeto"),
            ("owner-repo-abc123/node_modules/pkg/index.js", "module.exports = 1"),
        ]
    )

    async def fake_download(access_token, full_name, ref, destination):
        destination.write_bytes(tar)
        return len(tar)

    monkeypatch.setattr(acquisition, "_download_archive", fake_download)

    async with acquire_repository(None, "owner/repo", "main") as repo_dir:
        scan = scan_repository(repo_dir)
        workdir = repo_dir.parent.parent

        assert {f.path for f in scan.files} == {"README.md", "app.py", "src/index.ts"}
        assert scan.languages == {
            "Python": len("print('ola')"),
            "TypeScript": len("export const x = 1;"),
            "Markdown": len("# Projeto"),
        }
        assert scan.truncated is False

    # A limpeza do PR 03 continua valendo depois do scan.
    assert not workdir.exists()


# --- garantias de segurança -------------------------------------------------


def test_scanner_never_executes_or_imports_repository_code(tmp_path: Path, monkeypatch):
    """Um arquivo que explodiria se importado ou executado é apenas inventariado."""
    write(tmp_path, "malicioso.py", "raise SystemExit('nunca deve rodar')\n")
    write(tmp_path, "setup.py", "import os; os.system('echo invadido')\n")
    write(tmp_path, "Makefile", "all:\n\techo invadido\n")

    import subprocess

    def explode(*args, **kwargs):  # pragma: no cover - só falha se for chamado
        raise AssertionError("o scanner não pode usar subprocess")

    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(subprocess, "Popen", explode)
    monkeypatch.setattr(os, "system", explode)

    scan = scan_repository(tmp_path)

    assert {f.path for f in scan.files} == {"Makefile", "malicioso.py", "setup.py"}
    assert scan.languages["Python"] > 0


def test_scanner_makes_no_network_calls(tmp_path: Path, monkeypatch):
    """Qualquer tentativa de abrir conexão derruba o teste."""
    import socket

    def explode(*args, **kwargs):  # pragma: no cover - só falha se for chamado
        raise AssertionError("o scanner não pode acessar a rede")

    monkeypatch.setattr(socket.socket, "connect", explode)
    monkeypatch.setattr(socket, "create_connection", explode)

    write(tmp_path, "app.py", "import requests; requests.get('http://evil')")

    scan = scan_repository(tmp_path)

    assert scan.file_count == 1
