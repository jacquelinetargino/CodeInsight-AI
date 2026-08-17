import enum


class AnalysisStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Dimension(str, enum.Enum):
    """Dimensões persistidas em `analysis_results.dimension`.

    Espelham `app.engine.findings.FindingCategory` valor a valor. São dois enums
    porque o motor não deve depender da camada de banco, mas divergirem seria um
    bug: `tests/test_engine_scoring.py` falha se saírem de sincronia.
    """

    SECURITY = "security"
    QUALITY = "quality"
    ARCHITECTURE = "architecture"
    DEPENDENCIES = "dependencies"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    GIT = "git"
    CONFIGURATION = "configuration"


class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
