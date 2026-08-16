"""Sinais de risco relacionados ao Git.

Duas fontes, deliberadamente separadas:

- **Sistema de arquivos** — arquivos sensíveis versionados, binários grandes.
  Sempre disponível, porque vem do repositório extraído.
- **Atividade** — branches, commits, contribuidores. Vem da API do GitHub e
  pode não existir; o analyzer trata a ausência como "não avaliado", nunca como
  "está tudo bem".

Nada do conteúdo dos arquivos sensíveis é lido ou reportado: o achado aponta o
caminho, e é o caminho que o usuário precisa para agir.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

# Arquivos cujo simples versionamento é o problema, independente do conteúdo.
# O `.env` já é coberto por SEC-005; aqui entram os demais.
SENSITIVE_FILE_PATTERNS: dict[str, tuple[str, ...]] = {
    "chave privada": ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"),
    "certificado ou chave": (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks"),
    "credencial de ferramenta": (".npmrc", ".pypirc", ".netrc", ".htpasswd"),
    "credencial de nuvem": ("credentials", "service-account.json", "gcloud.json"),
    "banco de dados local": (".sqlite", ".sqlite3", ".db"),
    "despejo de memória": (".dump", ".sql.gz"),
}

# Acima disto, um binário versionado incha o histórico permanentemente — o git
# guarda todas as versões.
LARGE_BINARY_BYTES = 5 * 1024 * 1024

# Mensagens que não dizem o que mudou.
_LOW_QUALITY_MESSAGE_RE = re.compile(
    r"^\s*(?:wip|fix|fixes|fixed|update|updates|updated|change|changes|test|tests|"
    r"asdf|foo|bar|temp|tmp|\.+|commit|minor|stuff|things|ajuste|correcao|correção|"
    r"atualizacao|atualização|teste|testes)\s*[.!]?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BranchInfo:
    name: str
    protected: bool = False


@dataclass(frozen=True)
class CommitInfo:
    message: str
    author: str | None = None


@dataclass
class GitActivity:
    """Dados vindos da API do GitHub.

    É opcional por construção: análise local não tem acesso a isso, e o motor
    precisa funcionar mesmo assim.
    """

    default_branch: str = "main"
    branches: list[BranchInfo] = field(default_factory=list)
    recent_commits: list[CommitInfo] = field(default_factory=list)
    contributors: list[str] = field(default_factory=list)
    merged_pull_requests: int = 0

    @property
    def default_branch_is_protected(self) -> bool:
        for branch in self.branches:
            if branch.name == self.default_branch:
                return branch.protected
        return False

    @property
    def low_quality_messages(self) -> list[str]:
        return [c.message for c in self.recent_commits if is_low_quality_message(c.message)]


def is_low_quality_message(message: str) -> bool:
    """Mensagem que não informa o que mudou.

    Só a primeira linha é avaliada: um resumo ruim com corpo detalhado ainda
    dificulta a leitura do histórico.
    """
    primeira = message.strip().splitlines()[0] if message.strip() else ""
    return bool(_LOW_QUALITY_MESSAGE_RE.match(primeira))


def classify_sensitive_file(relative_path: str) -> str | None:
    """Categoria de sensibilidade do arquivo, ou `None`.

    A classificação é por nome e extensão — o conteúdo nunca é lido, para que
    nada sensível transite pelo motor.
    """
    caminho = relative_path.replace("\\", "/").lower()
    nome = Path(caminho).name

    for categoria, padroes in SENSITIVE_FILE_PATTERNS.items():
        for padrao in padroes:
            if padrao.startswith("."):
                # Extensão: `chave.pem`. Também cobre nomes como `.npmrc`.
                if nome.endswith(padrao) or nome == padrao:
                    return categoria
            elif nome == padrao or caminho.endswith(f"/{padrao}"):
                return categoria

    return None
