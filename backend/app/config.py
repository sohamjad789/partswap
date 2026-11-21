import os
from dataclasses import dataclass

from dotenv import load_dotenv

from app.paths import repo_root

load_dotenv(repo_root() / ".env")

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_SUPER_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
DEFAULT_FAST_MODEL = "nvidia/nemotron-3.5-bolt-e4b"
DEFAULT_PARSE_URL = "https://ai.api.nvidia.com/v1/retrieval/nvidia/nemotron-3.5-parse/parse"
DEFAULT_MODE = "fixture"


@dataclass(frozen=True)
class Settings:
    nvidia_api_key: str
    nvidia_base_url: str
    super_model: str
    fast_model: str
    parse_url: str
    mode: str

    @property
    def has_api_key(self) -> bool:
        return bool(self.nvidia_api_key)


def get_settings() -> Settings:
    env = os.environ.get
    return Settings(
        nvidia_api_key=(env("NVIDIA_API_KEY") or "").strip(),
        nvidia_base_url=env("NVIDIA_BASE_URL") or DEFAULT_BASE_URL,
        super_model=env("NEMOTRON_SUPER_MODEL") or DEFAULT_SUPER_MODEL,
        fast_model=env("NEMOTRON_FAST_MODEL") or DEFAULT_FAST_MODEL,
        parse_url=env("NEMOTRON_PARSE_URL") or DEFAULT_PARSE_URL,
        mode=env("PARTSWAP_MODE") or DEFAULT_MODE,
    )
