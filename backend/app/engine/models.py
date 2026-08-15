"""Estruturas de dados produzidas pelo scanner e consumidas pelos analyzers.

São Pydantic para que os PRs seguintes possam serializar um relatório sem
conversão manual, e porque validação explícita vale mais do que dicionário solto
quando o dado vem de repositório de terceiros.
"""

from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """Um arquivo candidato à análise. Não guarda conteúdo: os analyzers leem sob
    demanda, para não carregar o repositório inteiro em memória."""

    path: str = Field(description="Caminho relativo à raiz, sempre com barras POSIX")
    size_bytes: int
    language: str | None = Field(
        default=None, description="Linguagem detectada, ou None quando não reconhecida"
    )
    is_binary: bool = False

    @property
    def is_analyzable_text(self) -> bool:
        """Binário entra no inventário mas nunca no parser."""
        return not self.is_binary and self.language is not None


class RepositoryScan(BaseModel):
    """Resultado do scan. `truncated` existe porque um scan parcial apresentado
    como completo produz score enganoso — quem consome precisa saber que só viu
    parte do repositório."""

    root: str
    files: list[FileInfo] = Field(default_factory=list)
    total_bytes: int = 0
    languages: dict[str, int] = Field(
        default_factory=dict, description="Bytes por linguagem, ignorando binários"
    )
    truncated: bool = False
    truncation_reason: str | None = None

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def primary_language(self) -> str | None:
        """A linguagem com mais bytes. Empate resolve pelo nome, para o resultado
        ser determinístico entre execuções."""
        if not self.languages:
            return None
        return max(sorted(self.languages), key=lambda lang: self.languages[lang])
