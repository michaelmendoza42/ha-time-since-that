# Time Since That behavior

Time Since That is a YAML-configured Home Assistant custom integration for household chore freshness tracking.

## Core concepts

- **Chore definition**: static YAML metadata such as `id`, `name`, `category`, `area`, `recommended_every`, and `elapsed_display`.
- **Completion event**: one timestamped household event recorded when someone marks a chore done.
- **Freshness**: how long it has been since the most recent completion event.
- **Recommended cadence**: optional guidance for how often the chore should usually happen. It is not a scheduler.
- **Elapsed display**: how freshness and interval values are rounded and displayed to humans. Internal tracking always stores exact timestamps.
- **Household stats**: v1 calculates stats across all completion events for the chore. Per-user stats are intentionally deferred.

## YAML contract

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
```

### Fields

- `id` is required and should be stable lowercase `snake_case`. Changing it creates a new chore identity.
- `name` is required.
- `category` and `area` are optional strings exposed as sensor attributes for dashboards and future filtering.
- `recommended_every` is optional and supports `minutes`, `hours`, or `days`.
- `elapsed_display` is optional and defaults to `unit: days` and `rounding: floor`.

### Rounding

Supported rounding modes are `floor`, `ceil`, and `nearest`. Rounding affects display state and attributes only; stored timestamps and stats are exact.

## State and history

Each configured chore exposes a freshness sensor and a mark-done button entity. Pressing the button records a completion event for that chore.

The bundled Lovelace card is a dashboard-only convenience layer. Without an explicit entity list, it discovers all Time Since That sensor entities and sorts overdue items first. It reads sensor state/attributes and calls the same mark-done service; it does not store separate state.

Completion history is stored locally in Home Assistant `.storage` using a versioned storage key. The integration stores timestamp, source, Home Assistant context IDs, and user attribution when Home Assistant provides a user context.

Full event history is not exposed as sensor attributes to avoid recorder bloat.

## Removed chores

Removing a chore from YAML stops exposing an entity for that chore, but v1 does not intentionally delete stored history. Re-adding the same `id` can reuse the stored history.
