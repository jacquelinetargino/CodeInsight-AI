"""Tarballs maliciosos montados em memória — nenhum teste toca a rede nem enche
o disco. Cada caso corresponde a uma ameaça do desenho de segurança do PR 03."""

import gzip
import io
import tarfile
from pathlib import Path

import httpx
import pytest

from app.core.config import get_settings
from app.engine import acquisition
from app.engine.acquisition import (
    AcquisitionError,
    RepositoryTooLargeError,
    acquire_repository,
    is_binary,
    iter_analyzable_files,
    read_text,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def build_tar_gz(entries) -> bytes:
    """entries: lista de (nome, tipo, payload). tipo em {file, dir, symlink,
    link, fifo, chr}."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for name, kind, payload in entries:
            info = tarfile.TarInfo(name)
            if kind == "file":
                data = payload if isinstance(payload, bytes) else str(payload).encode()
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            elif kind == "dir":
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = payload
                tar.addfile(info)
            elif kind == "link":
                info.type = tarfile.LNKTYPE
                info.linkname = payload
                tar.addfile(info)
            elif kind == "fifo":
                info.type = tarfile.FIFOTYPE
                tar.addfile(info)
            elif kind == "chr":
                info.type = tarfile.CHRTYPE
                tar.addfile(info)
    return gzip.compress(raw.getvalue())


def extract_bytes(tar_bytes: bytes, target: Path) -> None:
    """Roda o mesmo caminho de extração da aplicação sobre um tarball em bytes."""
    archive = target.parent / "arquivo.tar.gz"
    archive.write_bytes(tar_bytes)
    acquisition._check_gzip_magic(archive)
    acquisition._extract(archive, target)


@pytest.fixture
def target(tmp_path: Path) -> Path:
    destino = tmp_path / "src"
    destino.mkdir()
    return destino


# --- T02/T03: caminhos ------------------------------------------------------


def test_rejects_traversal_entry(target: Path):
    """`filter="data"` recusa com OutsideDestinationError, subclasse de
    FilterError — asserção específica para o teste não passar por acidente."""
    tar = build_tar_gz([("../fora.txt", "file", "x")])
    with pytest.raises(tarfile.FilterError):
        extract_bytes(tar, target)
    assert not (target.parent.parent / "fora.txt").exists()


def test_neutralizes_absolute_path(target: Path):
    """O filtro `data` não rejeita caminho absoluto POSIX: remove a barra e grava
    dentro do destino. O importante é que nada escape."""
    tar = build_tar_gz([("/etc/codeinsight_probe.txt", "file", "x")])
    extract_bytes(tar, target)

    assert (target / "etc" / "codeinsight_probe.txt").exists()
    assert not Path("/etc/codeinsight_probe.txt").exists()


# --- T04/T05: links ---------------------------------------------------------


@pytest.mark.parametrize("alvo", ["../../etc/passwd", "/etc/passwd"])
def test_rejects_symlink_escape(target: Path, alvo: str):
    tar = build_tar_gz([("repo/link", "symlink", alvo)])
    extract_bytes(tar, target)
    # Symlinks não são selecionados para extração: nada é criado.
    assert not (target / "repo" / "link").exists()


def test_rejects_hardlink_escape(target: Path):
    tar = build_tar_gz([("repo/hl", "link", "../../etc/passwd")])
    extract_bytes(tar, target)
    assert not (target / "repo" / "hl").exists()


# --- T06: arquivos especiais ------------------------------------------------


@pytest.mark.parametrize("kind", ["fifo", "chr"])
def test_special_file_types_are_not_extracted(target: Path, kind: str):
    tar = build_tar_gz([("repo/especial", kind, None)])
    extract_bytes(tar, target)
    assert not (target / "repo" / "especial").exists()


# --- T12: nomes hostis ------------------------------------------------------


@pytest.mark.parametrize("nome", ["repo/CON.txt", "repo/PRN", "repo/com1.log"])
def test_windows_reserved_names_rejected(target: Path, nome: str):
    tar = build_tar_gz([(nome, "file", "x")])
    with pytest.raises(AcquisitionError, match="nome de caminho inválido"):
        extract_bytes(tar, target)


# --- T01: bomba de descompressão -------------------------------------------


def test_aborts_on_uncompressed_budget(target: Path, monkeypatch):
    """Um tar de zeros comprime absurdamente bem. O teto do descomprimido tem de
    barrar antes de gravar."""
    monkeypatch.setenv("ENGINE_MAX_UNCOMPRESSED_BYTES", str(64 * 1024))
    monkeypatch.setenv("ENGINE_MAX_FILE_BYTES", str(32 * 1024))
    get_settings.cache_clear()

    entries = [(f"repo/zeros_{i}.bin", "file", b"\0" * 16 * 1024) for i in range(20)]
    with pytest.raises(RepositoryTooLargeError, match="descomprimido"):
        extract_bytes(build_tar_gz(entries), target)


def test_aborts_on_file_count(target: Path, monkeypatch):
    monkeypatch.setenv("ENGINE_MAX_FILES", "5")
    get_settings.cache_clear()

    entries = [(f"repo/f{i}.py", "file", "print(1)") for i in range(10)]
    with pytest.raises(RepositoryTooLargeError, match="arquivos"):
        extract_bytes(build_tar_gz(entries), target)


def test_skips_oversized_file_without_failing(target: Path, monkeypatch):
    """Arquivo grande demais é pulado, não fatal — bundles minificados são
    grandes e inúteis para análise."""
    monkeypatch.setenv("ENGINE_MAX_FILE_BYTES", "100")
    get_settings.cache_clear()

    extract_bytes(
        build_tar_gz(
            [
                ("repo/pequeno.py", "file", "print(1)"),
                ("repo/enorme.js", "file", "x" * 5000),
            ]
        ),
        target,
    )
    assert (target / "repo" / "pequeno.py").exists()
    assert not (target / "repo" / "enorme.js").exists()


def test_ignored_dirs_are_pruned(target: Path):
    extract_bytes(
        build_tar_gz(
            [
                ("repo/app.py", "file", "print(1)"),
                ("repo/node_modules/left-pad/index.js", "file", "module.exports=1"),
                ("repo/.git/config", "file", "[core]"),
            ]
        ),
        target,
    )
    assert (target / "repo" / "app.py").exists()
    assert not (target / "repo" / "node_modules").exists()
    assert not (target / "repo" / ".git").exists()


# --- formato ----------------------------------------------------------------


def test_rejects_non_gzip_payload(tmp_path: Path):
    arquivo = tmp_path / "falso.tar.gz"
    arquivo.write_bytes(b"isto nao e gzip")
    with pytest.raises(AcquisitionError, match="gzip"):
        acquisition._check_gzip_magic(arquivo)


# --- T15: allowlist de redirect --------------------------------------------


@pytest.mark.parametrize(
    ("url", "permitido"),
    [
        ("https://codeload.github.com/o/r/legacy.tar.gz/main", True),
        ("https://api.github.com/repos/o/r/tarball/main", True),
        ("https://objects.githubusercontent.com/x", True),
        ("https://evil.example.com/payload", False),
        ("http://169.254.169.254/latest/meta-data/", False),
    ],
)
def test_redirect_allowlist(url: str, permitido: bool):
    if permitido:
        acquisition._assert_destino_permitido(url)
    else:
        with pytest.raises(AcquisitionError, match="não permitido"):
            acquisition._assert_destino_permitido(url)


# Só precisa parecer um gzip para o teste; o download é recusado antes de
# qualquer leitura do conteúdo.
GZIP_MINIMO = bytes([0x1F, 0x8B]) + bytes(100)


# --- T15b: o esquema de cada salto ------------------------------------------


@pytest.mark.parametrize(
    "esquema_ruim",
    [
        "http://codeload.github.com/o/r/legacy.tar.gz/main",
        "http://api.github.com/repos/o/r/tarball/main",
        "http://objects.githubusercontent.com/x",
    ],
)
def test_host_permitido_em_http_e_recusado(esquema_ruim: str):
    """Host permitido não basta: a requisição leva `Authorization: Bearer` em
    todos os saltos, e em http o token sai em texto claro."""
    with pytest.raises(AcquisitionError, match="esquema não permitido"):
        acquisition._assert_destino_permitido(esquema_ruim)


async def test_redirecionamento_para_http_nao_leva_o_token(tmp_path: Path, monkeypatch):
    """A prova no caminho real, com a credencial em jogo.

    Antes da checagem de esquema, o segundo salto saía assim:

        http://codeload.github.com/o/r/legacy.tar.gz  auth=Bearer <token>
    """
    vistas: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistas.append((str(request.url), request.headers.get("authorization")))
        if request.url.scheme == "https":
            return httpx.Response(
                302,
                headers={"location": "http://codeload.github.com/o/r/legacy.tar.gz/main"},
            )
        return httpx.Response(200, content=GZIP_MINIMO)

    monkeypatch.setattr(
        httpx.AsyncClient, "send", _fake_send(httpx.MockTransport(handler)), raising=True
    )

    with pytest.raises(AcquisitionError, match="esquema não permitido"):
        await acquisition._download_archive(
            "TOKEN-DO-SERVIDOR", "o/r", "main", tmp_path / "a.tar.gz"
        )

    saltos_em_claro = [url for url, _ in vistas if url.startswith("http://")]
    assert saltos_em_claro == [], f"requisição em texto claro: {saltos_em_claro}"
    assert all(auth == "Bearer TOKEN-DO-SERVIDOR" for _, auth in vistas), vistas


# --- T15c: o caminho da URL do tarball ---------------------------------------


def test_caminho_do_tarball_reescrito_e_recusado():
    """Terceira aparição do mecanismo dos PRs 35 e 38: `..` num segmento troca o
    endpoint chamado quando o httpx normaliza a URL."""
    caminho = "/repos/dono/repo/tarball/../../../../user"
    with pytest.raises(AcquisitionError, match="reescrito"):
        acquisition._assert_caminho_nao_reescrito(
            f"{acquisition.GITHUB_API_BASE}{caminho}", caminho
        )


@pytest.mark.parametrize("ref", ["main", "feature/nova-coisa", "v1.2.3", "release/2024.01"])
def test_referencia_legitima_passa(ref: str):
    """A trava do outro lado: `/` em nome de branch é comum e não pode ser
    confundido com navegação."""
    caminho = f"/repos/dono/repo/tarball/{ref}"
    acquisition._assert_caminho_nao_reescrito(f"{acquisition.GITHUB_API_BASE}{caminho}", caminho)


async def test_download_com_referencia_hostil_nao_chama_a_api(tmp_path: Path, monkeypatch):
    """Nenhuma entrada chega aqui com `..` hoje — `ref` é o `default_branch` da
    API do GitHub, que não permite isso em nome de referência. O teste garante
    que, se algum caminho novo trouxer, nenhuma requisição sai antes da recusa.
    """
    vistas: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistas.append(str(request.url))
        return httpx.Response(200, content=GZIP_MINIMO)

    monkeypatch.setattr(
        httpx.AsyncClient, "send", _fake_send(httpx.MockTransport(handler)), raising=True
    )

    with pytest.raises(AcquisitionError, match="reescrito"):
        await acquisition._download_archive(
            "TOKEN-DO-SERVIDOR", "o/r", "../../../../user", tmp_path / "a.tar.gz"
        )

    assert vistas == [], f"uma requisição saiu mesmo assim: {vistas}"


# --- T01: teto do download --------------------------------------------------


async def test_download_aborts_over_archive_cap(tmp_path: Path, monkeypatch):
    """Transporte falso emitindo bytes sem fim: o contador tem de cortar."""
    monkeypatch.setenv("ENGINE_MAX_ARCHIVE_BYTES", str(4096))
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\0" * (1024 * 1024))

    monkeypatch.setattr(
        httpx.AsyncClient, "send", _fake_send(httpx.MockTransport(handler)), raising=True
    )

    with pytest.raises(RepositoryTooLargeError, match="passou de"):
        await acquisition._download_archive(None, "o/r", "main", tmp_path / "a.tar.gz")


def _fake_send(transport: httpx.MockTransport):
    async def send(self, request, **kwargs):
        return await transport.handle_async_request(request)

    return send


# --- T13/T14: limpeza -------------------------------------------------------


async def test_tempdir_removed_on_success(monkeypatch):
    tar = build_tar_gz([("repo/app.py", "file", "print(1)")])
    monkeypatch.setattr(acquisition, "_download_archive", _fake_download(tar))

    async with acquire_repository(None, "o/r", "main") as repo_dir:
        workdir = repo_dir.parent.parent
        assert (repo_dir / "app.py").exists()
        assert workdir.exists()

    assert not workdir.exists()


async def test_tempdir_removed_on_exception(monkeypatch):
    tar = build_tar_gz([("repo/app.py", "file", "print(1)")])
    monkeypatch.setattr(acquisition, "_download_archive", _fake_download(tar))

    workdir = None
    with pytest.raises(ValueError, match="falha simulada"):
        async with acquire_repository(None, "o/r", "main") as repo_dir:
            workdir = repo_dir.parent.parent
            raise ValueError("falha simulada dentro do bloco")

    assert workdir is not None and not workdir.exists()


def _fake_download(tar_bytes: bytes):
    async def download(access_token, full_name, ref, destination):
        destination.write_bytes(tar_bytes)
        return len(tar_bytes)

    return download


# --- o tamanho declarado pela API não é porta --------------------------------


async def test_tamanho_declarado_nao_recusa_repositorio(monkeypatch, tmp_path):
    """Regressão: existiu uma porta baseada no `size` da GitHub API, e ela
    recusava repositórios de 3 MB.

    Medido: `pydantic/pydantic` declara 424 MB e entrega um tarball de 3,2 MB —
    132× menos. A razão vai de 1,6× a 132× entre repositórios, então nenhum
    limiar serve para os dois lados. `acquire_repository` não aceita mais esse
    parâmetro; quem tentar reintroduzi-lo quebra este teste.
    """
    import inspect

    assinatura = inspect.signature(acquire_repository)
    assert "declared_size_kb" not in assinatura.parameters


async def test_os_limites_reais_continuam_valendo():
    """A proteção é a que conta bytes de verdade, e ela não foi tocada.

    Cada limite abaixo tem teste próprio neste arquivo; esta asserção existe
    para que remover um deles do config seja uma falha ruidosa, e não uma
    ausência silenciosa.
    """
    get_settings.cache_clear()
    settings = get_settings()

    for nome in (
        "engine_max_archive_bytes",
        "engine_max_uncompressed_bytes",
        "engine_max_files",
        "engine_max_file_bytes",
    ):
        assert getattr(settings, nome) > 0, nome


# --- T11: binários e encoding ----------------------------------------------


def test_binary_detection_and_safe_read(tmp_path: Path):
    binario = tmp_path / "imagem.png"
    binario.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00binario")
    texto = tmp_path / "codigo.py"
    texto.write_text("print('olá')", encoding="utf-8")

    assert is_binary(binario) is True
    assert is_binary(texto) is False

    invalido = tmp_path / "quebrado.py"
    invalido.write_bytes(b"x = '\xff\xfe invalido'")
    assert read_text(invalido)  # não levanta


def test_iter_analyzable_files_prunes_ignored(tmp_path: Path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print(1)", encoding="utf-8")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "index.js").write_text("1", encoding="utf-8")

    encontrados = {p.name for p in iter_analyzable_files(tmp_path)}
    assert "main.py" in encontrados
    assert "index.js" not in encontrados


def test_post_extraction_size_budget_is_enforced(target: Path, monkeypatch):
    """Defesa em profundidade: mesmo que os tamanhos declarados no cabeçalho
    passassem pela vetagem, o que foi gravado em disco é medido de novo."""
    monkeypatch.setenv("ENGINE_MAX_FILE_BYTES", str(1024 * 1024))
    monkeypatch.setenv("ENGINE_MAX_UNCOMPRESSED_BYTES", str(1024 * 1024))
    get_settings.cache_clear()

    tar = build_tar_gz([("repo/dados.bin", "file", b"\0" * 200_000)])
    archive = target.parent / "arquivo.tar.gz"
    archive.write_bytes(tar)

    # Vetagem passa (200 KB < 1 MB); baixamos o teto logo antes da extração para
    # que só a medição pós-extração possa barrar.
    with tarfile.open(archive, mode="r:gz") as tar_file:
        membros = acquisition._vet_members(tar_file)
        tar_file.extractall(path=target, members=membros, filter="data")

    monkeypatch.setenv("ENGINE_MAX_UNCOMPRESSED_BYTES", "1000")
    get_settings.cache_clear()

    with pytest.raises(RepositoryTooLargeError, match="extraído"):
        acquisition._assert_size_budget(target)
