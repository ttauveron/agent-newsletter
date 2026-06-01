import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/app/config"))


class SourceRule(BaseModel):
    match: Optional[str] = None
    match_domain: Optional[str] = None
    category: str


class SourcesConfig(BaseModel):
    sources: list[SourceRule]


class DigestConfig(BaseModel):
    schedule: str = "07:00"
    timezone: str = "Europe/Zurich"


class EmailConfig(BaseModel):
    hermes_address: str = ""
    authorized_user_address: str = ""
    self_forward_addresses: list[str] = []


class WebConfig(BaseModel):
    allowed_domains: list[str] = []


class Settings(BaseModel):
    digest: DigestConfig = DigestConfig()
    email: EmailConfig = EmailConfig()
    web: WebConfig = WebConfig()


def load_settings() -> Settings:
    with open(CONFIG_DIR / "settings.yaml") as f:
        data = yaml.safe_load(f)
    return Settings(**(data or {}))


def load_sources() -> SourcesConfig:
    with open(CONFIG_DIR / "sources.yaml") as f:
        data = yaml.safe_load(f)
    return SourcesConfig(**(data or {"sources": []}))
