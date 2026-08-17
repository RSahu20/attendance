from enum import StrEnum


class DocumentVersionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    REVIEW_REQUIRED = "review_required"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class IngestionJobStatus(StrEnum):
    RECEIVED = "received"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REVIEW_REQUIRED = "review_required"


class IngestionStage(StrEnum):
    RECEIVED = "received"
    VALIDATING = "validating"
    STORING = "storing"
    EXTRACTING = "extracting"
    NORMALIZING = "normalizing"
    PERSISTING = "persisting"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEW_REQUIRED = "review_required"
