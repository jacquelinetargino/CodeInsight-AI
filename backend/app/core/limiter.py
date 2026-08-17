"""Limitação de taxa por IP.

Os limites são **explícitos por rota**, via `@limiter.limit(...)`. Só as duas
que disparam chamadas caras ao provedor de IA têm limite hoje: `POST /analysis`
e `POST /analysis/{id}/fix`.

Havia aqui um `default_limits=["120/minute"]` que **nunca se aplicava**: o
`slowapi` só impõe limite padrão através do `SlowAPIMiddleware`, que a aplicação
não registra. Medido: 130 chamadas seguidas a uma rota sem decorador
responderam 200. Configuração que promete o que não acontece é pior do que
nenhuma, então saiu.

Registrar o middleware para ganhar um teto global é possível, mas é decisão de
produto e não de tipagem: a chave é o IP, então usuários atrás do mesmo NAT
dividiriam o mesmo orçamento.

`key_style="endpoint"` não é detalhe. O padrão do `slowapi` é `"url"`, que põe o
**caminho concreto** no balde do limite — e `POST /analysis/{id}/fix` tem um id
variável no caminho. O efeito medido era 20 chamadas por minuto **por análise**,
não por IP: quem tivesse dez análises fazia duzentas chamadas de IA por minuto,
enquanto a documentação prometia vinte.

`POST /analysis` não sofria disso porque o caminho é fixo, o que fez o defeito
passar despercebido: um dos dois limites funcionava como esperado.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, key_style="endpoint")
