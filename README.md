# Home Assistant Volcano Hybrid
[![hacs][hacs_badge]][hacs_url]
[![Validate](validate_badge)](validate_url)

[![gh_latest_release_badge]][gh_latest_release_url] 
![gh_release_date_badge]
[![gh_issues_badge]][gh_issues_url]

A Storz & Bickel Volcano Hybrid integration for Home Assistant. Allows controlling core features via a single climate entity.

![Climate entity](resources/climate_entity.png)

## Installing

Install using HACS, or download the repository and put the files from `custom-components` in your `config/custom_components` folder.

## Quick start

- Add the integration
- Power on your Volcano Hybrid
- If you have BLE adapters configured the device should be discovered automatically
- Add it when it's found and start using the `climate.volcano_hybrid` entity.


## Usage

This integration adds a `climate` entity to control the Volcano Hybrid:

It shows the following information and allows these controls:
- Current temperature (read-only)
- Target temperature
- Set directly or increase value in 1 degree steps
- Enable/disable heating
- Enable/disable fan

Additionally there are the following configuration/diagnostic entities:
- The auto off time setting (configurable)
- Led brightness (configurable)
- Whether the device is showing temperature in celsius or fahrenheit (configurable)
- Whether vibration is enabled (configurable)
- The total heating time
- Whether the auto off timer is enabled (this is essentially the same as the heating state)

## Notice

This integration will connect to the Volcano as soon as it finds one (after it has been setup). 
This means that updates from the device will trigger updates in Home Assistant instantly, but also that no other bluetooth devices will be able to control the Volcano.

I'm planning to make that configurable at some point.

# Example usage

## Dashboard grid with shut-off timer and current states

![Climate entity](resources/tile_widget.png)

```yaml
type: grid
cards:
  - type: heading
    heading: Volcano Hybrid
    heading_style: title
    icon: mdi:volcano-outline
    badges:
      - type: entity
        show_state: true
        show_icon: true
        entity: sensor.volcano_hybrid_auto_off_time
  - type: thermostat
    entity: climate.volcano_hybrid
    features:
      - style: icons
        type: climate-hvac-modes
      - style: icons
        type: climate-fan-modes
    show_current_as_primary: true
    name: " "
```

## Easy temperature setting

![Climate entity](resources/set_temperature.png)

Uses [Button Card](https://github.com/custom-cards/button-card)

```yaml
type: grid
cards:
  - type: heading
    heading: Temperature
    heading_style: title
    icon: mdi:temperature-celsius
  - type: custom:button-card
    name: 179
    tap_action:
      action: call-service
      service: climate.set_temperature
      data:
        hvac_mode: heat
        temperature: 179
      target:
        entity_id: climate.volcano_hybrid
  - type: custom:button-card
    name: 185
    tap_action:
      action: call-service
      service: climate.set_temperature
      data:
        hvac_mode: heat
        temperature: 185
      target:
        entity_id: climate.volcano_hybrid
  - type: custom:button-card
    name: 191
    tap_action:
      action: call-service
      service: climate.set_temperature
      data:
        hvac_mode: heat
        temperature: 191
      target:
        entity_id: climate.volcano_hybrid
  - type: custom:button-card
    name: 199
    tap_action:
      action: call-service
      service: climate.set_temperature
      data:
        hvac_mode: heat
        temperature: 199
      target:
        entity_id: climate.volcano_hybrid
  - type: custom:button-card
    name: 209
    tap_action:
      action: call-service
      service: climate.set_temperature
      data:
        hvac_mode: heat
        temperature: 209
      target:
        entity_id: climate.volcano_hybrid
  - type: tile
    entity: automation.volcano_progress
    features_position: bottom
    vertical: false
    name: Volcano auto temp
    grid_options:
      columns: full
    tap_action:
      action: toggle
```

## Automatically progress temperature over time

This is an example automation that will automatically increase the temperature in 5-minute intervals.
Follows the [Vapesuvius temp guide](https://www.reddit.com/user/Vapesuvius/comments/zuwcs7/vapesuvius_unofficial_storz_bickel_temp_guide_2nd/)

```yaml
alias: Volcano progress
description: ""
triggers:
  - trigger: numeric_state
    entity_id:
      - sensor.volcano_hybrid_current_on_time
    above: 0
    below: 5
    id: "179"
    alias: 0-5 => 179
  - trigger: numeric_state
    entity_id:
      - sensor.volcano_hybrid_current_on_time
    above: 5
    below: 10
    id: "185"
    alias: 5-10 => 185
  - trigger: numeric_state
    entity_id:
      - sensor.volcano_hybrid_current_on_time
    above: 10
    below: 15
    id: "191"
    alias: 10-15 => 191
  - trigger: numeric_state
    entity_id:
      - sensor.volcano_hybrid_current_on_time
    above: 15
    below: 20
    id: "199"
    alias: 15-20 => 100
  - trigger: numeric_state
    entity_id:
      - sensor.volcano_hybrid_current_on_time
    above: 20
    id: "205"
    alias: 20-25 => 205
conditions: []
actions:
  - action: climate.set_temperature
    metadata: {}
    data:
      temperature: "{{ trigger.id  }}"
    target:
      entity_id: climate.volcano_hybrid
mode: single
```

### Increase/decrease temperature by Vapesuvius' temp guide steps

I use these, combined with a dimmer switch.

- Long press on: Turn on heating
- Long press off: Turn off heating
- Short press on: Turn on fan
- Short press off: Turn off fan
- Up: Increase temperature using these actions
- Down: Decrease temperature using these actions

```yaml
  - action: climate.set_temperature
    metadata: {}
    data:
      temperature: >
        {%set temp = state_attr('climate.volcano_hybrid', 'temperature')%}
        {%if temp < 179 %}179{%elif temp < 185 %}185{%elif temp < 191
        %}191{%elif temp < 199 %}199{%else %}205{%endif%}
    target:
      entity_id:
        - climate.volcano_hybrid
    alias: Inc temp


  - action: climate.set_temperature
    metadata: {}
    data:
      temperature: >
        {%set temp = state_attr('climate.volcano_hybrid', 'temperature')%}
        {%if temp > 205 %}205{%elif temp > 199 %}199{%elif temp > 191
        %}191{%elif temp > 185 %}185{%else %}179{%endif%}
    target:
      entity_id:
        - climate.volcano_hybrid
    alias: Dec temp
```


[validate_url]: https://github.com/SavageNL/home-assistant-volcano-hybrid/actions/workflows/validate.yaml
[validate_badge]: https://github.com/SavageNL/home-assistant-volcano-hybrid/actions/workflows/validate.yaml/badge.svg
[hacs_url]: https://github.com/hacs/integration
[hacs_badge]: https://img.shields.io/badge/HACS-Default-orange.svg
[gh_latest_release_badge]: https://img.shields.io/github/v/release/SavageNL/home-assistant-volcano-hybrid
[gh_latest_release_url]: https://github.com/SavageNL/home-assistant-volcano-hybrid/releases
[gh_release_date_badge]: https://img.shields.io/github/release-date/SavageNL/home-assistant-volcano-hybrid
[gh_issues_badge]: https://img.shields.io/github/issues/SavageNL/home-assistant-volcano-hybrid
[gh_issues_url]: https://github.com/SavageNL/home-assistant-volcano-hybrid/issues