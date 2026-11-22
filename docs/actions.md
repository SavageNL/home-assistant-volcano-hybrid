# Actions

## Wait for temperature

`volcano_hybrid.wait_for_temperature` heats a device up and waits until it has
reached its target: it can set the target (`temperature`) and switch the heater on
(`turn_on`) first, so one step does what would otherwise take three. Its target is
the device's thermostat (`climate`) entity.

| Field | Default | Description |
| --- | --- | --- |
| `temperature` | — | Set this target first, in your Home Assistant temperature unit, as `climate.set_temperature` takes it. Leave it out to wait for the current target. |
| `turn_on` | `false` | Switch the heater on first if it is off. |
| `tolerance` | `0` | How far below the target still counts as reached, in your Home Assistant temperature unit. |
| `timeout` | 15 minutes | How long to wait before giving up. |

A target at or below the current temperature counts as reached straight away: the
action never waits for the device to cool down.

The wait ends without reaching the target when:

| Reason | What happened |
| --- | --- |
| `timeout` | The timeout passed first. |
| `disconnected` | The device stayed disconnected for 30 seconds. |
| `heater_off` | The heater stayed off for 15 seconds, switched off on the device or from Home Assistant. |
| `target_changed` | Someone changed the target temperature during the wait. |

The grace periods are there because neither reading is steady: a Volcano that is
switching on can report its heater off for a second or two, and a Bluetooth
connection can drop for a few seconds while the device carries on heating. A device
that is not connected when the action is called is refused straight away by Home
Assistant, since its thermostat entity is unavailable.

Called on its own, a failed wait stops the script with an error, so a script never
carries on as if the device had heated up. That would leave the heater on, though, so
scripts that switch the device on should ask for the response instead and switch it
off themselves. With a `response_variable`, a failed wait does not raise: the response
holds `reached` and `reason` for each entity.

```yaml
- action: volcano_hybrid.wait_for_temperature
  target:
    entity_id: climate.volcano_hybrid
  data:
    temperature: 190
    turn_on: true
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
