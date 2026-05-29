
from config import EmailConfig, Settings, SourceRule, SourcesConfig
from processing.whitelist import EmailAction, WhitelistFilter


def make_filter(authorized_user: str = "user@personal.com", rules: list = None) -> WhitelistFilter:
    settings = Settings(email=EmailConfig(authorized_user_address=authorized_user))
    sources = SourcesConfig(sources=rules or [])
    return WhitelistFilter(settings, sources)


# --- Authorized user ---

def test_authorized_user_is_user_message():
    f = make_filter(authorized_user="user@personal.com")
    assert f.classify("user@personal.com").action == EmailAction.user_message


def test_authorized_user_case_insensitive():
    f = make_filter(authorized_user="user@personal.com")
    assert f.classify("USER@PERSONAL.COM").action == EmailAction.user_message


def test_empty_authorized_user_not_matched():
    f = make_filter(authorized_user="")
    assert f.classify("someone@example.com").action == EmailAction.ignored


# --- Exact match ---

def test_exact_match_newsletter():
    rules = [SourceRule(match="newsletter@example.com", category="cloud_security")]
    result = make_filter(rules=rules).classify("newsletter@example.com")
    assert result.action == EmailAction.newsletter
    assert result.category == "cloud_security"


def test_exact_match_case_insensitive():
    rules = [SourceRule(match="newsletter@example.com", category="cloud_security")]
    result = make_filter(rules=rules).classify("NEWSLETTER@EXAMPLE.COM")
    assert result.action == EmailAction.newsletter


def test_exact_match_no_partial():
    rules = [SourceRule(match="newsletter@example.com", category="cloud_security")]
    result = make_filter(rules=rules).classify("other@example.com")
    assert result.action == EmailAction.ignored


# --- Domain match ---

def test_domain_match_newsletter():
    rules = [SourceRule(match_domain="linkedin.com", category="market_signal")]
    result = make_filter(rules=rules).classify("jobs@linkedin.com")
    assert result.action == EmailAction.newsletter
    assert result.category == "market_signal"


def test_domain_match_case_insensitive():
    rules = [SourceRule(match_domain="LinkedIn.com", category="market_signal")]
    result = make_filter(rules=rules).classify("jobs@LINKEDIN.COM")
    assert result.action == EmailAction.newsletter


def test_domain_match_no_subdomain_bleed():
    rules = [SourceRule(match_domain="linkedin.com", category="market_signal")]
    result = make_filter(rules=rules).classify("jobs@mail.linkedin.com")
    assert result.action == EmailAction.ignored


# --- Priority & fallthrough ---

def test_exact_match_before_domain_match():
    rules = [
        SourceRule(match="specific@linkedin.com", category="specific"),
        SourceRule(match_domain="linkedin.com", category="market_signal"),
    ]
    result = make_filter(rules=rules).classify("specific@linkedin.com")
    assert result.category == "specific"


def test_user_message_before_whitelist():
    rules = [SourceRule(match="user@personal.com", category="cloud_security")]
    f = make_filter(authorized_user="user@personal.com", rules=rules)
    assert f.classify("user@personal.com").action == EmailAction.user_message


def test_unknown_sender_ignored():
    rules = [SourceRule(match="newsletter@example.com", category="cloud_security")]
    result = make_filter(rules=rules).classify("spam@unknown.com")
    assert result.action == EmailAction.ignored
    assert result.category is None
