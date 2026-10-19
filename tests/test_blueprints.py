"""The example blueprints load, expand and validate as Home Assistant would."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import pytest
from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
from homeassistant.components.automation.config import (
    async_validate_config_item as async_validate_automation,
)
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.components.script.config import (
    async_validate_config_item as async_validate_script,
)
from homeassistant.util.yaml import load_yaml

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

ROOT = Path(__file__).parent.parent
BLUEPRINTS = sorted((ROOT / "blueprints").glob("*/volcano_hybrid/*.yaml"))
REPOSITORY = "https://github.com/SavageNL/home-assistant-volcano-hybrid"

# What a user would pick for the inputs that have no default.
INPUTS = {
    "volcano": "climate.volcano_hybrid",
    "on_time": "sensor.volcano_hybrid_current_on_time",
}


def _load(path: Path) -> Blueprint:
    domain = path.parent.parent.name
    schema = AUTOMATION_BLUEPRINT_SCHEMA if domain == "automation" else BLUEPRINT_SCHEMA
    return Blueprint(
        load_yaml(path), path=str(path), expected_domain=domain, schema=schema
    )


def _blob_url(path: Path) -> str:
    return f"{REPOSITORY}/blob/main/{path.relative_to(ROOT).as_posix()}"


def test_there_are_blueprints() -> None:
    """The glob finds the blueprints (an empty one would pass every test)."""
    assert len(BLUEPRINTS) == 5


@pytest.mark.parametrize("path", BLUEPRINTS, ids=lambda path: path.stem)
async def test_blueprint_expands_into_a_valid_config(
    hass: HomeAssistant, path: Path
) -> None:
    """Each blueprint, filled in, is a script or automation HA accepts."""
    blueprint = _load(path)
    inputs = {key: INPUTS[key] for key in blueprint.inputs if key in INPUTS}
    config: dict[str, Any] = {
        "use_blueprint": {"path": path.name, "input": inputs},
    }
    blueprint_inputs = BlueprintInputs(blueprint, config)
    blueprint_inputs.validate()
    expanded = blueprint_inputs.async_substitute()

    if blueprint.domain == "automation":
        assert await async_validate_automation(hass, path.stem, expanded)
    else:
        assert await async_validate_script(hass, path.stem, expanded)


@pytest.mark.parametrize("path", BLUEPRINTS, ids=lambda path: path.stem)
def test_blueprint_points_at_itself(path: Path) -> None:
    """The source URL is where HA re-imports updates from."""
    assert _load(path).metadata["source_url"] == _blob_url(path)


@pytest.mark.parametrize("path", BLUEPRINTS, ids=lambda path: path.stem)
def test_blueprint_has_an_import_button(path: Path) -> None:
    """Every blueprint is offered for import somewhere on the examples site."""
    import_url = (
        "https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url="
        + quote(_blob_url(path), safe="")
    )
    pages = "".join(page.read_text("utf-8") for page in (ROOT / "docs").rglob("*.md"))
    assert import_url in pages
