# Hands-free bag session

A script that runs a whole temperature ladder on its own, one bag per rung:

1. Turns on the Volcano
1. For each temperature in the list:
   1. Sets the temperature and waits for the device to reach it
   1. Waits 30s, so you can fit a fresh bag
   1. Turns on the fan for 40s to fill it, then turns it off
1. Turns off the Volcano after the last bag

Pick your Volcano when you set it up (the thermostat entity is named after the device, so it isn't always `climate.volcano_hybrid`). The ladder and the timings are settings too, so the same script runs any ladder (see [Presets](../presets.md#ladders)). If a rung isn't reached within 15 minutes the script turns the Volcano off and stops with an error.

Temperatures are always in °C, even if Home Assistant shows °F: the script converts them for you. A rung counts as reached within 1 °C, since the Volcano often settles a degree under its target.

List the temperatures low to high: a rung the chamber is already above is treated as reached, so stepping down doesn't wait for it to cool.

=== "Blueprint"

    [![Import the blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FSavageNL%2Fhome-assistant-volcano-hybrid%2Fblob%2Fmain%2Fblueprints%2Fscript%2Fvolcano_hybrid%2Fbag_session.yaml)

    Click the button, then **Preview** and **Import** in Home Assistant. Create a
    script from it under **Settings** → **Automations & scenes** → **Scripts** →
    **Create script** → the blueprint, pick your Volcano and adjust the values.
    To run several variants (say, two different ladders), create one script per
    variant from the same blueprint.

=== "YAML"

    A standalone script with the same steps. Its values are script fields, so you can pick a ladder each time you run it, or pass them with `data:` from a dashboard button or an automation.

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

Ready-made ladders for the `temperatures` field are on the [Presets](../presets.md#ladders) page.

The script runs in `single` mode, so starting it again while it's running does nothing. If you stop it part-way, it doesn't clean up after itself: turn the fan and heater off yourself.
