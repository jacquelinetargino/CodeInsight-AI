"""IP do cliente para o rate limit, atrás de proxies confiáveis.

O problema: no Render a conexão chega do proxy interno, não do usuário. O
`request.client.host` é o IP desse proxy, e o slowapi o usava como chave — todos
os usuários dividiam o mesmo balde (10 logins por minuto para o site inteiro).

Por que não só `--forwarded-allow-ips` do uvicorn: com `'*'` o uvicorn devolve a
PRIMEIRA entrada do `X-Forwarded-For`, justamente a que o cliente escreve; com
uma lista, seria preciso saber os IPs internos do Render e os da Cloudflare,
que não são documentados e mudam.

A regra aqui: cada proxy confiável ACRESCENTA uma entrada no fim do
`X-Forwarded-For`. Atrás de N proxies confiáveis, a entrada N-ésima contando da
direita foi escrita pelo proxy mais externo e é o IP de quem falou com ele — o
cliente. Tudo o que o cliente forjar fica à esquerda dessa posição e nunca é
lido. Por isso N precisa ser exatamente o número de proxies que acrescentam
entradas:

- N menor que o real: a chave vira o IP de um proxy. Usuários voltam a dividir
  balde, mas ninguém burla o limite. Falha segura.
- N maior que o real: a chave cai numa posição que o cliente controla. Burlável.

Na dúvida, `TRUSTED_PROXY_HOPS=0` (o padrão): ignora o cabeçalho e usa o IP da
conexão, o comportamento de antes. A validação da cadeia real está em
`docs/proxy-ip.md`, com `GET /health/proxy`.

IPv6 entra no balde pelo /64: um único cliente costuma controlar o /64 inteiro
(2^64 endereços) e trocaria de endereço a cada tentativa.
"""

import ipaddress
from dataclasses import dataclass
from typing import Literal

from starlette.requests import Request

from app.core.config import get_settings

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# Prefixo do balde de rate limit. IPv4 fica no endereço exato: NAT de
# operadora já faz muitos usuários dividirem um IPv4, agrupar pioraria isso.
IPV6_BUCKET_PREFIX = 64
# Prefixos dos IPs mostrados pelo diagnóstico: o bastante para reconhecer a
# própria rede, sem expor o endereço inteiro de ninguém.
IPV4_MASK_PREFIX = 24
IPV6_MASK_PREFIX = 48

UNKNOWN_CLIENT = "desconhecido"


def parse_ip(raw: str | None) -> IPAddress | None:
    """IP de uma entrada de cabeçalho ou de `client.host`, ou `None`.

    Aceita `1.2.3.4`, `1.2.3.4:5678`, `::1`, `[::1]` e `[::1]:443`. IPv4
    mapeado em IPv6 (`::ffff:1.2.3.4`) volta como o IPv4 — é o mesmo cliente
    e não pode ganhar um balde à parte.
    """
    if not raw:
        return None
    valor = raw.strip().strip('"')
    if valor.startswith("["):
        fim = valor.find("]")
        if fim == -1:
            return None
        valor = valor[1:fim]
    elif valor.count(":") == 1:
        # IPv4 com porta. IPv6 sem colchetes tem dois ou mais ":".
        valor = valor.split(":", 1)[0]
    try:
        ip = ipaddress.ip_address(valor)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def forwarded_chain(request: Request) -> list[str]:
    """As entradas do `X-Forwarded-For`, na ordem, juntando várias linhas do
    cabeçalho como manda a RFC 9110 (campos repetidos equivalem a uma lista)."""
    entradas: list[str] = []
    for linha in request.headers.getlist("x-forwarded-for"):
        entradas.extend(parte.strip() for parte in linha.split(",") if parte.strip())
    return entradas


@dataclass(frozen=True)
class ClientIP:
    ip: IPAddress | None
    # De onde veio: do cabeçalho (posição confiável) ou da conexão.
    source: Literal["forwarded", "peer"]
    # O `client.host` cru quando não é IP (ex.: "testclient"), para manter a
    # chave estável mesmo assim.
    raw_peer: str | None = None


def resolve_client_ip(request: Request, trusted_hops: int) -> ClientIP:
    peer_raw = request.client.host if request.client else None
    peer = ClientIP(ip=parse_ip(peer_raw), source="peer", raw_peer=peer_raw)
    if trusted_hops <= 0:
        return peer

    cadeia = forwarded_chain(request)
    if len(cadeia) < trusted_hops:
        # Menos entradas do que proxies confiáveis: a requisição não passou pela
        # cadeia esperada (ou alguém está brincando com o cabeçalho). Nada aqui
        # é confiável — fica a conexão.
        return peer
    candidato = parse_ip(cadeia[-trusted_hops])
    if candidato is None:
        return peer
    return ClientIP(ip=candidato, source="forwarded")


def bucket_for(ip: IPAddress) -> str:
    if isinstance(ip, ipaddress.IPv6Address):
        return str(ipaddress.ip_network(f"{ip}/{IPV6_BUCKET_PREFIX}", strict=False))
    return str(ip)


def rate_limit_key(request: Request) -> str:
    """`key_func` do slowapi."""
    cliente = resolve_client_ip(request, get_settings().trusted_proxy_hops)
    if cliente.ip is not None:
        return bucket_for(cliente.ip)
    return cliente.raw_peer or UNKNOWN_CLIENT


# --- diagnóstico (GET /health/proxy) --------------------------------------------


def mask_ip(ip: IPAddress) -> str:
    prefixo = IPV6_MASK_PREFIX if isinstance(ip, ipaddress.IPv6Address) else IPV4_MASK_PREFIX
    return str(ipaddress.ip_network(f"{ip}/{prefixo}", strict=False))


def classify(ip: IPAddress | None) -> str:
    if ip is None:
        return "invalido"
    if ip.is_loopback:
        return "loopback"
    if ip.is_private or ip.is_link_local or ip.is_reserved:
        return "privado"
    return "publico"


def describe(ip: IPAddress | None) -> dict[str, str | None]:
    return {"tipo": classify(ip), "rede": mask_ip(ip) if ip is not None else None}
