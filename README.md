# Home Assistant Volcano Hybrid
[![hacs][hacs_badge]][hacs_url]
[![Validate][validate_badge]][validate_url]

[![gh_latest_release_badge]][gh_latest_release_url] 
![gh_release_date_badge]
[![gh_issues_badge]][gh_issues_url]

A Storz & Bickel integration for Home Assistant using Bluetooth: Volcano Hybrid, Crafty / Crafty+, Venty and Veazy. Allows controlling core features via a single climate entity.

![Climate entity](resources/climate_entity.png)

## Installing

Install using HACS (click the button below if you have it installed), or download the repository and put the folder from `custom-components` in your `config/custom_components` folder.

[![Open HACS Repository On MY](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=SavageNL&repository=home-assistant-volcano-hybrid&category=integration)

## Supported devices

| Device | Tested on hardware | Notes |
| --- | --- | --- |
| Volcano Hybrid | yes | — |
| Crafty+ | **no** | decoded from the vendor app; monitor-only below firmware V02.51 |
| Crafty | **no** | decoded from the vendor app; monitor-only below firmware V02.51 |
| Venty | **no** | polled every second while connected |
| Veazy | **no** | polled every second while connected |

If you own one of the untested devices, please open an issue with the diagnostics download — that is how these become tested.

## Quick start

- Add the integration
- Power on your device (Volcano Hybrid, Crafty, Venty or Veazy)
- If you have BLE adapters configured the device should be discovered automatically
- Add it when it's found and start using the climate entity (for a Volcano Hybrid that is `climate.volcano_hybrid`).


## Usage

Every device gets a `climate` entity; the rest are sensors, switches, numbers and buttons, and most of the configuration and diagnostic ones are disabled by default. The sections below list what each device offers.

### Volcano Hybrid

This integration adds a `climate` entity to control the Volcano Hybrid:

It shows the following information and allows these controls:
- Current temperature (read-only)
- Target temperature
- Set directly or increase value in 1 degree steps
- Enable/disable heating
- Enable/disable fan
- Whether it is heating up, holding temperature, or cooling down after being switched off (the `hvac_action` attribute: the card shows *Heating* while it works towards the target, *Heat* once it is holding, and *Idle* while it cools with its display still lit)

There is also a **Ready** binary sensor, which is on once the vaporizer reports it reached the target temperature. It is the device's own "temperature reached" signal passed through unchanged, which is what makes it the right thing to wait on: it is the same signal that drives the device's vibration alert, so it turns on exactly when the Volcano tells you it is ready.

Being the device's own signal, it also inherits the device's idea of "reached": a target change of 2 °C or less never turns it off, and it stays on while the device coasts down after you lower the target or switch the heater off. For "is it actually working towards the target right now", use `hvac_action` instead.

Additionally, there are the following configuration/diagnostic entities:
- The auto off time setting (configurable)
- Led brightness (configurable)
- Whether the device is showing temperature in Celsius or Fahrenheit (configurable)
- Whether vibration is enabled (configurable)
- The total heating time
- Whether the auto off timer is enabled (this arms when the target temperature is reached)
- Whether the heater is running and whether the pump is running
- A heater/pump fault sensor (the device reports a timing fault in its heater control, which stops both the heater and the pump)
- Whether the device is in its service/burn-in mode (it heats itself to 230 °C for ten minutes)
- The raw status registers 1/2/3 and error history 1/2, as hex, for diagnosing faults (see [the BLE spec](VOLCANO_BLE_SPEC.md)), plus status registers 4/5 — the device's two remaining status words, which nothing decodes yet and which stay empty on a device that does not report them
- A last fault sensor, which reads that error history rather than reprinting it: it names the newest fault the device logged, and its attributes carry the rest of the log both decoded and raw
- The device connected state
- A reconnect button (connects immediately)
- A delayed reconnect button (disconnects, then reconnects after a short delay so a better Bluetooth path can be chosen)
- An auto-connect switch (enable/disable automatic connecting; see [Connecting](#connecting))
- The rssi from the last ble message

Most of these are disabled by default; enable them under the device page in **Settings** → **Devices & services**.

### Crafty / Crafty+

Experimental, untested on hardware. The `climate` entity sets the target temperature and switches the heater; there is no fan, so no fan modes. Entities:
- Battery (sensor)
- Auto off countdown (sensor)
- Total heat time (sensor)
- Ready (binary sensor, on once the target temperature is reached)
- Heater running (binary sensor)
- Boost and Superboost (binary sensors)
- Error and Needs factory reset (binary sensors)
- Find mode active (binary sensor)
- Boost temperature (configurable)
- LED Brightness (configurable)
- Auto off time (configurable)
- Vibration enabled (configurable)
- Charge LED (configurable)
- Automatic Bluetooth shutdown (configurable; see [Sleeping devices](#sleeping-devices))
- Find device (button, makes the device buzz)
- Status register 1/2, System status and Battery status 1/2 as hex, for diagnosing faults (see [the Crafty spec](CRAFTY_BLE_SPEC.md))
- The device connected state, signal strength and connected address, the reconnect buttons and the auto-connect switch, as on the Volcano

Below firmware V02.51 the Crafty does not expose its settings characteristics, so there the integration can only monitor and control the temperature and heater. There is no firmware update entity for the Crafty.

### Venty / Veazy

Experimental, untested on hardware. The `climate` entity sets the target temperature and switches the heater; there is no fan, so no fan modes. Entities:
- Battery (sensor)
- Auto off countdown (sensor)
- Heater mode (sensor)
- Total heat time and Total charging time (sensors)
- Colour (sensor, Veazy only)
- Ready (binary sensor)
- Heater running and Charging (binary sensors)
- Boost and Superboost (binary sensors)
- Target changed on device (binary sensor)
- Bootloader mode (binary sensor; while the device is in its bootloader it is reported but never controlled)
- Permanent Bluetooth (Venty: binary sensor; Veazy: switch, see [Sleeping devices](#sleeping-devices))
- Boost temperature and Superboost temperature (configurable)
- Display brightness (configurable)
- Showing celsius (configurable)
- Vibration enabled (configurable)
- Charge optimization and Charge limit (configurable)
- Boost visualization (configurable)
- Boost timeout disabled (configurable)
- Find device (button)
- Firmware (update entity; it reports the installed version, no newer version is known yet)
- The device connected state, signal strength and connected address, the reconnect buttons and the auto-connect switch, as on the Volcano

These devices are polled every second while connected (see [the Venty spec](VENTY_BLE_SPEC.md)).

## How the device is controlled

The Crafty and Venty/Veazy protocols are documented in [**CRAFTY_BLE_SPEC.md**](CRAFTY_BLE_SPEC.md) and [**VENTY_BLE_SPEC.md**](VENTY_BLE_SPEC.md). The Volcano Hybrid Bluetooth protocol is documented in [**VOLCANO_BLE_SPEC.md**](VOLCANO_BLE_SPEC.md): every service and characteristic, how the values are encoded, the meaning of each bit in the status registers, and the firmware-update protocol (which this integration deliberately does not implement).

## Warning

### Do not leave the device unattended while using the integration

That being said, there are some safety measures:
- Temperature commands **WILL** be retried every second (while the device is on) when they don't appear to get set
- On-commands (fan-on, heater-on) **WON'T** be retried. If they fail, they fail.
- Off-commands **WILL** be retried (as long as the device is on, but if they fail, it will be on)

This will however not protect you from losing control when bluetooth fails, so _do not leave the device unattended while using the integration_.

## Connecting

By default this integration connects to a device as soon as it sees one (after it has been set up).
This means updates from the device trigger updates in Home Assistant instantly, but it also means no other Bluetooth client can control the device while Home Assistant holds the connection (the Volcano stops advertising once connected).
The portable devices sleep when idle, so they are connected when they wake up; see [Sleeping devices](#sleeping-devices).

You can control this behavior:

- **Auto connect** switch — turn it off to release the device so the official app or another Bluetooth client can connect. Commands you send from Home Assistant (and the reconnect buttons) still connect on demand. Turn it back on to resume automatic connecting. The setting is remembered across restarts.
- **(Re)connect** button — connects immediately.
- **(Re)connect after delay** button — disconnects and reconnects after the configured delay, leaving time for a fresh advertisement so the strongest Bluetooth proxy can take the connection.

### Sleeping devices

The portable devices (Crafty, Venty, Veazy) switch Bluetooth off when idle to save battery. Their entities show *unavailable* until the device wakes and advertises again, at which point the integration connects as usual. The *Automatic Bluetooth shutdown* setting (Crafty) and *Permanent Bluetooth* (Veazy) change that, at the cost of battery life.

### Configuration

The connect timing is configurable via the integration's options (**Settings** → **Devices & services** → **Storz & Bickel** → **Configure**):

- **Auto-connect delay** (default `1` second) — how long to wait after seeing the device before connecting automatically. A short wait lets every Bluetooth proxy report the advertisement so the best path is chosen instead of the first one to see it. Keep this low.
- **Delayed reconnect delay** (default `11` seconds) — how long the *(Re)connect after delay* button stays disconnected before reconnecting. The Volcano advertises roughly every 10 seconds while idle, so the default guarantees at least one fresh advertisement.

## Troubleshooting

### The device is not discovered

- Volcano: make sure it is plugged in; its Bluetooth stays available even when the heater and fan are off.
- Crafty, Venty and Veazy: wake the device (switch it on or press a button) so it advertises; they switch Bluetooth off when idle, see [Sleeping devices](#sleeping-devices).
- Make sure a [Bluetooth adapter or ESPHome Bluetooth proxy](https://www.home-assistant.io/integrations/bluetooth/) is set up in Home Assistant and within range of the device.
- The official Storz & Bickel app (or any other Bluetooth client) may be holding the connection. Close the app and try again.

### The entities show as unavailable

The Bluetooth connection to the device was lost. The integration reconnects automatically as soon as the device is seen again (unless the `Auto connect` switch is off — see [Connecting](#connecting)); the diagnostic `Connected` binary sensor and `Signal strength` sensor (disabled by default) can help spot range issues. Pressing the `(Re)connect` button forces a new connection attempt.

### Commands fail with "the device is not connected"

The command could not be delivered because the device is currently disconnected. Wait for it to reconnect (or press the `(Re)connect` button) and try again.

## Removing the integration

This integration follows standard integration removal:

1. Go to **Settings** → **Devices & services** and select the **Storz & Bickel** integration.
2. Open the three-dot menu of the config entry and select **Delete**.

After removal the device keeps working standalone; no settings on the device itself need to be reset. If you installed through HACS you can then also remove the repository from HACS.

# Example usage

- [Complete dashboard using only stock cards](#complete-dashboard-using-only-stock-cards)
- [Dashboard grid with shut-off timer and current states](#Dashboard-grid-with-shut-off-timer-and-current-states)
- [Dashboard button card for pre-selected temperatures](#Button-card-for-pre-selected-temperatures)
- [Automation to automatically progress temperature over time](#Automatically-progress-temperature-over-time)
- [Example service calls to increase/decrease temperature by Vapesuvius temp guide steps](#increasedecrease-temperature-by-vapesuvius-temp-guide-steps)
- [Script to fill a bag](#fill-a-bag)
- [Script for a hands-free bag session](#hands-free-bag-session)
- [Script for a hands-free whip session](#hands-free-whip-session)
- [Script for party rounds](#party-rounds)
- [Ready-made ladders for the session scripts](#ready-made-ladders)
- [Ready-made whip sessions](#ready-made-whip-sessions)


## Complete dashboard using only stock cards

A single dashboard that brings together temperature control, preset temperature
buttons, a status card, and the device settings, using only built-in Home
Assistant cards (no `custom:button-card` or other HACS frontend cards). It is a
[Sections](https://www.home-assistant.io/dashboards/sections/) view, so it
reflows to one column on a phone and up to two on a wider screen.

Create a new dashboard (Settings > Dashboards > Add dashboard > New dashboard
from scratch), open its three-dot menu > Raw configuration editor, and paste the
whole block below.

The entity ids assume the default device slug `volcano_hybrid`; adjust them if
you renamed the device. Most of the Volcano's entities are disabled by default
(the settings, the diagnostics, and the PRV error sensors), so the Control and
Presets sections work right away, while the Status and Settings sections show a
reminder to enable those entities first (Settings > Devices & services > Volcano
Hybrid > the entity > gear icon > Enabled).

![Dashboard](resources/dashboard.png)


```yaml
views:
  - title: Volcano
    icon: mdi:volcano-outline
    type: sections
    max_columns: 2
    sections:
      # ---------- Control (works out of the box) ----------
      - type: grid
        cards:
          - type: heading
            heading: Volcano Hybrid
            heading_style: title
            icon: mdi:volcano-outline
            badges:
              - type: entity
                entity: sensor.volcano_hybrid_auto_off_time
                show_state: true
                show_icon: true
              - type: entity
                entity: binary_sensor.volcano_hybrid_connected
                show_state: true
                show_icon: true
          - type: thermostat
            entity: climate.volcano_hybrid
            show_current_as_primary: true
            name: " "
            features:
              - style: icons
                type: climate-hvac-modes
              - style: icons
                type: climate-fan-modes

      # ---------- Presets (works out of the box: climate.set_temperature) ----------
      - type: grid
        cards:
          - type: heading
            heading: Presets
            heading_style: subtitle
            icon: mdi:thermometer
          - type: button
            name: "179"
            icon: mdi:thermometer-low
            show_state: false
            tap_action:
              action: perform-action
              perform_action: climate.set_temperature
              target:
                entity_id: climate.volcano_hybrid
              data:
                hvac_mode: heat
                temperature: 179
          - type: button
            name: "185"
            icon: mdi:thermometer
            tap_action:
              action: perform-action
              perform_action: climate.set_temperature
              target:
                entity_id: climate.volcano_hybrid
              data:
                hvac_mode: heat
                temperature: 185
          - type: button
            name: "191"
            icon: mdi:thermometer
            tap_action:
              action: perform-action
              perform_action: climate.set_temperature
              target:
                entity_id: climate.volcano_hybrid
              data:
                hvac_mode: heat
                temperature: 191
          - type: button
            name: "199"
            icon: mdi:thermometer
            tap_action:
              action: perform-action
              perform_action: climate.set_temperature
              target:
                entity_id: climate.volcano_hybrid
              data:
                hvac_mode: heat
                temperature: 199
          - type: button
            name: "209"
            icon: mdi:thermometer-high
            tap_action:
              action: perform-action
              perform_action: climate.set_temperature
              target:
                entity_id: climate.volcano_hybrid
              data:
                hvac_mode: heat
                temperature: 209

      # ---------- Status (Connected works OOTB; PRV/runtime need enabling) ----------
      - type: grid
        cards:
          - type: heading
            heading: Status
            heading_style: subtitle
            icon: mdi:heart-pulse
          - type: markdown
            content: |
              {% if is_state('binary_sensor.volcano_hybrid_prv1_error','on') or is_state('binary_sensor.volcano_hybrid_prv2_error','on') %}
              ## PRV error reported
              Check the device.
              {% elif not is_state('binary_sensor.volcano_hybrid_connected','on') %}
              ## Not connected
              The Volcano is not reachable over Bluetooth right now.
              {% else %}
              ## All good
              Connected, no PRV errors reported.
              {% endif %}
          - type: entities
            title: Runtime
            show_header_toggle: false
            entities:
              - entity: binary_sensor.volcano_hybrid_connected
              - entity: sensor.volcano_hybrid_current_on_time
              - entity: sensor.volcano_hybrid_total_heat_time
              - entity: sensor.volcano_hybrid_signal_strength

      # ---------- Device settings (enable these entities first) ----------
      - type: grid
        cards:
          - type: heading
            heading: Device settings
            heading_style: subtitle
            icon: mdi:cog
          - type: markdown
            content: >
              These entities are disabled by default. Enable each one in
              Settings > Devices & services > Volcano Hybrid > the entity >
              gear icon > Enabled, then reload.
          - type: entities
            show_header_toggle: false
            entities:
              - entity: number.volcano_hybrid_shut_off_time
              - entity: number.volcano_hybrid_led_brightness
              - entity: switch.volcano_hybrid_vibration_enabled
              - entity: switch.volcano_hybrid_showing_celsius
              - entity: switch.volcano_hybrid_display_on_when_cooling
              - entity: binary_sensor.volcano_hybrid_auto_shutdown_enabled
              - entity: button.volcano_hybrid_reconnect
```

## Dashboard grid with shut-off timer and current states

An example grid with a header and a thermostat entity (both standard Home Assistant components).

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

## Button card for pre-selected temperatures

![Climate entity](resources/set_temperature.png)

Example grid using [Button Card](https://github.com/custom-cards/button-card) to easily set pre-defined temperatures.

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
Follows the [Vapesuvius temp guide](https://www.reddit.com/user/Vapesuvius/comments/zuwcs7/vapesuvius_unofficial_storz_bickel_temp_guide_2nd/) (for temp, not time)

```yaml
alias: Volcano progress
description: ""
triggers:
  - trigger: numeric_state
    entity_id:
      - sensor.volcano_hybrid_current_on_time
    above: 0
    id: "179"
    alias: 0 => 179
  - trigger: numeric_state
    entity_id:
      - sensor.volcano_hybrid_current_on_time
    above: 5
    id: "185"
    alias: 5 => 185
  - trigger: numeric_state
    entity_id:
      - sensor.volcano_hybrid_current_on_time
    above: 10
    id: "191"
    alias: 10 => 191
  - trigger: numeric_state
    entity_id:
      - sensor.volcano_hybrid_current_on_time
    above: 15
    id: "199"
    alias: 15 => 199
  - trigger: numeric_state
    entity_id:
      - sensor.volcano_hybrid_current_on_time
    above: 20
    id: "205"
    alias: 20 => 205
conditions:
  - alias: Don't trigger when device reconnects
    condition: and
    conditions:
      - condition: template
        value_template: >-
          {{ trigger.from_state.state not in ['unknown','unavailable'] and
          trigger.to_state.state not in ['unknown','unavailable'] }}
        alias: from_state or to_state was unknown or unavailable
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

### Fill a bag

This is an example script that will:
1. Turn on the Volcano
1. Wait for the device to heat up, and then 10s more
1. Turn on the fan
1. Wait for 40s (that's how long it takes to nearly fill up my standard bags, adjust to yours accordingly)
1. Turns off the fan
1. Waits 10 more seconds (this gives you time to turn the fan on to fill the bag completely)
1. Turns off the Volcano

```yaml
sequence:
  - action: climate.turn_on
    metadata: {}
    data: {}
    target:
      entity_id: climate.volcano_hybrid
  - wait_template: >-
      {{state_attr('climate.volcano_hybrid', 'temperature') ==
      state_attr('climate.volcano_hybrid', 'current_temperature')}}
    continue_on_timeout: true
    alias: Wait for heatup
  - alias: Wait a little bit more
    delay:
      hours: 0
      minutes: 0
      seconds: 10
      milliseconds: 0
  - action: climate.set_fan_mode
    metadata: {}
    data:
      fan_mode: "on"
    target:
      entity_id: climate.volcano_hybrid
  - alias: Wait for the bag to fill (40s)
    delay:
      hours: 0
      minutes: 0
      seconds: 41
      milliseconds: 0
  - action: climate.set_fan_mode
    metadata: {}
    data:
      fan_mode: "off"
    target:
      entity_id: climate.volcano_hybrid
  - delay:
      hours: 0
      minutes: 0
      seconds: 10
      milliseconds: 0
    alias: Wait a little bit more
  - action: climate.turn_off
    metadata: {}
    data: {}
    target:
      entity_id: climate.volcano_hybrid
alias: Volcano fill bag
description: ""
```


### Hands-free bag session

A script that runs a whole temperature ladder on its own, one bag per rung:

1. Turns on the Volcano
1. For each temperature in the list:
   1. Sets the temperature and waits for the device to reach it
   1. Waits 30s, so you can fit a fresh bag
   1. Turns on the fan for 40s to fill it, then turns it off
1. Turns off the Volcano after the last bag

Pick your Volcano in the **Volcano** field (the thermostat entity is named after the device, so it isn't always `climate.volcano_hybrid`). Everything else is a script field too, so the same script runs any ladder (see [Ready-made ladders](#ready-made-ladders)). Run it from the script's page to fill the fields in, or call it from a dashboard button or an automation with `data:`. If a rung isn't reached within 15 minutes the script turns the Volcano off and stops with an error.

Temperatures are always in °C, even if Home Assistant shows °F: the script converts them for you. A rung counts as reached within 1 °C, since the Volcano often settles a degree under its target.

List the temperatures low to high: a rung the chamber is already above is treated as reached, so stepping down doesn't wait for it to cool.

```yaml
alias: Volcano bag session
description: >-
  Hands-free ladder: at each temperature it heats until reached, gives you time
  to fit a fresh bag, fills it, then moves on. Turns the Volcano off at the end.
mode: single
fields:
  volcano:
    name: Volcano
    description: The Volcano's thermostat entity (it's named after the device).
    default: climate.volcano_hybrid
    selector:
      entity:
        filter:
          - integration: volcano_hybrid
            domain: climate
  temperatures:
    name: Temperatures
    description: Rungs in °C, in order. One bag is filled at each.
    default: [179, 185, 191, 199, 205, 211, 217, 230]
    selector:
      object: {}
  fit_seconds:
    name: Time to fit a bag
    description: Seconds to wait at each rung before the fan starts.
    default: 30
    selector:
      number:
        min: 0
        max: 300
        unit_of_measurement: s
  fill_seconds:
    name: Fill time
    description: Seconds the fan runs to fill each bag.
    default: 40
    selector:
      number:
        min: 5
        max: 120
        unit_of_measurement: s
sequence:
  - variables:
      volcano_entity: "{{ volcano | default('climate.volcano_hybrid') }}"
      # Temperatures here are °C. HA shows climate temperatures in your unit
      # system, so on °F convert (the Volcano's 230 °C max shows as 446 °F).
      fahrenheit: "{{ state_attr(volcano_entity, 'max_temp') | float(0) > 300 }}"
  - action: climate.turn_on
    target:
      entity_id: "{{ volcano_entity }}"
  - repeat:
      for_each: "{{ temperatures | default([179, 185, 191, 199, 205, 211, 217, 230]) }}"
      sequence:
        - variables:
            rung: >-
              {{ ((repeat.item | float * 9 / 5 + 32) | round(1)) if fahrenheit
              else repeat.item | float }}
            margin: "{{ 1.8 if fahrenheit else 1 }}"
        - action: climate.set_temperature
          data:
            temperature: "{{ rung }}"
          target:
            entity_id: "{{ volcano_entity }}"
        - alias: Wait for the device to reach the rung
          wait_template: >-
            {{ state_attr(volcano_entity, 'current_temperature') | float(0)
            >= rung | float - margin | float }}
          timeout: "00:15:00"
          continue_on_timeout: true
        - if: "{{ not wait.completed }}"
          then:
            - action: climate.turn_off
              target:
                entity_id: "{{ volcano_entity }}"
            - stop: "Didn't reach {{ repeat.item }} °C within 15 minutes"
              error: true
        - alias: Time to fit a fresh bag
          delay:
            seconds: "{{ fit_seconds | default(30) | int }}"
        - action: climate.set_fan_mode
          data:
            fan_mode: "on"
          target:
            entity_id: "{{ volcano_entity }}"
        - alias: Fill the bag
          delay:
            seconds: "{{ fill_seconds | default(40) | int }}"
        - action: climate.set_fan_mode
          data:
            fan_mode: "off"
          target:
            entity_id: "{{ volcano_entity }}"
  - action: climate.turn_off
    target:
      entity_id: "{{ volcano_entity }}"
```

### Hands-free whip session

The same ladder for whip use: instead of filling bags it holds each temperature for a few minutes, then moves to the next. The fan is left to you.

```yaml
alias: Volcano whip session
description: >-
  Hands-free ladder for whip use: holds each temperature once reached, then
  moves on. Turns the Volcano off at the end.
mode: single
fields:
  volcano:
    name: Volcano
    description: The Volcano's thermostat entity (it's named after the device).
    default: climate.volcano_hybrid
    selector:
      entity:
        filter:
          - integration: volcano_hybrid
            domain: climate
  temperatures:
    name: Temperatures
    description: Rungs in °C, in order.
    default: [179, 185, 191, 199, 205, 211, 217, 230]
    selector:
      object: {}
  hold_minutes:
    name: Hold time
    description: Minutes to hold each rung once it's reached.
    default: 3
    selector:
      number:
        min: 0.5
        max: 30
        step: 0.5
        unit_of_measurement: min
sequence:
  - variables:
      volcano_entity: "{{ volcano | default('climate.volcano_hybrid') }}"
      # Temperatures here are °C. HA shows climate temperatures in your unit
      # system, so on °F convert (the Volcano's 230 °C max shows as 446 °F).
      fahrenheit: "{{ state_attr(volcano_entity, 'max_temp') | float(0) > 300 }}"
  - action: climate.turn_on
    target:
      entity_id: "{{ volcano_entity }}"
  - repeat:
      for_each: "{{ temperatures | default([179, 185, 191, 199, 205, 211, 217, 230]) }}"
      sequence:
        - variables:
            rung: >-
              {{ ((repeat.item | float * 9 / 5 + 32) | round(1)) if fahrenheit
              else repeat.item | float }}
            margin: "{{ 1.8 if fahrenheit else 1 }}"
        - action: climate.set_temperature
          data:
            temperature: "{{ rung }}"
          target:
            entity_id: "{{ volcano_entity }}"
        - alias: Wait for the device to reach the rung
          wait_template: >-
            {{ state_attr(volcano_entity, 'current_temperature') | float(0)
            >= rung | float - margin | float }}
          timeout: "00:15:00"
          continue_on_timeout: true
        - if: "{{ not wait.completed }}"
          then:
            - action: climate.turn_off
              target:
                entity_id: "{{ volcano_entity }}"
            - stop: "Didn't reach {{ repeat.item }} °C within 15 minutes"
              error: true
        - alias: Hold the rung
          delay:
            seconds: "{{ (hold_minutes | default(3) | float * 60) | int }}"
  - action: climate.turn_off
    target:
      entity_id: "{{ volcano_entity }}"
```

### Party rounds

Bags for a group at one temperature: heats up, gives you time to fit the first bag, then fills a bag every few minutes. It stops after a set number of bags and turns the Volcano off, so it can't run on unattended.

```yaml
alias: Volcano party rounds
description: >-
  One temperature, a bag every few minutes, then the Volcano turns off.
mode: single
fields:
  volcano:
    name: Volcano
    description: The Volcano's thermostat entity (it's named after the device).
    default: climate.volcano_hybrid
    selector:
      entity:
        filter:
          - integration: volcano_hybrid
            domain: climate
  temperature:
    name: Temperature
    default: 190
    selector:
      number:
        min: 40
        max: 230
        unit_of_measurement: °C
  bags:
    name: Bags
    default: 8
    selector:
      number:
        min: 1
        max: 20
  gap_minutes:
    name: Time between bags
    description: Minutes to pass the bag round and fit the next one.
    default: 2.5
    selector:
      number:
        min: 0.5
        max: 15
        step: 0.5
        unit_of_measurement: min
  fill_seconds:
    name: Fill time
    default: 40
    selector:
      number:
        min: 5
        max: 120
        unit_of_measurement: s
sequence:
  - variables:
      volcano_entity: "{{ volcano | default('climate.volcano_hybrid') }}"
      # Temperatures here are °C. HA shows climate temperatures in your unit
      # system, so on °F convert (the Volcano's 230 °C max shows as 446 °F).
      fahrenheit: "{{ state_attr(volcano_entity, 'max_temp') | float(0) > 300 }}"
      target: >-
        {{ ((temperature | default(190) | float * 9 / 5 + 32) | round(1)) if fahrenheit
        else temperature | default(190) | float }}
      margin: "{{ 1.8 if fahrenheit else 1 }}"
  - action: climate.set_temperature
    data:
      temperature: "{{ target }}"
    target:
      entity_id: "{{ volcano_entity }}"
  - action: climate.turn_on
    target:
      entity_id: "{{ volcano_entity }}"
  - alias: Wait for heatup
    wait_template: >-
      {{ state_attr(volcano_entity, 'current_temperature') | float(0)
      >= target | float - margin | float }}
    timeout: "00:15:00"
    continue_on_timeout: true
  - if: "{{ not wait.completed }}"
    then:
      - action: climate.turn_off
        target:
          entity_id: "{{ volcano_entity }}"
      - stop: "Didn't heat up within 15 minutes"
        error: true
  - alias: Time to fit the first bag
    delay:
      seconds: 30
  - repeat:
      count: "{{ bags | default(8) | int }}"
      sequence:
        - action: climate.set_fan_mode
          data:
            fan_mode: "on"
          target:
            entity_id: "{{ volcano_entity }}"
        - alias: Fill the bag
          delay:
            seconds: "{{ fill_seconds | default(40) | int }}"
        - action: climate.set_fan_mode
          data:
            fan_mode: "off"
          target:
            entity_id: "{{ volcano_entity }}"
        - if: "{{ repeat.index < bags | default(8) | int }}"
          then:
            - alias: Pass it round, fit the next bag
              delay:
                seconds: "{{ (gap_minutes | default(2.5) | float * 60) | int }}"
  - action: climate.turn_off
    target:
      entity_id: "{{ volcano_entity }}"
```

### Ready-made ladders

Paste one of these into the `temperatures` field of the bag or whip session (all °C, low to high):

| Ladder | Temperatures | Notes |
|---|---|---|
| Vapesuvius full spectrum | `[179, 185, 191, 199, 205, 211, 217, 230]` | The [temp guide](https://www.reddit.com/user/Vapesuvius/comments/zuwcs7/vapesuvius_unofficial_storz_bickel_temp_guide_2nd/) rungs |
| Even steps | `[185, 199, 211, 230]` | Rungs 2/4/6/8, leaves more in already-vaped bud for edibles |
| Odd steps | `[179, 191, 205, 217]` | Rungs 1/3/5/7 |
| Dosing capsule | `[185, 197, 211, 230]` | Four rungs sized for a capsule |
| Flavor | `[170, 175, 180]` | The lighter-terpene range |
| Terpene tour | `[169, 180, 187, 202, 215, 222, 230]` | 1–2 °C above the boiling points of myrcene, limonene, CBN, linalool, borneol, CBC and geraniol |
| Balloon climb | `[170, 175, 180, 185, 190, 195, 200, 205, 210, 215, 220]` | Eleven 5° steps |
| Express | `[185, 205, 225]` | Three big steps |
| Low & slow | `[180, 190, 200]` | Gentle; try a 5-minute hold for whip use |
| Hot finisher | `[215, 220, 225, 230]` | The last of a used load |

### Ready-made whip sessions

Values for the whip session's `temperatures` and `hold_minutes` fields. A single temperature is just a timed hold that turns the Volcano off at the end.

| Session | Temperatures | Hold time | About |
|---|---|---|---|
| Gentle hold | `[185]` | 20 min | 20 min |
| Classic hold | `[195]` | 15 min | 15 min |
| Hot hold | `[205]` | 10 min | 10 min; the vapor is warm, a waterpipe helps |
| Two-stage | `[190, 205]` | 8 min | 16 min: flavor first, then strength |
| Ramp | `[175, 180, 185, 190, 195, 200, 205, 210, 215]` | 1.5 min | 14 min, each pull a little warmer |
| Long session | `[185, 195, 205, 215]` | 6 min | 24 min |
| Vapesuvius | `[179, 185, 191, 199, 205, 211, 217, 230]` | 3 min | 24 min, the full temp guide |

Times are hold time only; add a little for heating between rungs.

Each script runs in `single` mode, so starting it again while it's running does nothing. If you stop a script part-way, it doesn't clean up after itself: turn the fan and heater off yourself.

[validate_url]: https://github.com/SavageNL/home-assistant-volcano-hybrid/actions/workflows/validate.yml
[validate_badge]: https://github.com/SavageNL/home-assistant-volcano-hybrid/actions/workflows/validate.yml/badge.svg
[hacs_url]: https://github.com/hacs/integration
[hacs_badge]: https://img.shields.io/badge/HACS-Default-orange.svg
[gh_latest_release_badge]: https://img.shields.io/github/v/release/SavageNL/home-assistant-volcano-hybrid
[gh_latest_release_url]: https://github.com/SavageNL/home-assistant-volcano-hybrid/releases
[gh_release_date_badge]: https://img.shields.io/github/release-date/SavageNL/home-assistant-volcano-hybrid
[gh_issues_badge]: https://img.shields.io/github/issues/SavageNL/home-assistant-volcano-hybrid
[gh_issues_url]: https://github.com/SavageNL/home-assistant-volcano-hybrid/issues
