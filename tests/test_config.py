"""Tests for explicit LedgerLoop runtime configuration."""

import os
from pathlib import Path
from unittest.mock import patch

from core.config import DEFAULT_GEMINI_MODEL, load_settings
from core.service import run_reconciliation


PROJECT_DIR = Path(__file__).resolve().parent.parent


def test_defaults_use_local_dataset_and_offline_mode():
    with patch.dict(os.environ, {}, clear=True):
        settings = load_settings(PROJECT_DIR)

    assert settings.data_dir == PROJECT_DIR / "data"
    assert settings.dataset_name == "data"
    assert settings.gemini_model == DEFAULT_GEMINI_MODEL
    assert settings.gemini_models == (DEFAULT_GEMINI_MODEL,)
    assert settings.gemini_enabled is False


def test_environment_overrides_are_normalized_and_deduplicated():
    values = {
        "LEDGERLOOP_DATA_DIR": "data_large",
        "LLM_PROVIDER": " GEMINI ",
        "GEMINI_MODEL": "primary-model",
        "GEMINI_MODELS": "secondary-model, primary-model, , tertiary-model",
        "GEMINI_API_KEY": "test-only",
    }
    with patch.dict(os.environ, values, clear=True):
        settings = load_settings(PROJECT_DIR)

    assert settings.data_dir == PROJECT_DIR / "data_large"
    assert settings.llm_provider == "gemini"
    assert settings.gemini_models == (
        "primary-model",
        "secondary-model",
        "tertiary-model",
    )
    assert settings.gemini_enabled is True


def test_service_uses_explicit_dataset_settings():
    settings = load_settings(PROJECT_DIR)
    result = run_reconciliation(settings)

    assert result.settings == settings
    # One physical source row is intentionally skipped by non-strict
    # normalization; the service exposes canonical records to matching.
    assert len(result.matcher.gateway_records) == 115
    assert result.settings.dataset_name == "data"
    assert result.stage3_consumed
