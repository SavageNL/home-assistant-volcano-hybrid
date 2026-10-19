# Presets

## Ladders

Paste one of these into the `temperatures` field of the [bag session](scripts/bag-session.md) or [whip session](scripts/whip-session.md) (all °C, low to high):

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

## Whip sessions

Values for the [whip session](scripts/whip-session.md)'s `temperatures` and `hold_minutes` fields. A single temperature is just a timed hold that turns the Volcano off at the end.

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

Sessions longer than the Volcano's **Auto-off time** need a longer Auto-off time; see the [whip session](scripts/whip-session.md) page.
