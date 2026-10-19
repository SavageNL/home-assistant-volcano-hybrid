# Step the temperature up or down

Two actions that move the target to the next or previous step of the Vapesuvius temp guide. They're building blocks for your own automation; for example, with a dimmer switch:

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
