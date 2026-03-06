from enum import Enum


class EmailDirection(str, Enum):
    EMAIL = "EMAIL"
    INCOMING_EMAIL = "INCOMING_EMAIL"
    FORWARDED_EMAIL = "FORWARDED_EMAIL"

    def __str__(self) -> str:
        return self.value


class JobType(str, Enum):
    FETCH = "FETCH"
    SCORE = "SCORE"
    RESCORE = "RESCORE"
    EXPORT = "EXPORT"
    CHAIN_BUILD = "Chain_Build"

    def __str__(self) -> str:
        return self.value


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    def __str__(self) -> str:
        return self.value
