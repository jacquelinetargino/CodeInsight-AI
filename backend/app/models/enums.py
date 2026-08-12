import enum


class AnalysisStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Dimension(str, enum.Enum):
    SECURITY = "security"
    QUALITY = "quality"
    ARCHITECTURE = "architecture"
    DOCUMENTATION = "documentation"
    TESTS = "tests"
    GIT = "git"


class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
