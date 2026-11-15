"""Предохранители API: лимит реплик и схема модели."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import main, planner
from app.config import settings
from app.schema import Intent, UiFeature


def _client(host: str) -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=host))


def test_ask_limit_stops_a_burst_from_one_client_but_not_from_another(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-" + "x" * 40)
    monkeypatch.setattr(settings, "ask_per_minute", 3)
    main._asks.clear()
    for _ in range(3):
        main._require_model(_client("10.0.0.1"))
    with pytest.raises(HTTPException) as error:
        main._require_model(_client("10.0.0.1"))
    assert error.value.status_code == 429
    main._require_model(_client("10.0.0.2"))
    main._asks.clear()


def test_schema_offers_ui_help_and_formula_replacement():
    props = planner._schema([])["schema"]["properties"]
    assert Intent.UI_HELP.value in props["intent"]["enum"]
    assert props["calc_replace"] == {"type": "boolean"}
    assert set(UiFeature) <= set(v for v in props["ui_feature"]["enum"] if v)


def test_every_ui_feature_has_an_answer():
    assert set(main.UI_HELP) == set(UiFeature)
