# Fill a bag

A script that fills one bag at the temperature the Volcano is set to:

1. Turns on the Volcano
1. Waits until it reaches its target temperature, and then 10 s more
1. Turns on the fan for 40 s (about how long it takes to nearly fill a standard bag; adjust to yours)
1. Turns off the fan
1. Waits 10 s more, so you can top the bag up with the fan button
1. Turns off the Volcano

If the target isn't reached within 15 minutes, it turns the Volcano off and stops with an error.

=== "Blueprint"

    [![Import the blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FSavageNL%2Fhome-assistant-volcano-hybrid%2Fblob%2Fmain%2Fblueprints%2Fscript%2Fvolcano_hybrid%2Ffill_bag.yaml)

    Click the button, then **Preview** and **Import** in Home Assistant. Create a
    script from it under **Settings** → **Automations & scenes** → **Scripts** →
    **Create script** → the blueprint, pick your Volcano and adjust the values.
    To run several variants (say, two different ladders), create one script per
    variant from the same blueprint.

=== "YAML"

    A standalone script with the same steps. Change `climate.volcano_hybrid` if your device got another name, and the delays to suit your bags.

    ```yaml
    alias: Volcano fill a bag
    description: ""
    mode: single
    variables:
      volcano_entity: climate.volcano_hybrid
      # The Volcano often settles a degree under its target.
      margin: "{{ 1.8 if state_attr(volcano_entity, 'max_temp') | float(0) > 300 else 1 }}"
    sequence:
      - action: climate.turn_on
        target:
          entity_id: "{{ volcano_entity }}"
      - alias: Wait for heatup
        wait_template: >-
          {{ state_attr(volcano_entity, 'current_temperature') | float(0)
          >= state_attr(volcano_entity, 'temperature') | float(0) - margin | float }}
        timeout: "00:15:00"
        continue_on_timeout: true
      - if: "{{ not wait.completed }}"
        then:
          - action: climate.turn_off
            target:
              entity_id: "{{ volcano_entity }}"
          - stop: "Didn't reach the target temperature within 15 minutes"
            error: true
      - alias: Let it settle
        delay:
          seconds: 10
      - action: climate.set_fan_mode
        data:
          fan_mode: "on"
        target:
          entity_id: "{{ volcano_entity }}"
      - alias: Fill the bag
        delay:
          seconds: 40
      - action: climate.set_fan_mode
        data:
          fan_mode: "off"
        target:
          entity_id: "{{ volcano_entity }}"
      - alias: Time to top the bag up
        delay:
          seconds: 10
      - action: climate.turn_off
        target:
          entity_id: "{{ volcano_entity }}"
    ```
