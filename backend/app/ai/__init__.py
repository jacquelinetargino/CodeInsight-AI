"""LEGACY/OPCIONAL — integrações com provedores externos de IA.

Nada aqui é necessário para analisar um repositório: essa é a função do
CodeInsight Engine (`app/engine/`), escrito em Python e sem dependência de
serviço externo, créditos ou chave de API.

Este pacote existe para recursos complementares, todos acionados sob demanda
pelo usuário e todos degradando para "indisponível" quando não há provedor:

- explicar um achado em linguagem natural;
- resumir um relatório;
- sugerir a correção de um achado específico;
- gerar documentação (README).

Regra ao usar este pacote: se o código precisa funcionar sem IA, chame
`get_optional_ai_provider()` e trate o `None`. `get_ai_provider()` só onde a
ausência de IA é, legitimamente, um erro para o usuário.
"""
