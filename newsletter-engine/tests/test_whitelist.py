from config import EmailConfig, Settings, SourceRule, SourcesConfig
from processing.whitelist import EmailAction, WhitelistFilter


def make_filter(
    authorized_user: str = "user@personal.com",
    rules: list = None,
    self_forward_addresses: list = None,
) -> WhitelistFilter:
    settings = Settings(
        email=EmailConfig(
            authorized_user_address=authorized_user,
            self_forward_addresses=self_forward_addresses or [],
        )
    )
    sources = SourcesConfig(sources=rules or [])
    return WhitelistFilter(settings, sources)


# --- Authorized user ---


def test_authorized_user_is_user_message():
    f = make_filter(authorized_user="user@personal.com")
    assert f.classify("user@personal.com").action == EmailAction.user_message


def test_authorized_user_case_insensitive():
    f = make_filter(authorized_user="user@personal.com")
    assert f.classify("USER@PERSONAL.COM").action == EmailAction.user_message


def test_authorized_user_forwarded_subject_is_newsletter():
    f = make_filter(authorized_user="user@personal.com")
    result = f.classify("user@personal.com", "Fwd: Weekly Security Brief")
    assert result.action == EmailAction.newsletter
    assert result.category == "forwarded_newsletter"


def test_authorized_user_forwarded_prefixes_are_newsletters():
    f = make_filter(authorized_user="user@personal.com")
    for subject in [
        "FW: Cloud newsletter",
        "Tr: Bulletin cyber",
        "Transf: Bulletin cyber",
        "WG: Sicherheitsbericht",
    ]:
        assert f.classify("user@personal.com", subject).action == EmailAction.newsletter


def test_authorized_user_non_forwarded_subject_stays_user_message():
    f = make_filter(authorized_user="user@personal.com")
    assert f.classify("user@personal.com", "Weekly summary please").action == (
        EmailAction.user_message
    )


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


# --- Self-forward addresses (To: header) ---


def test_self_forward_recipient_is_newsletter():
    f = make_filter(self_forward_addresses=["relay@personal.com"])
    result = f.classify("lex@sreweekly.com", "SRE Weekly Issue #519", "relay@personal.com")
    assert result.action == EmailAction.newsletter
    assert result.category == "forwarded_newsletter"


def test_self_forward_recipient_case_insensitive():
    f = make_filter(self_forward_addresses=["relay@personal.com"])
    result = f.classify("lex@sreweekly.com", "SRE Weekly", "RELAY@PERSONAL.COM")
    assert result.action == EmailAction.newsletter


def test_self_forward_no_match_without_recipient():
    f = make_filter(self_forward_addresses=["relay@personal.com"])
    result = f.classify("lex@sreweekly.com", "SRE Weekly")
    assert result.action == EmailAction.ignored


def test_self_forward_does_not_shadow_authorized_user():
    f = make_filter(
        authorized_user="user@personal.com",
        self_forward_addresses=["relay@personal.com"],
    )
    assert f.classify("user@personal.com", "Hello", "relay@personal.com").action == (
        EmailAction.user_message
    )


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
