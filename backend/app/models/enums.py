import enum


class ArtifactType(str, enum.Enum):
    PROSE = "prose"
    CODE = "code"


class ArtifactStatus(str, enum.Enum):
    DRAFTING = "drafting"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    CANCELLED = "cancelled"


class WaveStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WaveTrigger(str, enum.Enum):
    INITIAL = "initial"
    ITERATION = "iteration"
    RETRY = "retry"


class CommentSource(str, enum.Enum):
    IN_APP = "in_app"
    GITHUB_PR = "github_pr"
    GITLAB_MR = "gitlab_mr"


class SkillCategory(str, enum.Enum):
    SKILL = "skill"
    WORK_LEARNING = "work_learning"
    BRIEFING = "briefing"


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class AgentRole(str, enum.Enum):
    LEAD = "lead"
    WORKER = "worker"


class AgentStatus(str, enum.Enum):
    LEARNING = "learning"
    READY = "ready"
    WORKING = "working"
    REFLECTING = "reflecting"


class ProgressionLevel(str, enum.Enum):
    APPRENTI = "apprenti"
    OPERATIONNEL = "opérationnel"
    EXPERT = "expert"


class ModelTier(str, enum.Enum):
    SONNET = "sonnet"
    OPUS = "opus"


class GitProvider(str, enum.Enum):
    GITHUB = "github"
    GITLAB = "gitlab"


class GitConnectionStatus(str, enum.Enum):
    ACTIVE = "active"
    ERROR = "error"
    REVOKED = "revoked"


class McpAuthType(str, enum.Enum):
    API_KEY = "api_key"
    OAUTH = "oauth"
    NONE = "none"


class McpConnectionStatus(str, enum.Enum):
    ACTIVE = "active"
    ERROR = "error"
    UNAVAILABLE = "unavailable"
