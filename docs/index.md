# Volcano Hybrid examples

Ready-made dashboards, scripts and automations for the
[Storz & Bickel integration](https://github.com/SavageNL/home-assistant-volcano-hybrid)
for Home Assistant.

<div class="grid cards" markdown>

-   :material-view-dashboard-outline: **[Dashboards](dashboards.md)**

    A complete dashboard with only stock cards, a compact thermostat grid, and
    buttons for preset temperatures.

-   :material-script-text-outline: **Scripts**

    [Fill a bag](scripts/fill-a-bag.md),
    a [hands-free bag session](scripts/bag-session.md),
    a [whip session](scripts/whip-session.md) and
    [party rounds](scripts/party-rounds.md).

-   :material-robot-outline: **Automations**

    [Step up a temperature ladder over time](automations/temperature-progression.md),
    or [step up and down with a switch](automations/temperature-steps.md).

-   :material-stairs-up: **[Presets](presets.md)**

    Temperature ladders and whip sessions to paste into the session scripts.

</div>

## Blueprint or YAML

Most scripts and automations come two ways:

- **Blueprint**: the import button adds it to Home Assistant, and you fill in
  your Volcano and the values in a form. When the blueprint is updated here,
  Home Assistant can re-import it.
- **YAML**: paste it into a new script or automation (three-dot menu → **Edit in
  YAML**) and adjust the entity ids and values in place.

Temperatures in these examples are in °C. The scripts convert them when Home
Assistant uses °F; the dashboards and the step actions don't, so change their
numbers if yours does.

The entity ids assume the default device name, `volcano_hybrid`. A device added
from discovery may be named after its Bluetooth name instead (for example
`climate.s_b_volcano_h`); use your own ids where they differ.

!!! warning "Don't leave the Volcano unattended"
    These scripts switch a heater on. They turn the Volcano off when they finish
    or fail, but stopping one part-way leaves the heater and fan as they are.

Something missing or broken?
[Open an issue](https://github.com/SavageNL/home-assistant-volcano-hybrid/issues)
or send a pull request: the pages live in the repository's `docs/` folder and
the blueprints in `blueprints/`.
