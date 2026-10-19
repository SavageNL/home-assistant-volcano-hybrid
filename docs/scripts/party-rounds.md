# Party rounds

Bags for a group at one temperature: heats up, gives you time to fit the first bag, then fills a bag every few minutes. It stops after a set number of bags and turns the Volcano off, so it can't run on unattended.

=== "Blueprint"

    [![Import the blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FSavageNL%2Fhome-assistant-volcano-hybrid%2Fblob%2Fmain%2Fblueprints%2Fscript%2Fvolcano_hybrid%2Fparty_rounds.yaml)

    Click the button, then **Preview** and **Import** in Home Assistant. Create a
    script from it under **Settings** → **Automations & scenes** → **Scripts** →
    **Create script** → the blueprint, pick your Volcano and adjust the values.
    To run several variants (say, two different ladders), create one script per
    variant from the same blueprint.

=== "YAML"

    A standalone script with the same steps. Its values are script fields, so you can pick a ladder each time you run it, or pass them with `data:` from a dashboard button or an automation.

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

The script runs in `single` mode, so starting it again while it's running does nothing. If you stop it part-way, it doesn't clean up after itself: turn the fan and heater off yourself.
