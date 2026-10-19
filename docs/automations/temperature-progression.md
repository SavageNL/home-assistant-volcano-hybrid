# Temperature progression

Steps the target temperature up a ladder while the Volcano runs: the first rung when it switches on, the next one every 5 minutes, then it stays on the last. The default ladder follows the [Vapesuvius temp guide](https://www.reddit.com/user/Vapesuvius/comments/zuwcs7/vapesuvius_unofficial_storz_bickel_temp_guide_2nd/) (for temperature, not time). A temperature you set by hand stays until the next rung starts.

!!! note "Enable the Current on time sensor first"
    The automation follows the Volcano's **Current on time** sensor, which is disabled by default. Enable it under **Settings** → **Devices & services** → the Volcano → the entity → gear icon → **Enabled**.

=== "Blueprint"

    [![Import the blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FSavageNL%2Fhome-assistant-volcano-hybrid%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fvolcano_hybrid%2Ftemperature_progression.yaml)

    Click the button, then **Preview** and **Import** in Home Assistant. Create an automation from it, pick your Volcano and its Current on time sensor, and set the ladder and the minutes per rung.

=== "YAML"

    A standalone automation with the same logic. Change the entity ids if your device got another name, and `ladder` and `step_minutes` to taste.

    ```yaml
    alias: Volcano progress
    description: ""
    mode: queued
    max_exceeded: silent
    variables:
      volcano_entity: climate.volcano_hybrid
      # Rungs in °C, one per interval; it stays on the last one.
      ladder: [179, 185, 191, 199, 205]
      step_minutes: 5
    triggers:
      - trigger: state
        entity_id: sensor.volcano_hybrid_current_on_time
    conditions:
      - alias: Running, and not just reconnected
        condition: template
        value_template: >-
          {{ trigger.to_state is not none
          and trigger.to_state.state | is_number
          and (trigger.from_state is none
               or trigger.from_state.state != 'unavailable') }}
    actions:
      - variables:
          last: "{{ ladder | count - 1 }}"
          index: >-
            {{ [(trigger.to_state.state | float // step_minutes | float) | int,
            last] | min }}
          # Off is "unknown", so switching on counts as moving onto the first rung.
          previous: >-
            {% if trigger.from_state is not none
            and trigger.from_state.state | is_number %}
            {{ [(trigger.from_state.state | float // step_minutes | float) | int,
            last] | min }}
            {% else %}-1{% endif %}
      - alias: Only when a new rung starts, so a manual change sticks until the next
        condition: template
        value_template: "{{ index | int != previous | int }}"
      - variables:
          celsius: "{{ ladder[index | int] | float }}"
          rung: >-
            {{ ((celsius * 9 / 5 + 32) | round(1))
            if state_attr(volcano_entity, 'max_temp') | float(0) > 300
            else celsius }}
      - action: climate.set_temperature
        data:
          temperature: "{{ rung }}"
        target:
          entity_id: "{{ volcano_entity }}"
    ```
