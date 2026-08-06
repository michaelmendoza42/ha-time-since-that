# Time Since That behavior

Time Since That is a Home Assistant config-entry integration for household freshness tracking.

## Reset boundary

Version 1 uses UI-managed chore definitions. It deliberately does not import or alter the early YAML configuration/history model. Existing YAML and legacy history stay untouched as backup data; users create their desired chores in the integration UI.

## Core concepts

- **Chore definition**: UI-managed metadata: immutable internal ID, name, optional category/area/tags, recommended cadence, and elapsed display.
- **Completion event**: a timestamped event recorded by the service, generated button, inline card action, initial last-completed input, or explicit correction.
- **Initial completion**: an optional past date/time supplied when creating a chore. It creates one event with source `initial`.
- **Historical completion insertion**: a past-or-current date/time submitted from the card or `record_completion` service. It appends a distinct event and never replaces existing history. Future values are rejected.
- **Last-completed correction**: an explicit action that changes only the latest completion timestamp, preserving that event's identity and attribution. For a never-completed chore, it creates one initial event instead. It recalculates freshness and interval statistics.
- **Freshness**: time since the latest completion event.
- **Recommended cadence**: optional duration-based guidance, not a scheduler. It accepts minutes, hours, days, weeks, and fixed 30-day months.
- **Tags**: normalized lowercase labels used by aggregate card filters. Category is separate metadata.

## UI management

Use **Settings → Devices & services → Time Since That → Configure** to add, edit, adjust, or remove chores.

- Chore IDs are derived at creation and remain immutable after rename.
- A last-completed value must be a valid past date/time.
- Removing a chore removes its active entities after confirmation. V1 history is retained, but there is no restore UI in this release.

## State and history

Each active chore exposes a freshness sensor and a mark-done button entity.

The v1 history repository uses its own storage namespace and retains event buckets for removed chores. It never reads, writes, imports, or deletes the legacy YAML-era history stores.

Full event history is not exposed as sensor attributes to avoid Recorder bloat. Snapshots sort events chronologically, so inserting an older completion recalculates count and interval statistics without incorrectly replacing the latest completion.

## Dashboard card

For storage-managed Lovelace resources, the integration persistently registers the bundled card as one origin-relative, versioned JavaScript module. This lets desktop and Companion App clients load the same card through LAN or external Home Assistant routes.

YAML-managed Lovelace resources are read-only to integrations. In that advanced mode the integration provides a best-effort frontend fallback, but the user must declare the card module in Lovelace YAML for a durable loading guarantee.

- **All chores mode** discovers active Time Since That sensors, sorts overdue first, and offers card-local tag filtering.
- **One chore mode** displays a selected sensor with inline Mark done and dated-completion actions.
- **Enter completed date** opens a local date/time form below Mark done. Saving converts the local value to an ISO timestamp and appends it through `record_completion`; canceling adds nothing.
- Every chore row derives its primary text from `last_done_at`: minutes, hours, days, weeks, or fixed 30-day months ago. It appends local `HH:MM` when completed less than 24 hours ago, otherwise `DD/MM`.
- Recommended cadence appears as a concise duration-only pill such as `2 weeks`; its tooltip and accessible label identify it as the recommended cadence.
- Average time between completions appears only after the second completion. With exactly two completions it is their single interval; with more completions it is the mean of every consecutive interval.
- Filter selection is ephemeral per card view; it does not change chore definitions.

### Tag filter contract

- `All` is a synthetic aggregate control, not a stored tag.
- A selected `All` represents every available real tag plus `No tag` when untagged chores exist.
- Deselecting selected `All` clears every filter and displays no chores.
- Deselecting an individual filter when All is selected removes only that filter and makes All mixed.
- Re-selecting the final missing filter restores All.
- Multiple selected tags use OR matching.
- `No tag` matches only chores with an empty tags list.
