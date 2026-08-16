"""Detecção de credenciais em código, com mascaramento obrigatório.

Regra que vale para o módulo inteiro: **o segredo completo nunca sai daqui**.
O mascaramento acontece na detecção, antes de qualquer `Finding` existir — não
na camada de exibição. Assim não há caminho em que um segredo real seja
persistido no banco, escrito em log ou devolvido pela API.

A detecção é determinística: expressões regulares explícitas por provedor, sem
inferência estatística. Cada padrão é uma linha auditável, e cada um carrega a
confiança que merece — um prefixo específico como `AKIA` quase não erra, uma
atribuição genérica de `password = "..."` erra bastante.
"""

import re
from dataclasses import dataclass

# Quanto do segredo permanece visível. Serve para o humano reconhecer qual
# credencial é (o prefixo identifica o provedor) sem que ela seja utilizável.
VISIBLE_PREFIX_CHARS = 4
MASK_LENGTH = 8

# Valores que parecem credencial mas são convite para preencher. Sem isso o
# detector acusaria o próprio `.env.example` de qualquer projeto.
_PLACEHOLDER_RE = re.compile(
    r"^(?:x{3,}|y{3,}|\.{3,}|-{3,}|_{3,}|0{3,}|1{3,}|"
    r"changeme|change[-_]me|placeholder|example|sample|dummy|fake|test|testing|"
    # Prefixos de convite ("your-secret-here", "replace-with-your-key") vêm
    # seguidos de outras palavras, então o resto do valor também é consumido.
    r"(?:your|my|our|insert|replace|enter|add|set|put)[-_ ][\w\- ]*|"
    r"todo|tbd|none|null|nil|undefined|"
    r"secret|password|token|apikey|api[-_]key|value|string|"
    # Genéricos de documentação, em inglês e português. `user:pass@host` e
    # `USUARIO:SENHA@host` são a forma canônica de escrever um exemplo de
    # string de conexão — acusá-los treina o usuário a ignorar o relatório.
    r"pass|passwd|senha|usuario|usuário|user|username|login|"
    r"foo|bar|baz|abc123|123456|admin|root|hostname|host|dbname|database)$",
    re.IGNORECASE,
)

# Interpolação de variável: `${VAR}`, `$VAR`, `{{ var }}`, `%(var)s`, `<valor>`.
# Isto não é uma credencial fixa — é a ausência de uma. O `docker-compose.yml`
# deste projeto era acusado por conter `${POSTGRES_PASSWORD}`, que é exatamente
# a prática recomendada.
_INTERPOLATION_RE = re.compile(
    r"^(?:\$\{[^}]*\}|\$[A-Za-z_]\w*|\{\{[^}]*\}\}|%\([^)]*\)s|%s|<[^>]*>)$"
)

# O detector mascara o que encontra; a evidência mascarada acaba citada em
# documentação e em teste. Reencontrá-la e reportá-la seria o detector se
# acusando a si próprio.
_ALREADY_MASKED_RE = re.compile(r"\*{4,}")


@dataclass(frozen=True)
class SecretPattern:
    """Um padrão de credencial. `confidence` reflete quão específico ele é."""

    name: str
    regex: re.Pattern[str]
    confidence: float
    description: str


@dataclass(frozen=True)
class SecretMatch:
    """Ocorrência encontrada. Guarda apenas a forma **mascarada** — o valor
    original não é retido em lugar nenhum."""

    pattern_name: str
    line: int
    masked_evidence: str
    confidence: float
    description: str


def _p(name: str, pattern: str, confidence: float, description: str) -> SecretPattern:
    return SecretPattern(name, re.compile(pattern), confidence, description)


# Prefixos proprietários primeiro: são os que praticamente não geram falso
# positivo, porque o formato é atribuído pelo próprio provedor.
SECRET_PATTERNS: list[SecretPattern] = [
    _p("aws-access-key", r"\bAKIA[0-9A-Z]{16}\b", 0.98, "Chave de acesso da AWS"),
    _p("github-pat-classic", r"\bghp_[A-Za-z0-9]{36}\b", 0.98, "Token pessoal do GitHub"),
    _p("github-pat-fine", r"\bgithub_pat_[A-Za-z0-9_]{22,}", 0.98, "Token pessoal do GitHub"),
    _p("github-oauth", r"\bgho_[A-Za-z0-9]{36}\b", 0.98, "Token OAuth do GitHub"),
    _p("anthropic-key", r"\bsk-ant-[A-Za-z0-9_\-]{20,}", 0.98, "Chave da API da Anthropic"),
    _p("openai-key", r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}", 0.95, "Chave da API da OpenAI"),
    _p("groq-key", r"\bgsk_[A-Za-z0-9]{20,}", 0.95, "Chave da API da Groq"),
    _p("google-api-key", r"\bAIza[0-9A-Za-z_\-]{35}\b", 0.95, "Chave de API do Google"),
    _p("slack-token", r"\bxox[baprs]-[A-Za-z0-9\-]{10,}", 0.95, "Token do Slack"),
    _p("stripe-secret", r"\b[sr]k_live_[A-Za-z0-9]{20,}", 0.98, "Chave secreta do Stripe"),
    _p("supabase-secret", r"\bsb_secret_[A-Za-z0-9_\-]{20,}", 0.95, "Chave secreta do Supabase"),
    _p(
        "sendgrid-key", r"\bSG\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}", 0.95, "Chave do SendGrid"
    ),
    _p(
        "private-key",
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",
        0.99,
        "Chave privada embutida no repositório",
    ),
    _p(
        "jwt",
        r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
        0.90,
        "JSON Web Token",
    ),
    # A senha é capturada em grupo para passar pela checagem de placeholder:
    # `postgres://user:changeme@host` é exemplo de documentação, não vazamento.
    # Capturar também melhora a evidência — mascara só a senha, preservando
    # host e usuário como contexto.
    _p(
        "database-url-with-password",
        r"\b(?:postgres|postgresql|mysql|mongodb|redis|amqp)(?:\+\w+)?://[^\s:@/]+:([^\s@/]+)@",
        0.90,
        "URL de conexão com credencial embutida",
    ),
    # Atribuição genérica: erra mais, então entra com confiança baixa e exige
    # um valor com tamanho plausível entre aspas.
    _p(
        "generic-assignment",
        r"(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
        r"private[_-]?key|client[_-]?secret)\b\s*[:=]\s*[\"']([^\"'\s]{8,})[\"']",
        0.55,
        "Credencial atribuída diretamente no código",
    ),
]


def mask_secret(value: str) -> str:
    """Reduz a credencial a uma forma reconhecível mas inutilizável.

    Mantém um prefixo curto — é ele que diz *qual* credencial é — e substitui o
    resto por um número fixo de asteriscos, sem revelar o comprimento real.
    Segredos muito curtos são mascarados por inteiro.
    """
    if not value:
        return ""
    if len(value) <= VISIBLE_PREFIX_CHARS:
        return "*" * MASK_LENGTH
    return value[:VISIBLE_PREFIX_CHARS] + "*" * MASK_LENGTH


def mask_line(line: str, secret: str) -> str:
    """Mascara a credencial dentro da linha, preservando o contexto ao redor.

    É o que vira `evidence` no achado: os primeiros caracteres do valor são
    preservados e o resto vira asteriscos, mostrando onde está o problema — e
    qual provedor emitiu a credencial — sem entregar a credencial em si.

    O exemplo fica de fora de propósito: escrever um valor com forma de chave
    real dentro da documentação é exatamente a prática que esta regra alerta.
    """
    if not secret:
        return line.strip()
    return line.replace(secret, mask_secret(secret)).strip()


def _is_placeholder(value: str) -> bool:
    """Um valor que parece credencial mas não é uma.

    Três famílias: convite para preencher (`changeme`, `your-key-here`),
    interpolação de variável (`${VAR}`) e evidência já mascarada pelo próprio
    detector. Nenhuma delas é um segredo vazado, e reportá-las é o caminho mais
    curto para o usuário parar de ler o relatório.
    """
    valor = value.strip()
    return bool(
        _PLACEHOLDER_RE.match(valor)
        or _INTERPOLATION_RE.match(valor)
        or _ALREADY_MASKED_RE.search(valor)
    )


def detect_secrets(content: str) -> list[SecretMatch]:
    """Varre um texto e devolve as ocorrências já mascaradas.

    Recebe conteúdo como texto puro: nada é executado, importado ou
    interpretado. A mesma linha pode acionar mais de um padrão, mas cada padrão
    reporta uma ocorrência por linha para não inundar o relatório.
    """
    matches: list[SecretMatch] = []

    for line_number, line in enumerate(content.splitlines(), start=1):
        for pattern in SECRET_PATTERNS:
            found = pattern.regex.search(line)
            if not found:
                continue

            # Padrões com grupo de captura isolam o valor; os demais casam o
            # segredo inteiro.
            secret = found.group(1) if found.groups() else found.group(0)
            if _is_placeholder(secret):
                continue

            matches.append(
                SecretMatch(
                    pattern_name=pattern.name,
                    line=line_number,
                    masked_evidence=mask_line(line, secret),
                    confidence=pattern.confidence,
                    description=pattern.description,
                )
            )

    return matches
