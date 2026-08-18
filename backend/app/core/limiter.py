"""Limitação de taxa por IP.

Os limites são **explícitos por rota**, via `@limiter.limit(...)`. Têm limite
hoje as duas rotas que disparam chamadas caras ao provedor de IA (`POST
/analysis`, `POST /analysis/{id}/fix`) e as duas rotas de autenticação abertas
ao público (`POST /auth/login`, `POST /auth/register`).

O limite do login não é orçamento de custo, é a única barreira contra
adivinhação de senha: medido, 60 tentativas seguidas contra a mesma conta
respondiam 401 e nenhuma 429. Cada tentativa contra uma conta existente também
custa ~210 ms de CPU do servidor (o `verify_password` do bcrypt), então a rota
servia de alavanca de exaustão sem sequer precisar de credencial.

**O que este limite não resolve:** a chave é o IP, então um atacante distribuído
continua tendo 10 tentativas por minuto *por endereço*. Barrar isso exigiria
contagem por conta em armazenamento compartilhado — ver a limitação de memória
descrita abaixo.

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
