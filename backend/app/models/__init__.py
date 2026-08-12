"""Importa todos os modelos para que fiquem registrados no Base.metadata
(necessário para o autogenerate do Alembic e para a resolução das relationships)."""

from app.models.analysis import Analysis, AnalysisResult  # noqa: F401
from app.models.enums import AnalysisStatus, Dimension, Severity  # noqa: F401
from app.models.fix_suggestion import FixSuggestion  # noqa: F401
from app.models.github_credential import GithubCredential  # noqa: F401
from app.models.readme import GeneratedReadme  # noqa: F401
from app.models.repository import Repository  # noqa: F401
from app.models.suggestion import Suggestion  # noqa: F401
from app.models.user import User  # noqa: F401
