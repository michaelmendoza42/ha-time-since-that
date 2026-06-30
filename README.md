# Chore Tracker

Chore Tracker is a HACS-installable Home Assistant custom integration for household chore freshness tracking.

It lets you define chores in YAML, mark a chore done from Home Assistant, and see how long it has been since the chore was last completed. It also tracks optional recommended cadence and household-level cadence stats.

## Status

Early `0.1.0` implementation. YAML configuration is the v1 interface; config flow, custom Lovelace cards, and per-user stats are deferred.

## Installation

### HACS custom repository

1. In HACS, add this repository as a custom repository with category **Integration**.
2. Install **Chore Tracker**.
3. Restart Home Assistant.

### Manual install

Copy `custom_components/chore_tracker` into your Home Assistant config directory:

```text
/config/custom_components/chore_tracker
```

Then restart Home Assistant.

## Configuration

Add chores to `configuration.yaml`:

```yaml
chore_tracker:
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

## Chore fields

| Field | Required | Description |
| --- | --- | --- |
| `id` | yes | Stable lowercase `snake_case` id. Changing this creates a new chore identity. |
| `name` | yes | Human display name. |
| `category` | no | Optional metadata exposed as an attribute. |
| `area` | no | Optional metadata exposed as an attribute. This does not map to the HA Area Registry in v1. |
| `recommended_every` | no | Optional recommended cadence with `value` and `unit`. |
| `elapsed_display` | no | Optional display unit and rounding for elapsed values. Defaults to days/floor. |

Supported units: `minutes`, `hours`, `days`.

Supported rounding: `floor`, `ceil`, `nearest`.

## Entities

Each configured chore creates one sensor, for example:

```text
sensor.chore_scoop_cat_litter
```

The sensor state is human-readable:

```text
3 days since
```

Important attributes include:

```yaml
chore_id: scoop_cat_litter
friendly_chore_name: Scoop cat litter
last_done_at: "2026-06-29T10:14:00-04:00"
last_done_by_name: Michael
last_done_by_user_id: abc123
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

## Marking a chore done

Use the canonical service action:

```yaml
service: chore_tracker.mark_done
target:
  entity_id: sensor.chore_scoop_cat_litter
```

You can also call it by chore id:

```yaml
service: chore_tracker.mark_done
data:
  chore_id: scoop_cat_litter
```

This records a completion event with timestamp, source, Home Assistant context, and user attribution when Home Assistant provides a user context.

### Example dashboard button

```yaml
type: button
name: Scoop cat litter done
tap_action:
  action: call-service
  service: chore_tracker.mark_done
  target:
    entity_id: sensor.chore_scoop_cat_litter
```

## Product behavior

See [`docs/behavior.md`](docs/behavior.md) for the v1 behavior contract.

## Privacy

Chore Tracker stores completion history locally in Home Assistant storage. It makes no network calls and requires no secrets.

This repository is public/shareable. Machine-specific deployment notes should live in a gitignored `LOCAL.md`, not in public docs.

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
- No automatic config generation, restart, or HAOS deployment behavior.
