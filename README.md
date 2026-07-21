# Time Since That

Time Since That is a HACS-installable Home Assistant integration for one question: **how long has it been since that thing was last done?**

Create chores in Home Assistant, optionally seed their last-completed date/time, and place either an all-chores or single-chore card on a dashboard.

## Version 1 reset

Version `1.0.0` replaces the early YAML prototype with UI-managed chores.

Before updating from an earlier version:

1. Create a full Home Assistant backup.
2. Keep your existing `time_since_that:` YAML and old history files as backup material.
3. Update the integration and restart Home Assistant.
4. Re-create the chores you want in the integration UI. Use **Last completed** to seed each starting state.
5. Verify the new entities/cards, then remove the old YAML block.

This is intentionally **not a migration**: v1 does not import, modify, or delete the old YAML-era history stores.

## Install

1. In HACS, add this repository as a custom repository with category **Integration**.
2. Install or update **Time Since That**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Time Since That**.

## Manage chores

Open **Settings → Devices & services → Time Since That → Configure**.

Use the menu to:

- **Add chore** — choose a name, optional category/area/tags/cadence, and optional initial last-completed date/time.
- **Edit chore** — update display metadata, tags, cadence, and elapsed display.
- **Adjust last completed** — correct the latest completion timestamp. This changes freshness and interval statistics, so it is deliberately separate from ordinary editing.
- **Remove chore** — removes active entities after confirmation while retaining v1 history for safety.

### Tags

Tags are optional comma-separated labels in the chore form, such as:

```text
pets, daily
```

They are normalized to lowercase. `category` remains separate metadata; it is not automatically treated as a tag.

## Entities

Each chore creates:

```text
sensor.time_since_that_scoop_cat_litter
button.mark_scoop_cat_litter_done
```

The sensor shows `never` until the first completion, then a state such as `3 days since`. Its attributes include:

```yaml
chore_id: scoop_cat_litter
tags:
  - pets
  - daily
last_done_at: "2026-07-20T10:30:00-04:00"
completion_count: 18
elapsed: "3 days"
over_recommended: true
over_by: "1 day"
```

The generated button and `time_since_that.mark_done` service both record a new completion event.

## Dashboard cards

The integration automatically registers the custom card; you do **not** add a dashboard Resource URL manually.

### All chores card

Dashboard → Add card → **Time Since That Card**, then choose **All chores**.

Equivalent YAML:

```yaml
type: custom:time-since-that-card
title: Time Since That
```

The card discovers active chores, shows overdue items first, and offers tag filters.

### One chore per card

Dashboard → Add card → **Time Since That Card**, choose **One chore**, then select the chore.

Equivalent YAML:

```yaml
type: custom:time-since-that-card
title: Cat litter
entity: sensor.time_since_that_scoop_cat_litter
```

The card displays that chore plus an inline **Mark done** action.

### Tag filters

Aggregate cards show `All`, every real tag, and `No tag` when needed.

- Initially, **All** is selected.
- Select one or more tags to show chores with **any** selected tag.
- Select **No tag** to show untagged chores.
- Tap selected **All** to deselect every filter and show no chores.
- When All is selected, deselecting one tag soft-deselects All while keeping other filters selected.

## Service

Automations can mark a chore done by entity:

```yaml
service: time_since_that.mark_done
target:
  entity_id: sensor.time_since_that_scoop_cat_litter
```

Or by the immutable chore ID:

```yaml
service: time_since_that.mark_done
data:
  chore_id: scoop_cat_litter
```

## Privacy

Time Since That stores its v1 completion history locally in Home Assistant. It makes no network calls and requires no secrets.

This repository is public/shareable. Do not commit machine-specific deployment notes, access details, credentials, tokens, or AI-agent working context.

## Legacy YAML generator

[`tools/yaml-generator/index.html`](tools/yaml-generator/index.html) remains available as a reference/drafting tool for the retired YAML prototype. It is not used by v1 runtime configuration.

## Development

```sh
python3 -m unittest discover -s tests
```

Home Assistant config-flow validation requires a Home Assistant-compatible test environment. Browser-observable card behavior is exercised by the frontend harnesses in `tests/frontend/`.

## License

Apache-2.0.
