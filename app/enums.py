from enum import Enum


class EmailDirection(str, Enum):
    EMAIL = "EMAIL"
    INCOMING_EMAIL = "INCOMING_EMAIL"
    FORWARDED_EMAIL = "FORWARDED_EMAIL"

    def __str__(self) -> str:
        return self.value
