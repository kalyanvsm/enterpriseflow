from enum import StrEnum


class RetryOutcome(StrEnum):
    RETRY_SCHEDULED = "retry_scheduled"
    RETRY_EXHAUSTED = "retry_exhausted"
    STALE_CLAIM = "stale_claim"
