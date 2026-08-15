"""Catálogo de regras do CodeInsight Engine.

Cada regra é um dado declarativo — id, categoria, severidade, recomendação e
confiança — separado do código que a detecta. Isso mantém o catálogo auditável
(dá para listar tudo que o motor procura sem ler implementação) e permite
desabilitar uma regra sem tocar no analyzer.
"""

from app.engine.rules.registry import Rule, RuleRegistry, registry

__all__ = ["Rule", "RuleRegistry", "registry"]
