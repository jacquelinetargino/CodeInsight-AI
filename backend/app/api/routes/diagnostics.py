"""`GET /health/proxy`: a forma da cadeia de proxies, para validar
`TRUSTED_PROXY_HOPS` antes de ativá-lo (ver `docs/proxy-ip.md`).

Desligado por padrão (`PROXY_DIAGNOSTICS_ENABLED=false` responde 404). Ligado,
mostra a QUEM CHAMA a sua própria requisição: quantas entradas o
`X-Forwarded-For` tem, de que tipo é cada uma e a rede delas (IPv4 /24, IPv6
/48) — nunca um IP completo. Nada é gravado em log.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.client_ip import describe, forwarded_chain, parse_ip, resolve_client_ip
from app.core.config import get_settings
from app.core.limiter import limiter

router = APIRouter(tags=["diagnostics"])

# Um cabeçalho com milhares de entradas não vira uma resposta de milhares de
# linhas. Uma cadeia real tem duas ou três.
MAX_ENTRADAS_MOSTRADAS = 10


@router.get("/health/proxy", include_in_schema=False)
@limiter.limit("10/minute")
async def proxy_diagnostics(request: Request, response: Response) -> dict[str, Any]:
    settings = get_settings()
    if not settings.proxy_diagnostics_enabled:
        # Igual a uma rota inexistente: desligado, o endpoint não se anuncia.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")

    response.headers["Cache-Control"] = "no-store"
    cadeia = forwarded_chain(request)
    total = len(cadeia)
    entradas = [
        {"posicao_da_direita": total - indice, **describe(parse_ip(valor))}
        for indice, valor in enumerate(cadeia)
    ][-MAX_ENTRADAS_MOSTRADAS:]
    cliente = resolve_client_ip(request, settings.trusted_proxy_hops)

    return {
        "trusted_proxy_hops": settings.trusted_proxy_hops,
        "conexao": describe(parse_ip(request.client.host if request.client else None)),
        "x_forwarded_for": {"total": total, "entradas": entradas},
        "chave_do_rate_limit": {"origem": cliente.source, **describe(cliente.ip)},
        "como_ler": (
            "Compare a 'rede' de cada entrada com a rede do seu próprio IP público. "
            "A posicao_da_direita onde ele aparece é o valor candidato de "
            "TRUSTED_PROXY_HOPS — confirme com um X-Forwarded-For falso antes de "
            "ativar. Desligue PROXY_DIAGNOSTICS_ENABLED ao terminar."
        ),
    }
