import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _load_env_file() -> None:
    env_file = Path(__file__).resolve().parents[2] / "agent_env.env"
    if not env_file.exists():
        env_file = Path(__file__).resolve().parents[3] / "agent_env.env"

    if not env_file.exists():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    debug: bool = False
    llm_api_key: str = ""
    llm_model_id: str = ""
    llm_base_url: str = ""
    amap_api_key: str = ""
    amap_secret_key: str = ""
    unsplash_access_key: str = ""
    frontend_origin: str = "http://localhost:5173"
    agent_timeout_seconds: int = 300


@lru_cache
def get_settings() -> Settings:
    _load_env_file()
    return Settings(
        debug=os.getenv("DEBUG", "false").lower() in {"1", "true", "yes"},
        llm_api_key=os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")),
        llm_model_id=os.getenv("LLM_MODEL_ID", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        amap_api_key=os.getenv("AMAP_API_KEY", ""),
        amap_secret_key=os.getenv("AMAP_SECRET_KEY", ""),
        unsplash_access_key=os.getenv(
            "UNSPLASH_ACCESS_KEY",
            os.getenv("UNSPLASH_API_KEY", os.getenv("UNSPLASH_ID", "")),
        ),
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
        agent_timeout_seconds=int(os.getenv("AGENT_TIMEOUT_SECONDS", "300")),
    )
