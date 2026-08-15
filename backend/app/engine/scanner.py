"""Percorre um repositório já extraído e produz um `RepositoryScan`.

Não baixa nada nem toca a rede: recebe um diretório que já existe em disco —
tipicamente o que `acquisition.acquire_repository` entrega. O percurso, a poda de
diretórios, o descarte de symlinks e os limites por arquivo e por quantidade vêm
do módulo de aquisição; aqui acrescentamos metadados, detecção de linguagem e o
orçamento de tamanho total.

O repositório continua sendo dado não confiável: nada é executado, importado ou
passado para shell. Só leitura de metadados e, para classificar binários, dos
primeiros 8 KB.
"""

import logging
from pathlib import Path

from app.core.config import get_settings
from app.engine.acquisition import is_binary, iter_analyzable_files
from app.engine.languages import detect_language
from app.engine.models import FileInfo, RepositoryScan

logger = logging.getLogger(__name__)


class ScanError(Exception):
    """Falha ao percorrer o repositório. Mensagem segura para exibir."""


def _relative_path(root: Path, path: Path) -> str:
    """Caminho relativo à raiz, normalizado e sempre com barras POSIX — para que
    um achado tenha o mesmo `file_path` no Windows e no Linux.

    Também é a barreira de contenção: um caminho que resolva para fora da raiz é
    recusado em vez de virar item do inventário."""
    root_resolved = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ScanError("Arquivo fora da raiz do repositório foi ignorado por segurança.")
    return resolved.relative_to(root_resolved).as_posix()


def scan_repository(root: Path) -> RepositoryScan:
    """Inventaria os arquivos analisáveis de `root`.

    O resultado marca `truncated` quando algum limite interrompeu o percurso: um
    scan parcial apresentado como completo produziria score enganoso.
    """
    if not root.is_dir():
        raise ScanError(f"Raiz do repositório não é um diretório: {root}")

    settings = get_settings()
    scan = RepositoryScan(root=str(root))
    total_bytes = 0

    candidates = iter_analyzable_files(root)

    # `iter_analyzable_files` para ao atingir o teto de arquivos. Bater exatamente
    # no limite é o sinal disponível de que pode haver mais coisa não vista.
    if len(candidates) >= settings.engine_max_files:
        scan.truncated = True
        scan.truncation_reason = (
            f"Limite de {settings.engine_max_files} arquivos atingido; "
            "o repositório pode ter mais arquivos não inventariados."
        )

    for path in candidates:
        try:
            relative = _relative_path(root, path)
        except ScanError as exc:
            logger.warning("Arquivo descartado no scan: %s", exc)
            continue

        try:
            size = path.stat().st_size
        except OSError:
            continue

        if total_bytes + size > settings.engine_max_uncompressed_bytes:
            scan.truncated = True
            scan.truncation_reason = (
                "Limite de bytes totais atingido; o inventário está incompleto."
            )
            break

        binary = is_binary(path)
        language = None if binary else detect_language(path)

        scan.files.append(
            FileInfo(path=relative, size_bytes=size, language=language, is_binary=binary)
        )
        total_bytes += size
        if language:
            scan.languages[language] = scan.languages.get(language, 0) + size

    scan.total_bytes = total_bytes
    # Ordem estável: dois scans do mesmo repositório produzem a mesma saída,
    # independentemente da ordem em que o sistema de arquivos devolveu as entradas.
    scan.files.sort(key=lambda item: item.path)
    return scan
