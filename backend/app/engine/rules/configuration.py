"""Leitura de arquivos de configuração e infraestrutura.

Dockerfile, compose, workflows de CI e .gitignore são lidos como texto. Nenhuma
imagem é construída, nenhum container sobe, nenhum workflow é executado.
"""

import re
from dataclasses import dataclass, field

MAX_EVIDENCE_CHARS = 200

# --- Dockerfile -------------------------------------------------------------

_FROM_RE = re.compile(r"^\s*FROM\s+(?P<image>\S+)", re.IGNORECASE | re.MULTILINE)
_USER_RE = re.compile(r"^\s*USER\s+(?P<user>\S+)", re.IGNORECASE | re.MULTILINE)
_HEALTHCHECK_RE = re.compile(r"^\s*HEALTHCHECK\b", re.IGNORECASE | re.MULTILINE)
# `ENV SENHA=...` com valor literal: credencial embutida na imagem.
_ENV_SECRET_RE = re.compile(
    r"^\s*(?:ENV|ARG)\s+(?P<nome>\w*(?:PASSWORD|SECRET|TOKEN|KEY|SENHA)\w*)"
    r"\s*[= ]\s*(?P<valor>\S+)",
    re.IGNORECASE | re.MULTILINE,
)
_ADD_REMOTE_RE = re.compile(r"^\s*ADD\s+https?://", re.IGNORECASE | re.MULTILINE)


@dataclass
class DockerfileReport:
    """O que o Dockerfile declara. `runs_as_root` é `True` quando nenhum USER
    não-root aparece — o padrão do Docker é root, então ausência é o problema."""

    base_images: list[str] = field(default_factory=list)
    final_user: str | None = None
    has_healthcheck: bool = False
    embedded_secrets: list[tuple[int, str]] = field(default_factory=list)
    remote_add: list[int] = field(default_factory=list)

    @property
    def runs_as_root(self) -> bool:
        return self.final_user is None or self.final_user in {"root", "0"}

    @property
    def uses_floating_tag(self) -> bool:
        """`latest` ou ausência de tag: a mesma build produz imagens diferentes."""
        for imagem in self.base_images:
            if imagem.startswith("$"):  # ARG, não dá para avaliar
                continue
            nome = imagem.split(" AS ")[0].split(" as ")[0].strip()
            if "@sha256:" in nome:
                continue
            tag = nome.split(":")[-1] if ":" in nome.rsplit("/", 1)[-1] else ""
            if not tag or tag == "latest":
                return True
        return False


def analyze_dockerfile(content: str) -> DockerfileReport:
    relatorio = DockerfileReport(
        base_images=[m.group("image") for m in _FROM_RE.finditer(content)],
        has_healthcheck=bool(_HEALTHCHECK_RE.search(content)),
    )

    usuarios = _USER_RE.findall(content)
    relatorio.final_user = usuarios[-1] if usuarios else None

    for numero, linha in enumerate(content.splitlines(), start=1):
        casamento = _ENV_SECRET_RE.match(linha)
        if casamento:
            valor = casamento.group("valor").strip("\"'")
            # `ENV SENHA=${VAR}` ou vazio é injeção em runtime, não valor fixo.
            if valor and not valor.startswith(("$", "${")):
                relatorio.embedded_secrets.append((numero, casamento.group("nome")))
        if _ADD_REMOTE_RE.match(linha):
            relatorio.remote_add.append(numero)

    return relatorio


# --- docker-compose ---------------------------------------------------------

_PRIVILEGED_RE = re.compile(r"^\s*privileged\s*:\s*true", re.IGNORECASE | re.MULTILINE)
# `- "0.0.0.0:5432:5432"` ou `- 5432:5432` expõe em todas as interfaces.
_OPEN_PORT_RE = re.compile(r"^\s*-\s*[\"']?(?:0\.0\.0\.0:)?(?P<host>\d{2,5}):\d{2,5}", re.MULTILINE)
_HOST_NETWORK_RE = re.compile(r"^\s*network_mode\s*:\s*[\"']?host", re.IGNORECASE | re.MULTILINE)


@dataclass
class ComposeReport:
    privileged_lines: list[int] = field(default_factory=list)
    host_network_lines: list[int] = field(default_factory=list)
    exposed_ports: list[tuple[int, str]] = field(default_factory=list)


def analyze_compose(content: str) -> ComposeReport:
    relatorio = ComposeReport()

    for numero, linha in enumerate(content.splitlines(), start=1):
        if _PRIVILEGED_RE.match(linha):
            relatorio.privileged_lines.append(numero)
        if _HOST_NETWORK_RE.match(linha):
            relatorio.host_network_lines.append(numero)
        casamento = _OPEN_PORT_RE.match(linha)
        if casamento:
            relatorio.exposed_ports.append((numero, casamento.group("host")))

    return relatorio


# --- CI ---------------------------------------------------------------------

# `uses: actions/checkout@v4` — tag móvel. `@sha` seria imutável.
_ACTION_USES_RE = re.compile(
    r"^\s*(?:-\s*)?uses\s*:\s*(?P<ref>[\w.\-]+/[\w.\-]+@\S+)", re.MULTILINE
)
_CURL_PIPE_SHELL_RE = re.compile(r"curl[^\n|]*\|\s*(?:sudo\s+)?(?:ba)?sh", re.IGNORECASE)


@dataclass
class WorkflowReport:
    unpinned_actions: list[tuple[int, str]] = field(default_factory=list)
    curl_pipe_shell: list[int] = field(default_factory=list)


def analyze_workflow(content: str) -> WorkflowReport:
    relatorio = WorkflowReport()

    for numero, linha in enumerate(content.splitlines(), start=1):
        casamento = _ACTION_USES_RE.match(linha)
        if casamento:
            ref = casamento.group("ref")
            # Só um sha completo é imutável; `@v4` pode ser reapontado.
            if not re.search(r"@[0-9a-f]{40}$", ref):
                relatorio.unpinned_actions.append((numero, ref))
        if _CURL_PIPE_SHELL_RE.search(linha):
            relatorio.curl_pipe_shell.append(numero)

    return relatorio


# --- .gitignore -------------------------------------------------------------

# Entradas cuja ausência costuma resultar em vazamento ou lixo versionado.
CRITICAL_GITIGNORE_ENTRIES = {
    ".env": ("*.env", ".env"),
    "credenciais": ("*.pem", "*.key", "id_rsa", "*.p12"),
    "dependências": ("node_modules", "venv", ".venv"),
    "cache de build": ("__pycache__", "dist", "build"),
}


def missing_gitignore_entries(content: str) -> list[str]:
    """Categorias sem nenhuma entrada correspondente."""
    linhas = {linha.strip().lstrip("/") for linha in content.splitlines() if linha.strip()}
    faltando = []
    for categoria, padroes in CRITICAL_GITIGNORE_ENTRIES.items():
        if not any(any(p in linha for linha in linhas) for p in padroes):
            faltando.append(categoria)
    return faltando
