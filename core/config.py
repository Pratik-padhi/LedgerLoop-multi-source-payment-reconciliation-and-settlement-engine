"""Runtime configuration for LedgerLoop."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"


@dataclass(frozen=True)
class Settings:
    """Validated process configuration shared by the service and web layer."""

    project_dir: Path
    data_dir: Path
    llm_provider: str
    gemini_model: str
    gemini_models: tuple[str, ...]
    gemini_enabled: bool

    @property
    def dataset_name(self) -> str:
        return self.data_dir.name


def _csv_values(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def load_settings(project_dir: str | os.PathLike[str] | None = None) -> Settings:
    """Load explicit environment configuration with stable local defaults."""
    root = Path(project_dir or Path(__file__).resolve().parent.parent)
    configured_data_dir = os.environ.get("LEDGERLOOP_DATA_DIR")
    data_dir = Path(configured_data_dir) if configured_data_dir else root / "data"
    if not data_dir.is_absolute():
        data_dir = root / data_dir

    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
    if not model:
        model = DEFAULT_GEMINI_MODEL
    configured_models = _csv_values(os.environ.get("GEMINI_MODELS"))
    models = tuple(dict.fromkeys((model, *configured_models)))

    return Settings(
        project_dir=root,
        data_dir=data_dir,
        llm_provider=provider,
        gemini_model=model,
        gemini_models=models,
        gemini_enabled=provider == "gemini" or bool(os.environ.get("GEMINI_API_KEY")),
    )
