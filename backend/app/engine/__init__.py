"""CodeInsight Engine — análise técnica de repositórios em Python puro.

Não depende de provedor de IA, créditos ou serviço externo: tudo aqui é análise
estática, AST, regras e heurísticas. Os provedores em `app/ai/` são opcionais e
servem apenas a recursos complementares.

Premissa que vale para todo o pacote: **o repositório analisado é dado não
confiável**. Nada dele é executado, importado, interpretado como instrução ou
tratado como caminho seguro.
"""
