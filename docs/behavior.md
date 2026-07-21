# Time Since That behavior

Time Since That is a Home Assistant config-entry integration for household freshness tracking.

## Reset boundary

Version 1 uses UI-managed chore definitions. It deliberately does not import or alter the early YAML configuration/history model. Existing YAML and legacy history stay untouched as backup data; users create their desired chores in the integration UI.

## Core concepts

- **Chore definition**: UI-managed metadata: immutable internal ID, name, optional category/area/tags, recommended cadence, and elapsed display.
- **Completion event**: a timestamped event recorded by the service, generated button, inline card action, initial last-completed input, or explicit correction.
- **Initial completion**: an optional past date/time supplied when creating a chore. It creates one event with source `initial`.
- **Last-completed correction**: an explicit action that changes only the latest completion timestamp, preserving that event's identity and attribution. For a never-completed chore, it creates one initial event instead. It recalculates freshness and interval statistics.
- **Freshness**: time since the latest completion event.
- **Recommended cadence**: optional guidance, not a scheduler.
- **Tags**: normalized lowercase labels used by aggregate card filters. Category is separate metadata.

## UI management

Use **Settings → Devices & services → Time Since That → Configure** to add, edit, adjust, or remove chores.

- Chore IDs are derived at creation and remain immutable after rename.
- A last-completed value must be a valid past date/time.
- Removing a chore removes its active entities after confirmation. V1 history is retained, but there is no restore UI in this release.

## State and history

Each active chore exposes a freshness sensor and a mark-done button entity.

The v1 history repository uses its own storage namespace and retains event buckets for removed chores. It never reads, writes, imports, or deletes the legacy YAML-era history stores.

Full event history is not exposed as sensor attributes to avoid Recorder bloat.

## Dashboard card

The bundled card is registered automatically by the integration.

- **All chores mode** discovers active Time Since That sensors, sorts overdue first, and offers card-local tag filtering.
- **One chore mode** displays a selected sensor with one inline Mark done action.
- Filter selection is ephemeral per card view; it does not change chore definitions.

### Tag filter contract

- `All` is a synthetic aggregate control, not a stored tag.
- A selected `All` represents every available real tag plus `No tag` when untagged chores exist.
- Deselecting selected `All` clears every filter and displays no chores.
- Deselecting an individual filter when All is selected removes only that filter and makes All mixed.
- Re-selecting the final missing filter restores All.
- Multiple selected tags use OR matching.
- `No tag` matches only chores with an empty tags list.
