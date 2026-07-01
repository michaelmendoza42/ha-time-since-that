# Time Since That

Time Since That is a HACS-installable Home Assistant custom integration for answering one household question: **how long has it been since that thing was last done?**

The current `0.1.0` implementation is chore-focused. You define tracked items in YAML, Home Assistant creates one sensor per item, and calling a service records a completion event. The sensor then shows freshness, recommended cadence status, and household-level interval stats.

## Integration names

| Surface | Current value |
| --- | --- |
| HACS/integration display name | `Time Since That` |
| Integration domain | `time_since_that` |
| YAML root key | `time_since_that` |
| Service | `time_since_that.mark_done` |
| Example entity | `sensor.time_since_that_scoop_cat_litter` |
| Storage key | `time_since_that.history` |

## Status

Early `0.1.0` implementation.

Implemented:

- YAML configuration for tracked chores/items.
- One sensor entity per configured item.
- A `time_since_that.mark_done` service.
- Local Home Assistant storage for completion history.
- User attribution when Home Assistant provides a service-call user context.
- Elapsed freshness display, recommended cadence status, and household-level interval stats.
- Minute-by-minute sensor refreshes so elapsed values continue to age.

Deferred:

- Config flow/options flow.
- Custom Lovelace card.
- Per-user stats.
- Automatic config generation or deployment behavior.

## Installation

### HACS custom repository

1. In HACS, add this repository as a custom repository with category **Integration**.
2. Install **Time Since That**.
3. Restart Home Assistant.

### Manual install

Copy `custom_components/time_since_that` into your Home Assistant config directory:

```text
/config/custom_components/time_since_that
```

Then restart Home Assistant.

## Configuration

Add items to `configuration.yaml`:

```yaml
time_since_that:
  chores:
    - id: scoop_cat_litter
      name: Scoop cat litter
      category: pets
      area: Bathroom
      recommended_every:
        value: 2
        unit: days
      elapsed_display:
        unit: days
        rounding: floor

    - id: refill_humidifier
      name: Refill humidifier
      recommended_every:
        value: 12
        unit: hours
      elapsed_display:
        unit: hours
        rounding: floor

    - id: move_laundry
      name: Move laundry
      recommended_every:
        value: 45
        unit: minutes
      elapsed_display:
        unit: minutes
        rounding: nearest
```

YAML changes require a Home Assistant restart in v1.

### Generate the YAML with the included web app

This repo includes a dependency-free browser helper at [`tools/yaml-generator/index.html`](tools/yaml-generator/index.html). Open it locally, add each task or chore in the form, then copy or download the generated `time_since_that.yaml`.

For split-file configuration, add this to `configuration.yaml`:

```yaml
time_since_that: !include time_since_that.yaml
```

The generator output starts with `chores:`, so it is ready to save as the included `time_since_that.yaml` file.

## Chore fields

| Field | Required | Description |
| --- | --- | --- |
| `id` | yes | Stable lowercase `snake_case` id. Changing this creates a new tracked identity. |
| `name` | yes | Human display name. |
| `category` | no | Optional metadata exposed as a sensor attribute. |
| `area` | no | Optional metadata exposed as a sensor attribute. This does not map to the Home Assistant Area Registry in v1. |
| `recommended_every` | no | Optional recommended cadence with `value` and `unit`. This is guidance, not a scheduler. |
| `elapsed_display` | no | Optional display unit and rounding for elapsed values. Defaults to `days`/`floor`. |

Supported units: `minutes`, `hours`, `days`.

Supported rounding: `floor`, `ceil`, `nearest`.

## What Home Assistant creates

Each configured item creates one sensor, for example:

```text
sensor.time_since_that_scoop_cat_litter
```

Before the item has ever been marked done, the sensor state is:

```text
never
```

After it has history, the sensor state is human-readable:

```text
3 days since
```

Important attributes include:

```yaml
chore_id: scoop_cat_litter
friendly_chore_name: Scoop cat litter
last_done_at: "2026-06-29T10:14:00-04:00"
last_done_by_name: Example User
last_done_by_user_id: user_abc123
completion_count: 18
elapsed: "3 days"
elapsed_value: 3
elapsed_unit: days
recommended_every: "2 days"
recommended_every_value: 2
recommended_every_unit: days
over_recommended: true
over_by: "1 day"
over_by_value: 1
average_interval: "2 days"
average_interval_seconds: 207360
median_interval: "2 days"
median_interval_seconds: 181440
shortest_interval: "1 day"
longest_interval: "5 days"
category: pets
area: Bathroom
```

Full completion history is stored locally but is not exposed as an entity attribute to avoid recorder bloat.

## Marking something done

Use the canonical service action against an entity:

```yaml
service: time_since_that.mark_done
target:
  entity_id: sensor.time_since_that_scoop_cat_litter
```

You can also call it by configured id:

```yaml
service: time_since_that.mark_done
data:
  chore_id: scoop_cat_litter
```

The service records a completion event with timestamp, source, Home Assistant context IDs, and user attribution when Home Assistant provides a user context.

## Example card and flow

There is no custom Lovelace card in v1. The current integration is designed to work with standard Home Assistant entity/button cards or any dashboard card that can read a sensor and call a service.

A simple dashboard concept can look like this:

```text
┌──────────────────────────────────────────────┐
│ TIME SINCE THAT                              │
├──────────────────────────────────────────────┤
│ 🐾 Scoop cat litter                          │
│                                              │
│ 3 days since                                 │
│ Recommended: every 2 days                    │
│ Status: overdue by 1 day                     │
│ Last done by: Example User                   │
│                                              │
│ [ Mark done ]                                │
└──────────────────────────────────────────────┘
```

The current Home Assistant flow behind that card is:

```text
configuration.yaml
  time_since_that.chores[]
        │
        ▼
Home Assistant startup validates YAML
        │
        ▼
Creates sensor.time_since_that_<id>
        │
        ▼
Dashboard shows sensor state + attributes
        │
        ▼
User taps "Mark done"
        │
        ▼
Calls time_since_that.mark_done
        │
        ▼
Completion event saved to .storage
        │
        ▼
Sensor refreshes state and stats
```

Example built-in button card:

```yaml
type: button
entity: sensor.time_since_that_scoop_cat_litter
name: Scoop cat litter
tap_action:
  action: call-service
  service: time_since_that.mark_done
  target:
    entity_id: sensor.time_since_that_scoop_cat_litter
```

Example entity card to show the resulting sensor:

```yaml
type: entity
entity: sensor.time_since_that_scoop_cat_litter
name: Scoop cat litter
attribute: elapsed
```

## Product behavior

See [`docs/behavior.md`](docs/behavior.md) for the v1 behavior contract.

## Privacy

Time Since That stores completion history locally in Home Assistant storage. It makes no network calls and requires no secrets.

This repository is public/shareable. Do not commit machine-specific deployment notes, local Home Assistant access details, server names, credentials, tokens, or AI-agent working context. Keep local deployment notes in a gitignored `LOCAL.md`.

## License

Apache-2.0.

## Development

Run the local pure-Python tests:

```sh
python3 -m unittest discover -s tests
```

Home Assistant validation still requires a Home Assistant development/test environment with the integration dependencies installed. Release readiness should include HACS validation and hassfest.

## Limitations in v1

- YAML configuration only; no config flow/options flow yet.
- No custom Lovelace card or stats screen yet.
- Household-level stats only; per-user stats are stored for future use but not calculated/exposed.
- YAML changes require restart.
- No automatic config generation, restart, or deployment behavior.
