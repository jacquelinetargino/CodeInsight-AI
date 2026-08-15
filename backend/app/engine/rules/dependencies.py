"""Leitura de manifestos de dependência.

Todos os formatos são lidos como **dado**: nada é instalado, resolvido ou
executado. Não roda `pip`, `npm`, `go`, `cargo` nem `mvn` — o motor não pode
depender de gerenciador de pacote instalado, e executar um deles sobre um
repositório de terceiros seria entregar a máquina.

Uma escolha vale explicação: `pom.xml` e `build.gradle` são lidos por expressão
regular, não por parser de XML. `xml.etree` sobre entrada não confiável abre
porta para expansão de entidades ("billion laughs"), e extrair blocos
`<dependency>` com regex não tem essa superfície.
"""

import json
import re
import tomllib
from dataclasses import dataclass, field

# Faixas que aceitam qualquer versão futura. Não são erro por si — são risco de
# build irreprodutível.
_LOOSE_SPEC_RE = re.compile(r"^\s*(?:\*|latest|x|\^|~|>=?|>)")
_GIT_SOURCE_RE = re.compile(r"(?:git\+|git@|github\.com|gitlab\.com|bitbucket\.org)", re.IGNORECASE)
_HTTP_SOURCE_RE = re.compile(r"http://", re.IGNORECASE)

# Comentário e linha vazia em requirements.txt / go.mod.
_COMMENT_RE = re.compile(r"^\s*(#|//)")

# `nome==1.2.3`, `nome>=1.0`, `nome[extra]==1.0`, `nome ; marker`
_REQUIREMENT_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*(?P<spec>[^;#]*)",
)


@dataclass(frozen=True)
class Dependency:
    """Uma dependência declarada. `spec` é a restrição de versão como escrita."""

    name: str
    spec: str
    manifest: str
    ecosystem: str
    line: int = 0

    @property
    def is_pinned(self) -> bool:
        """Fixada é `==1.2.3` (Python), `1.2.3` exato (npm/cargo) ou `v1.2.3`
        (Go). Faixa aberta e ausência de versão não contam."""
        spec = self.spec.strip()
        if not spec:
            return False
        if spec.startswith("=="):
            return True
        return bool(re.fullmatch(r"v?\d+(?:\.\d+)*(?:[-+][\w.]+)?", spec))

    @property
    def has_git_source(self) -> bool:
        return bool(_GIT_SOURCE_RE.search(self.spec))

    @property
    def has_insecure_source(self) -> bool:
        return bool(_HTTP_SOURCE_RE.search(self.spec))


@dataclass
class ManifestReport:
    """Dependências encontradas e problemas de leitura.

    `parse_error` separa "manifesto sem dependências" de "manifesto que não deu
    para ler" — tratar os dois como iguais esconderia um repositório mal formado.
    """

    dependencies: list[Dependency] = field(default_factory=list)
    parse_error: str | None = None


# --- Python -----------------------------------------------------------------


def parse_requirements(content: str, manifest: str = "requirements.txt") -> ManifestReport:
    relatorio = ManifestReport()

    for numero, linha in enumerate(content.splitlines(), start=1):
        texto = linha.strip()
        if not texto or _COMMENT_RE.match(texto):
            continue
        # `-r outro.txt`, `-e .`, `--index-url ...` não são dependências.
        if texto.startswith("-"):
            continue

        casamento = _REQUIREMENT_RE.match(texto)
        if not casamento:
            continue

        relatorio.dependencies.append(
            Dependency(
                name=casamento.group("name"),
                spec=casamento.group("spec").strip(),
                manifest=manifest,
                ecosystem="python",
                line=numero,
            )
        )

    return relatorio


def parse_pyproject(content: str, manifest: str = "pyproject.toml") -> ManifestReport:
    """`tomllib` só lê dados — não há execução, diferente de `setup.py`."""
    relatorio = ManifestReport()
    try:
        dados = tomllib.loads(content)
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        relatorio.parse_error = f"TOML inválido: {exc}"
        return relatorio

    brutas: list[str] = list(dados.get("project", {}).get("dependencies", []) or [])
    for grupo in (dados.get("project", {}).get("optional-dependencies", {}) or {}).values():
        brutas.extend(grupo or [])

    for bruta in brutas:
        if not isinstance(bruta, str):
            continue
        casamento = _REQUIREMENT_RE.match(bruta)
        if casamento:
            relatorio.dependencies.append(
                Dependency(
                    name=casamento.group("name"),
                    spec=casamento.group("spec").strip(),
                    manifest=manifest,
                    ecosystem="python",
                )
            )

    return relatorio


# --- JavaScript -------------------------------------------------------------


def parse_package_json(content: str, manifest: str = "package.json") -> ManifestReport:
    relatorio = ManifestReport()
    try:
        dados = json.loads(content)
    except (json.JSONDecodeError, ValueError) as exc:
        relatorio.parse_error = f"JSON inválido: {exc}"
        return relatorio

    if not isinstance(dados, dict):
        relatorio.parse_error = "package.json não contém um objeto"
        return relatorio

    for chave in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        bloco = dados.get(chave)
        if not isinstance(bloco, dict):
            continue
        for nome, spec in bloco.items():
            relatorio.dependencies.append(
                Dependency(
                    name=str(nome),
                    spec=str(spec),
                    manifest=manifest,
                    ecosystem="javascript",
                )
            )

    return relatorio


# --- Go, Rust, Java ---------------------------------------------------------

_GO_REQUIRE_RE = re.compile(r"^\s*(?P<name>[\w./\-]+)\s+(?P<spec>v[\w.\-+]+)")


def parse_go_mod(content: str, manifest: str = "go.mod") -> ManifestReport:
    relatorio = ManifestReport()
    dentro_do_bloco = False

    for numero, linha in enumerate(content.splitlines(), start=1):
        texto = linha.strip()
        if _COMMENT_RE.match(texto):
            continue

        if texto.startswith("require ("):
            dentro_do_bloco = True
            continue
        if dentro_do_bloco and texto == ")":
            dentro_do_bloco = False
            continue

        alvo = texto
        if texto.startswith("require "):
            alvo = texto[len("require ") :]
        elif not dentro_do_bloco:
            continue

        casamento = _GO_REQUIRE_RE.match(alvo)
        if casamento:
            relatorio.dependencies.append(
                Dependency(
                    name=casamento.group("name"),
                    spec=casamento.group("spec"),
                    manifest=manifest,
                    ecosystem="go",
                    line=numero,
                )
            )

    return relatorio


def parse_cargo_toml(content: str, manifest: str = "Cargo.toml") -> ManifestReport:
    relatorio = ManifestReport()
    try:
        dados = tomllib.loads(content)
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        relatorio.parse_error = f"TOML inválido: {exc}"
        return relatorio

    for chave in ("dependencies", "dev-dependencies", "build-dependencies"):
        bloco = dados.get(chave)
        if not isinstance(bloco, dict):
            continue
        for nome, valor in bloco.items():
            # Pode ser `serde = "1.0"` ou `serde = { version = "1.0" }`.
            if isinstance(valor, str):
                spec = valor
            elif isinstance(valor, dict):
                spec = str(valor.get("version", valor.get("git", "")))
            else:
                spec = ""
            relatorio.dependencies.append(
                Dependency(name=str(nome), spec=spec, manifest=manifest, ecosystem="rust")
            )

    return relatorio


# Blocos <dependency> extraídos por regex, sem parser de XML: ver docstring do
# módulo.
_MAVEN_DEP_RE = re.compile(r"<dependency>(.*?)</dependency>", re.DOTALL | re.IGNORECASE)
_MAVEN_FIELD_RE = {
    "artifactId": re.compile(r"<artifactId>\s*([^<]+?)\s*</artifactId>", re.IGNORECASE),
    "version": re.compile(r"<version>\s*([^<]+?)\s*</version>", re.IGNORECASE),
}


def parse_pom_xml(content: str, manifest: str = "pom.xml") -> ManifestReport:
    relatorio = ManifestReport()

    for bloco in _MAVEN_DEP_RE.findall(content):
        nome = _MAVEN_FIELD_RE["artifactId"].search(bloco)
        versao = _MAVEN_FIELD_RE["version"].search(bloco)
        if not nome:
            continue
        relatorio.dependencies.append(
            Dependency(
                name=nome.group(1),
                spec=versao.group(1) if versao else "",
                manifest=manifest,
                ecosystem="java",
            )
        )

    return relatorio


_GRADLE_DEP_RE = re.compile(
    r"""(?:implementation|api|compile|testImplementation|runtimeOnly)\s*\(?\s*['"]"""
    r"""(?P<group>[^:'"]+):(?P<name>[^:'"]+)(?::(?P<spec>[^'"]*))?['"]""",
)


def parse_build_gradle(content: str, manifest: str = "build.gradle") -> ManifestReport:
    relatorio = ManifestReport()

    for numero, linha in enumerate(content.splitlines(), start=1):
        if _COMMENT_RE.match(linha.strip()):
            continue
        casamento = _GRADLE_DEP_RE.search(linha)
        if casamento:
            relatorio.dependencies.append(
                Dependency(
                    name=casamento.group("name"),
                    spec=(casamento.group("spec") or "").strip(),
                    manifest=manifest,
                    ecosystem="java",
                    line=numero,
                )
            )

    return relatorio


# --- despacho ---------------------------------------------------------------

# Nome do arquivo -> parser. O analyzer usa isto para saber o que sabe ler.
MANIFEST_PARSERS = {
    "requirements.txt": parse_requirements,
    "requirements-dev.txt": parse_requirements,
    "pyproject.toml": parse_pyproject,
    "package.json": parse_package_json,
    "go.mod": parse_go_mod,
    "Cargo.toml": parse_cargo_toml,
    "pom.xml": parse_pom_xml,
    "build.gradle": parse_build_gradle,
}

# Manifesto -> arquivo de lock esperado. Sem lock, uma faixa de versão vira
# build diferente a cada instalação.
LOCK_FILES = {
    "package.json": ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"),
    "pyproject.toml": ("poetry.lock", "uv.lock", "pdm.lock", "requirements.txt"),
    "Cargo.toml": ("Cargo.lock",),
    "go.mod": ("go.sum",),
}


def parse_manifest(filename: str, content: str) -> ManifestReport | None:
    """Lê um manifesto conhecido; devolve `None` para arquivo que não é manifesto."""
    parser = MANIFEST_PARSERS.get(filename)
    if parser is None:
        return None
    return parser(content, filename)
