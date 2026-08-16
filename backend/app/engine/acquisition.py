"""Baixa e extrai o tarball de um repositório do GitHub com segurança.

O arquivo vem de terceiros e é tratado como hostil do começo ao fim: pode ser uma
bomba de descompressão, conter caminhos que escapam do destino, symlinks
apontando para fora, arquivos especiais ou nomes que quebram o sistema de
arquivos. Cada uma dessas ameaças tem uma barreira explícita abaixo.

Uso:

    async with acquire_repository(token, "owner/repo", "main") as repo_dir:
        ...  # repo_dir some ao sair do bloco, inclusive em erro
"""

import contextlib
import logging
import os
import re
import shutil
import tarfile
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"

# O tarball da API redireciona para outro host. Seguir redirect sem restrição
# transformaria um repositório malicioso (ou um DNS comprometido) em SSRF, então
# só estes destinos são aceitos.
_ALLOWED_DOWNLOAD_HOSTS = frozenset(
    {
        "api.github.com",
        "codeload.github.com",
        "objects.githubusercontent.com",
    }
)

_GZIP_MAGIC = b"\x1f\x8b"

# Diretórios que nunca contribuem para a análise e que dominam a contagem de
# arquivos em repositórios reais. Podados durante a caminhada, antes de descer.
IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        "dist",
        "build",
        "target",
        "vendor",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".tox",
        ".next",
        ".nuxt",
    }
)

# Nomes reservados no Windows: criar um arquivo assim quebra a extração e pode
# ter efeitos colaterais no sistema. O ambiente de desenvolvimento é Windows.
_WINDOWS_RESERVED = re.compile(
    r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)",
    re.IGNORECASE,
)


class AcquisitionError(Exception):
    """Falha ao obter o repositório. A mensagem é segura para exibir ao usuário."""


class RepositoryTooLargeError(AcquisitionError):
    pass


def _assert_host_allowed(url: str) -> None:
    host = httpx.URL(url).host
    if host not in _ALLOWED_DOWNLOAD_HOSTS:
        raise AcquisitionError(
            f"Download redirecionado para um host não permitido ({host!r}). "
            "Abortado por segurança."
        )


def _is_hostile_name(name: str) -> bool:
    """Nomes que o sistema de arquivos não deveria receber, independentemente de
    onde apontem."""
    if "\x00" in name or any(ord(c) < 32 for c in name):
        return True
    return any(_WINDOWS_RESERVED.match(part) for part in Path(name).parts)


async def _download_archive(
    access_token: str | None, full_name: str, ref: str, destination: Path
) -> int:
    """Baixa o tarball contando os bytes recebidos e abortando ao estourar o
    limite. O GitHub responde com `transfer-encoding: chunked` e sem
    `Content-Length`, então não há como conferir o tamanho antes de baixar."""
    settings = get_settings()
    limit = settings.engine_max_archive_bytes
    url = f"{GITHUB_API_BASE}/repos/{full_name}/tarball/{ref}"

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    total = 0
    async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
        current_url = url
        for _ in range(5):  # limite de saltos, evita laço de redirecionamento
            _assert_host_allowed(current_url)
            request = client.build_request("GET", current_url, headers=headers)
            response = await client.send(request, stream=True)

            if response.is_redirect:
                location = response.headers.get("location", "")
                await response.aclose()
                if not location:
                    raise AcquisitionError("Redirecionamento sem destino ao baixar o tarball.")
                current_url = str(httpx.URL(current_url).join(location))
                continue

            try:
                if response.status_code == 404:
                    raise AcquisitionError(
                        f"Repositório ou referência não encontrada: {full_name}@{ref}"
                    )
                if response.status_code != 200:
                    raise AcquisitionError(
                        f"GitHub respondeu {response.status_code} ao baixar o repositório."
                    )

                with destination.open("wb") as handle:
                    async for chunk in response.aiter_bytes(64 * 1024):
                        total += len(chunk)
                        if total > limit:
                            raise RepositoryTooLargeError(
                                f"O arquivo do repositório passou de {limit} bytes. "
                                "Download interrompido."
                            )
                        handle.write(chunk)
            finally:
                await response.aclose()

            return total

    raise AcquisitionError("Redirecionamentos demais ao baixar o tarball.")


def _check_gzip_magic(archive: Path) -> None:
    with archive.open("rb") as handle:
        if handle.read(2) != _GZIP_MAGIC:
            raise AcquisitionError("O conteúdo baixado não é um arquivo gzip válido.")


def _vet_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    """Percorre as entradas aplicando o orçamento de extração.

    Os tamanhos vêm do cabeçalho do tar, ou seja, são afirmações do próprio
    arquivo — servem para recusar cedo, não como garantia. O que foi realmente
    gravado é reconferido em `_assert_size_budget`, depois da extração."""
    settings = get_settings()
    selected: list[tarfile.TarInfo] = []
    declared_total = 0
    file_count = 0

    for member in tar:
        if _is_hostile_name(member.name):
            raise AcquisitionError(
                "O arquivo contém um nome de caminho inválido para o sistema de arquivos."
            )

        if member.isdir():
            selected.append(member)
            continue

        # Symlinks, hardlinks, devices, FIFOs e sockets não são fonte de análise.
        # O filtro `data` do tarfile já recusaria os perigosos; recusar aqui dá
        # uma mensagem melhor e não depende só da stdlib.
        if not member.isfile():
            continue

        if any(part in IGNORED_DIRS for part in Path(member.name).parts):
            continue

        if member.size > settings.engine_max_file_bytes:
            logger.debug("Arquivo ignorado por tamanho: %s (%d bytes)", member.name, member.size)
            continue

        declared_total += member.size
        if declared_total > settings.engine_max_uncompressed_bytes:
            raise RepositoryTooLargeError(
                "O conteúdo descomprimido do repositório passou do limite configurado."
            )

        selected.append(member)
        file_count += 1
        if file_count > settings.engine_max_files:
            raise RepositoryTooLargeError(
                f"O repositório tem mais de {settings.engine_max_files} arquivos analisáveis."
            )

    return selected


def _assert_size_budget(root: Path) -> None:
    """Mede o que foi de fato gravado em disco, em vez de confiar nos tamanhos
    declarados nos cabeçalhos do tar. Interrompe assim que o teto é cruzado."""
    settings = get_settings()
    limit = settings.engine_max_uncompressed_bytes
    total = 0

    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        total += path.stat().st_size
        if total > limit:
            raise RepositoryTooLargeError(
                "O conteúdo extraído passou do limite de bytes descomprimidos."
            )


def _assert_inside(root: Path, extracted_root: Path) -> None:
    """Defesa em profundidade: mesmo com `filter='data'`, confere que tudo que
    foi gravado está sob a raiz. Se um dia o filtro mudar, esta checagem segura."""
    root_resolved = root.resolve()
    for path in extracted_root.rglob("*"):
        if not path.resolve().is_relative_to(root_resolved):
            raise AcquisitionError(
                "Uma entrada do arquivo escapou do diretório de extração. Abortado."
            )


def _extract(archive: Path, target: Path) -> None:
    with tarfile.open(archive, mode="r:gz") as tar:
        members = _vet_members(tar)
        # filter="data" (PEP 706) recusa path traversal, symlink/hardlink para
        # fora do destino e caminhos absolutos do Windows; caminhos absolutos
        # POSIX são neutralizados para dentro do destino.
        tar.extractall(path=target, members=members, filter="data")
    _assert_inside(target, target)
    _assert_size_budget(target)


def _single_root(target: Path) -> Path:
    """O tarball do GitHub embrulha tudo em `owner-repo-sha/`. Devolve essa pasta
    para que o resto do motor veja a raiz real do repositório."""
    entries = [p for p in target.iterdir() if p.is_dir()]
    if len(entries) == 1:
        return entries[0]
    return target


@contextlib.asynccontextmanager
async def acquire_repository(
    access_token: str | None,
    full_name: str,
    ref: str,
    *,
    declared_size_kb: int | None = None,
) -> AsyncIterator[Path]:
    """Entrega o repositório extraído num diretório temporário, removido ao sair
    do bloco — em sucesso, em exceção e em cancelamento.

    `declared_size_kb` é o campo `size` da GitHub API, usado como porta barata
    antes de gastar banda. É advisório: reflete o repositório git, não o tarball.
    """
    settings = get_settings()

    if declared_size_kb is not None and declared_size_kb > settings.engine_max_repo_size_kb:
        raise RepositoryTooLargeError(
            f"O repositório tem cerca de {declared_size_kb // 1024} MB, acima do limite "
            f"de {settings.engine_max_repo_size_kb // 1024} MB."
        )

    # mkdtemp: permissões 0700 e caminho imprevisível. Arquivo e extração vivem
    # os dois aqui dentro, então a limpeza é uma remoção de raiz só.
    workdir = Path(tempfile.mkdtemp(prefix="codeinsight-"))
    archive = workdir / "repo.tar.gz"
    extracted = workdir / "src"
    extracted.mkdir()

    try:
        await _download_archive(access_token, full_name, ref, archive)
        _check_gzip_magic(archive)
        _extract(archive, extracted)
        # O comprimido não serve mais: liberar antes da fase longa importa em
        # ambiente de disco efêmero.
        archive.unlink(missing_ok=True)
        yield _single_root(extracted)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@dataclass
class DiscoveredFiles:
    """Resultado da descoberta.

    `oversized` existe porque arquivo grande demais para analisar ainda é um
    fato relevante — um binário de 50 MB versionado é achado do analyzer de Git.
    Descartá-lo em silêncio perderia essa informação.
    """

    analyzable: list[Path] = field(default_factory=list)
    oversized: list[Path] = field(default_factory=list)


def discover_files(root: Path) -> DiscoveredFiles:
    """Percorre o repositório uma vez, separando o que dá para analisar do que
    passou do teto de tamanho.

    Os diretórios ignorados são podados antes de descer neles — em repositório
    com `node_modules` commitado, essa diferença decide se a análise termina.
    """
    settings = get_settings()
    resultado = DiscoveredFiles()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_symlink():  # não seguimos links dentro do repositório
                continue
            try:
                tamanho = path.stat().st_size
            except OSError:
                continue

            if tamanho > settings.engine_max_file_bytes:
                resultado.oversized.append(path)
                continue

            resultado.analyzable.append(path)
            if len(resultado.analyzable) >= settings.engine_max_files:
                return resultado

    return resultado


def iter_analyzable_files(root: Path) -> list[Path]:
    """Apenas os arquivos analisáveis. Mantida com a assinatura original para
    não quebrar quem já a usa."""
    return discover_files(root).analyzable


def is_binary(path: Path) -> bool:
    """Byte nulo nos primeiros 8 KB é o indicador clássico. Binário entra no
    inventário, nunca no parser."""
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(8192)
    except OSError:
        return True


def read_text(path: Path) -> str:
    """Lê como texto sem nunca levantar por encoding: repositório de terceiros
    tem arquivo em qualquer codificação, e isso não pode derrubar a análise."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
