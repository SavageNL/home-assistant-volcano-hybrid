# Actions

## Wait for temperature

`volcano_hybrid.wait_for_temperature` waits until a device has heated up to its
current target temperature. Set the target and switch the heater on first, then
call it. Its target is the device's thermostat (`climate`) entity.

| Field | Default | Description |
| --- | --- | --- |
| `tolerance` | `1` | How far below the target still counts as reached, in your Home Assistant temperature unit. The Volcano often settles a degree under its target. |
| `timeout` | 15 minutes | How long to wait before giving up. |

A target at or below the current temperature counts as reached straight away: the
action never waits for the device to cool down.

The wait ends without reaching the target when:

| Reason | What happened |
| --- | --- |
| `timeout` | The timeout passed first. |
| `disconnected` | The device disconnected (or was not connected to begin with). |
| `heater_off` | The heater was switched off, on the device or from Home Assistant. |
| `target_changed` | Someone changed the target temperature during the wait. |

Called on its own, a failed wait stops the script with an error, so a script never
carries on as if the device had heated up. That would leave the heater on, though, so
scripts that switch the device on should ask for the response instead and switch it
off themselves. With a `response_variable`, a failed wait does not raise: the response
holds `reached` and `reason` for each entity.

```yaml
- action: climate.turn_on
  target:
    entity_id: climate.volcano_hybrid
- action: volcano_hybrid.wait_for_temperature
  target:
    entity_id: climate.volcano_hybrid
  data:
    tolerance: 1
    timeout:
      minutes: 15
  response_variable: heatup
- if: "{{ not heatup['climate.volcano_hybrid'].reached }}"
  then:
    - action: climate.turn_off
      target:
        entity_id: climate.volcano_hybrid
    - stop: "Didn't heat up ({{ heatup['climate.volcano_hybrid'].reason }})"
      error: true
```

Every [script](scripts/fill-a-bag.md) on this site waits this way.
