"""Reexporta os enums de domínio, que vivem em `app.enums`.

Este módulo existe só para compatibilidade: `from app.models.enums import ...`
aparece em muitos lugares e continua funcionando.

A definição saiu daqui porque importar qualquer coisa de `app.models` dispara o
`__init__` do pacote, que carrega os modelos SQLAlchemy e, com eles, a
configuração do banco. Os enums não têm nada a ver com persistência — são tipos
de valor — e o motor de análise precisava deles sem precisar de um Postgres
configurado só para importar.
"""

from app.enums import AnalysisStatus, Dimension, Severity

__all__ = ["AnalysisStatus", "Dimension", "Severity"]
