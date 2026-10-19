# Hands-free whip session

The same ladder for whip use: instead of filling bags it holds each temperature for a few minutes, then moves to the next. The fan is left to you.

!!! warning "Set the Auto-off time longer than the session"
    The Volcano switches itself off when its **Auto-off time** runs out, counted from when the heater or fan was switched on. This script never touches the fan, so nothing restarts that countdown: a session longer than the Auto-off time (30 minutes by default) is cut short by the device, and the script then stops with a timeout on the next rung.

=== "Blueprint"

    [![Import the blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FSavageNL%2Fhome-assistant-volcano-hybrid%2Fblob%2Fmain%2Fblueprints%2Fscript%2Fvolcano_hybrid%2Fwhip_session.yaml)

    Click the button, then **Preview** and **Import** in Home Assistant. Create a
    script from it under **Settings** → **Automations & scenes** → **Scripts** →
    **Create script** → the blueprint, pick your Volcano and adjust the values.
    To run several variants (say, two different ladders), create one script per
    variant from the same blueprint.

=== "YAML"

    A standalone script with the same steps. Its values are script fields, so you can pick a ladder each time you run it, or pass them with `data:` from a dashboard button or an automation.

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

Ready-made sessions for the `temperatures` and `hold_minutes` fields are on the [Presets](../presets.md#whip-sessions) page.

The script runs in `single` mode, so starting it again while it's running does nothing. If you stop it part-way, it doesn't clean up after itself: turn the fan and heater off yourself.
