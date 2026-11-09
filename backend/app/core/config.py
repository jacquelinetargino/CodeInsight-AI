from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _adapt_libpq_params(url: str) -> str:
    """Traduz parâmetros de query do libpq para os que o asyncpg entende.

    O Neon (e outros) entregam `?sslmode=require&channel_binding=require`, mas o
    asyncpg recusa `sslmode` e `channel_binding` com TypeError ao conectar; o
    equivalente dele é `ssl=<modo>`.
    """
    parts = urlsplit(url)
    if not parts.query:
        return url
    params = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "channel_binding":
            continue
        params.append(("ssl", value) if key == "sslmode" else (key, value))
    return urlunsplit(parts._replace(query=urlencode(params)))


def _origin_of(url: str) -> str:
    """`https://site.com/qualquer/caminho` → `https://site.com` (o que o
    navegador manda em `Origin`). Sem esquema, devolve o texto como veio."""
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return url.strip()
    return f"{parts.scheme}://{parts.netloc}"


GOOGLE_CLIENT_ID_SUFFIX = ".apps.googleusercontent.com"


def _looks_like_url_or_blank(value: str) -> bool:
    return not value or "://" in value or "/" in value or any(c.isspace() for c in value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "CodeInsight AI"
    api_v1_prefix: str = "/api/v1"
    # Aceita várias origens separadas por vírgula: em produção o front tem mais
    # de um domínio (aliases da Vercel) e ainda queremos permitir o dev local.
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    @property
    def cors_origins(self) -> list[str]:
        """Origens liberadas no CORS: as de FRONTEND_URL e a de PUBLIC_FRONTEND_URL.

        PUBLIC_FRONTEND_URL entra sempre: é para lá que o e-mail de redefinição
        e o login social mandam a pessoa, então o site nesse endereço PRECISA
        conseguir chamar a API. Foi esse descompasso que quebrou o "esqueci a
        senha" no domínio próprio: o site novo existia, o CORS não o conhecia, o
        navegador barrava o pedido e a tela só dizia "Tente novamente".

        A barra final sai porque o navegador manda `Origin` sem ela — com
        `https://site.com/` na lista, nenhuma origem casaria."""
        candidatas = self.frontend_url.split(",")
        if self.public_frontend_url_override:
            candidatas.append(_origin_of(self.public_frontend_url_override))
        origens: list[str] = []
        for candidata in candidatas:
            origem = candidata.strip().rstrip("/")
            if origem and origem not in origens:
                origens.append(origem)
        return origens

    database_url: str

    @field_validator("database_url")
    @classmethod
    def _force_asyncpg_driver(cls, v: str) -> str:
        # Provedores gerenciados (Render, Heroku etc.) entregam a connection
        # string sem o driver explícito — o SQLAlchemy async precisa de +asyncpg.
        if v.startswith("postgres://"):
            v = "postgresql+asyncpg://" + v[len("postgres://") :]
        elif v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://") :]
        return _adapt_libpq_params(v)

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Criptografa PATs do GitHub em repouso (Fernet).
    encryption_key: str

    # Token opcional do servidor, usado como fallback para repositórios públicos
    # quando o usuário não conectou seu próprio PAT (evita o rate limit de 60/h
    # de requisições não autenticadas na GitHub API).
    github_token: str | None = None

    # --- E-mail (OPCIONAL — só para "esqueci a senha") ---
    # Envio por API HTTP, não SMTP: o plano gratuito do Render bloqueia as
    # portas 25/465/587. Sem provedor, a recuperação de senha responde 503 e o
    # resto da aplicação não muda.
    email_provider: str | None = None  # brevo
    brevo_api_key: str | None = None
    # Remetente; precisa estar verificado no provedor.
    email_from: str | None = None
    email_from_name: str = "CodeInsight AI"
    password_reset_expire_minutes: int = 30
    # Intervalo mínimo entre dois e-mails de redefinição para a MESMA conta. O
    # limite por IP da rota não impede que vários IPs encham a caixa de alguém.
    password_reset_cooldown_seconds: int = 60

    # Base dos links que saem do backend para o navegador (e-mail de
    # redefinição, retorno do login social). Sem valor, vale a primeira origem
    # de FRONTEND_URL — o que quebra em silêncio se a lista começar por
    # http://localhost. Definir explicitamente remove essa dependência de ordem.
    public_frontend_url_override: str | None = Field(default=None, alias="PUBLIC_FRONTEND_URL")

    # --- Login social (OPCIONAL) ---
    # Cada provedor só aparece habilitado com id E secret definidos. Os secrets
    # existem só aqui, no backend: o navegador nunca os vê.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    # Nome com OAUTH de propósito: não confundir com GITHUB_TOKEN (PAT do
    # servidor para a API) nem com o PAT que cada usuário cola nas
    # configurações. Este app OAuth serve SÓ para identificar quem entra.
    github_oauth_client_id: str | None = None
    github_oauth_client_secret: str | None = None
    # Validade do "state" + PKCE guardados no cookie durante a ida ao provedor.
    oauth_state_max_age_seconds: int = 600

    # --- IP do cliente para o rate limit (ver app/core/client_ip.py) ---
    # Quantos proxies CONFIÁVEIS acrescentam entradas ao X-Forwarded-For antes
    # de a requisição chegar aqui. 0 = ignora o cabeçalho e usa o IP da conexão
    # (dev local, Docker Compose, testes). Errar para MAIS é perigoso: a chave
    # passa a ser uma posição que o cliente controla. Só ative depois de validar
    # a cadeia real com PROXY_DIAGNOSTICS_ENABLED (docs/proxy-ip.md).
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)
    # Liga GET /health/proxy, que mostra a forma da cadeia de proxies com os IPs
    # mascarados. Desligado por padrão; ligue só durante a validação.
    proxy_diagnostics_enabled: bool = False

    # --- Provedor de IA (LEGACY/OPCIONAL) ---
    # A análise principal é feita pelo CodeInsight Engine, em Python, sem IA
    # externa. Estes campos servem apenas a recursos complementares (explicar
    # achados, resumir relatório, sugerir correções, gerar documentação) e por
    # isso não têm valor obrigatório: a aplicação sobe sem nenhum deles.
    ai_provider: str = "claude"  # claude | openai | gemini | groq | local
    ai_api_key: str | None = None
    # Sem valor, cada provider usa o próprio `default_model`. Um padrão único
    # aqui (era "claude-sonnet-5") ia parar na Groq ao trocar só AI_PROVIDER.
    ai_model: str | None = None
    # Necessário para "local" (ex.: http://localhost:11434/v1 no Ollama) e
    # opcional para apontar os demais para um endpoint compatível custom
    # (para "groq", o padrão já é https://api.groq.com/openai/v1).
    ai_base_url: str | None = None
    # Teto do bloco de contexto enviado em cada prompt de análise. Existe porque
    # provedores cobram/limitam por tokens/minuto: uma análise dispara ~7
    # chamadas em sequência, então o contexto precisa caber no orçamento do
    # plano. ~4 caracteres por token serve de regra de bolso.
    ai_max_context_chars: int = 100_000

    # --- CodeInsight Engine: limites de recurso ---
    # O repositório analisado é dado NÃO CONFIÁVEL: pode ser gigante, ter milhões
    # de arquivos ou expandir mil vezes ao descomprimir. Cada limite abaixo cobre
    # um desses vetores e é ajustável por variável de ambiente.

    # Teto real sobre os bytes baixados. Precisa ser contado durante o streaming
    # porque o GitHub responde com transfer-encoding chunked, sem Content-Length.
    engine_max_archive_bytes: int = 50 * 1024 * 1024

    # Teto independente sobre o conteúdo descomprimido. Limitar só o download não
    # protege: gzip chega a expandir ~1000:1, então 50 MB comprimidos poderiam
    # virar dezenas de GB em disco.
    #
    # NOTA: este valor é conservador por precaução, não medido. O ambiente de
    # execução (FastAPI Cloud) não documenta o tamanho do disco efêmero. Se for
    # preciso analisar repositórios maiores, meça o espaço disponível antes de
    # aumentar.
    engine_max_uncompressed_bytes: int = 200 * 1024 * 1024

    engine_max_files: int = 20_000

    # Arquivo acima disso é pulado, não derruba a análise: bundles minificados
    # são grandes e legitimamente inúteis para análise estática.
    engine_max_file_bytes: int = 2 * 1024 * 1024

    # Teto de tempo da análise. Medido numa máquina de desenvolvimento:
    # django/django (7008 arquivos) leva ~116s, fastapi/fastapi (3137) ~61s.
    # Com 120s o maior deles ficava sem margem alguma, e um servidor mais lento
    # o mataria no meio.
    #
    # A análise roda em thread (ver `pipeline.analyze_repository`), então esperar
    # mais não bloqueia o event loop que atende as requisições — o custo de
    # aumentar é uma thread ocupada por mais tempo, não indisponibilidade.
    engine_max_analysis_seconds: int = 300

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def email_configured(self) -> bool:
        provider = (self.email_provider or "").lower().strip()
        return provider == "brevo" and bool(self.brevo_api_key) and bool(self.email_from)

    @property
    def public_frontend_url(self) -> str:
        """Base dos links enviados ao navegador: PUBLIC_FRONTEND_URL, ou a
        primeira origem de FRONTEND_URL."""
        if self.public_frontend_url_override and self.public_frontend_url_override.strip():
            return self.public_frontend_url_override.strip().rstrip("/")
        return self.cors_origins[0].rstrip("/") if self.cors_origins else ""

    @property
    def google_client_id_valid(self) -> bool:
        """Um ID de cliente do Google sempre termina em `.apps.googleusercontent.com`.

        Existe porque um valor trocado passa despercebido: em produção a variável
        recebeu a URL de callback, o botão aparecia habilitado e todo login
        terminava em `invalid_client` na tela do Google."""
        cid = (self.google_client_id or "").strip()
        return cid.endswith(GOOGLE_CLIENT_ID_SUFFIX) and not _looks_like_url_or_blank(cid)

    @property
    def github_client_id_valid(self) -> bool:
        """O GitHub não documenta um formato fixo (`Iv1.…`, `Ov23li…`), mas um ID
        nunca é URL nem tem espaço — o mesmo erro de colar o valor errado."""
        cid = (self.github_oauth_client_id or "").strip()
        return bool(cid) and not _looks_like_url_or_blank(cid)

    @property
    def google_oauth_configured(self) -> bool:
        # Com o ID inválido, o provedor fica DESLIGADO: botão desabilitado em vez
        # de um fluxo que sempre falha na tela do Google.
        return self.google_client_id_valid and bool(self.google_client_secret)

    @property
    def github_oauth_configured(self) -> bool:
        return self.github_client_id_valid and bool(self.github_oauth_client_secret)

    def oauth_callback_url(self, provider: str) -> str:
        """URL de retorno registrada no provedor. Precisa bater caractere por
        caractere com a cadastrada no Google Cloud / GitHub."""
        return f"{self.backend_url.rstrip('/')}{self.api_v1_prefix}/auth/oauth/{provider}/callback"

    @property
    def cookies_secure(self) -> bool:
        """`Secure` sempre que o backend é servido por HTTPS. Em http://localhost
        o navegador descartaria um cookie Secure e o login social não fecharia."""
        return self.is_production or self.backend_url.startswith("https://")

    @property
    def ai_configured(self) -> bool:
        """Se há um provedor de IA utilizável. Para `local` o que importa é o
        endpoint, não a chave — servidores locais (Ollama, LM Studio) aceitam
        qualquer valor de API key."""
        if self.ai_provider.lower().strip() == "local":
            return bool(self.ai_base_url)
        return bool(self.ai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
