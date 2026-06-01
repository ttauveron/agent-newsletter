from dataclasses import dataclass
from enum import Enum
from typing import Optional

from config import Settings, SourcesConfig

_FORWARD_PREFIXES = ("fwd:", "fw:", "tr:", "transf:", "wg:")
_FORWARDED_CATEGORY = "forwarded_newsletter"


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
        self._self_forward_addresses = {a.lower() for a in settings.email.self_forward_addresses}
        self._rules = sources.sources

    def classify(
        self,
        sender_email: str,
        subject: str | None = None,
        recipient_email: str | None = None,
    ) -> WhitelistResult:
        email_lower = sender_email.lower()

        if self._authorized_user and email_lower == self._authorized_user:
            if _is_forwarded_subject(subject):
                return WhitelistResult(action=EmailAction.newsletter, category=_FORWARDED_CATEGORY)
            return WhitelistResult(action=EmailAction.user_message)

        if recipient_email and recipient_email.lower() in self._self_forward_addresses:
            return WhitelistResult(action=EmailAction.newsletter, category=_FORWARDED_CATEGORY)

        sender_domain = email_lower.split("@")[-1] if "@" in email_lower else ""

        for rule in self._rules:
            if rule.match and email_lower == rule.match.lower():
                return WhitelistResult(action=EmailAction.newsletter, category=rule.category)
            if rule.match_domain and sender_domain == rule.match_domain.lower():
                return WhitelistResult(action=EmailAction.newsletter, category=rule.category)

        return WhitelistResult(action=EmailAction.ignored)


def _is_forwarded_subject(subject: str | None) -> bool:
    if not subject:
        return False
    return subject.strip().lower().startswith(_FORWARD_PREFIXES)
