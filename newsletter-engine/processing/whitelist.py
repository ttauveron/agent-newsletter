from dataclasses import dataclass
from enum import Enum
from typing import Optional

from config import Settings, SourcesConfig


class EmailAction(str, Enum):
    newsletter = "newsletter"
    user_message = "user_message"
    ignored = "ignored"


@dataclass
class WhitelistResult:
    action: EmailAction
    category: Optional[str] = None


class WhitelistFilter:
    def __init__(self, settings: Settings, sources: SourcesConfig):
        self._authorized_user = settings.email.authorized_user_address.lower()
        self._rules = sources.sources

    def classify(self, sender_email: str) -> WhitelistResult:
        email_lower = sender_email.lower()

        if self._authorized_user and email_lower == self._authorized_user:
            return WhitelistResult(action=EmailAction.user_message)

        sender_domain = email_lower.split("@")[-1] if "@" in email_lower else ""

        for rule in self._rules:
            if rule.match and email_lower == rule.match.lower():
                return WhitelistResult(action=EmailAction.newsletter, category=rule.category)
            if rule.match_domain and sender_domain == rule.match_domain.lower():
                return WhitelistResult(action=EmailAction.newsletter, category=rule.category)

        return WhitelistResult(action=EmailAction.ignored)
