# Project Context

## Purpose and Scope

Time Since That is a HACS-installable Home Assistant helper integration for tracking how long it has been since household chores were completed. Version 1 is configured through Home Assistant config entries, stores completion history locally, exposes one sensor and one mark-done button per chore, and bundles a Lovelace custom card.

This map describes the architecture observed in the repository as of Home Assistant integration version `1.0.4`. It distinguishes current runtime behavior from the retired YAML prototype under `tools/yaml-generator/` and `examples/`.

## Stack

### Runtime

- **Python 3 / Home Assistant custom integration** under `custom_components/time_since_that/`.
- **Home Assistant config entries and options flows** for singleton household/chore configuration.
- **Home Assistant entity platforms**: `sensor` and `button`.
- **Home Assistant `Store`** for local JSON completion-event persistence.
- **Voluptuous** and Home Assistant selectors for config, service, and form validation.
- **Vanilla JavaScript Web Components** for the bundled Lovelace card and card editor; there is no Lit, React, build step, or frontend bundler.
- **Home Assistant frontend/Lovelace APIs** for static file serving and persistent module-resource registration.

### Declared dependencies and compatibility

- `custom_components/time_since_that/manifest.json` declares no third-party Python requirements. Runtime libraries are supplied by Home Assistant.
- Manifest dependencies are `frontend` and `lovelace`.
- `hacs.json` declares Home Assistant `2024.6.0` as the minimum supported version.
- Compatibility branches in `__init__.py` support both `async_register_static_paths` and the older `register_static_path` API.
- The integration is `single_config_entry`, `integration_type: helper`, and `iot_class: calculated`.
- The integration makes no external network calls and requires no credentials.

### Development and CI

- Python tests use the standard-library `unittest` runner.
- Browser tests use `@playwright/test` `^1.61.1` and a small local Node HTTP server.
- `npm test` runs Python tests followed by the Playwright card suite.
- Pyright is configured in `basic` mode, with missing Home Assistant imports and module sources suppressed for local development.
- GitHub Actions separately run Python unit tests, HACS validation, and Hassfest. The Tests workflow currently does not install Node dependencies or run Playwright.

## Architecture

### Architectural style

The code is a compact layered Home Assistant integration with an event-history core:

1. **Composition and Home Assistant lifecycle** — `custom_components/time_since_that/__init__.py`
2. **Configuration/UI boundary** — `config_flow.py`, `config_schema.py`, strings/translations
3. **Application orchestration and persistence** — `manager.py`
4. **Pure domain model and calculations** — `model.py`
5. **Home Assistant projections/actions** — `sensor.py`, `button.py`, `services.yaml`
6. **Frontend resource adapter** — `frontend_resources.py`
7. **Browser UI** — `frontend/time-since-that-card.js`

The domain model is mostly independent of Home Assistant. The manager adapts domain objects to Home Assistant context, time, storage, and listeners. Entity and frontend layers project the manager's derived state rather than owning chore history.

### Sources of truth

- **Active chore definitions:** config-entry `data` initially, then config-entry `options` after the first options update.
- **Completion history:** Home Assistant `Store` key `time_since_that.v1_history`, version `1`.
- **Current sensor state:** calculated on demand from a `ChoreDefinition`, its completion events, and current time.
- **Durable behavioral contract:** `docs/behavior.md`.
- **User-facing setup and operations:** `README.md`.
- **Card filter selection:** ephemeral state inside each card instance; it is not persisted.

The early YAML configuration and legacy history are deliberately outside the v1 runtime. `config_schema.py` accepts an old `time_since_that:` root only so setup can warn and ignore it. The standalone YAML generator is retained as a legacy reference tool.

### Entry points

#### Integration lifecycle

- `async_setup` registers the domain service and bundled frontend once per Home Assistant process. If legacy YAML is present, it logs a warning and does not instantiate YAML chores.
- `async_setup_entry` loads v1 history, reads and validates chore definitions, creates the runtime manager, seeds initial completion events when necessary, stores runtime references in `hass.data`, and forwards sensor/button platform setup.
- `async_unload_entry` unloads both platforms and removes runtime manager references after a successful unload.
- The config-entry update listener reloads the entry after chore option changes.

#### User configuration

- `TimeSinceThatConfigFlow` creates the singleton household entry and its first chore.
- `TimeSinceThatOptionsFlow` provides add, edit, adjust-last-completed, and remove operations.
- Chore IDs are generated from the initial name, validated as lowercase snake_case, and preserved when display metadata changes.

#### User actions

- `time_since_that.mark_done` accepts either `entity_id` target(s) or an immutable `chore_id`.
- Each generated `button` calls the same manager operation with source `button`.
- The Lovelace card calls the service with a sensor `entity_id`.

### Primary data flows

#### Setup and projection

```text
Config entry data/options
  -> definition_from_dict + validate_chore_definitions
  -> immutable ChoreDefinition objects
  -> TimeSinceThatManager + TimeSinceThatHistoryRepository
  -> one ChoreSensor and one MarkDoneButton per chore
```

#### Completion mutation

```text
Service, entity button, card, initial seed, or correction
  -> TimeSinceThatManager
  -> CompletionEvent with UUID, timestamp, source, and optional HA context/user
  -> TimeSinceThatHistoryRepository
  -> full v1 event-map save through Home Assistant Store
  -> manager listeners
  -> sensor state writes
```

Normal completions append events. The explicit last-completed correction replaces only the chronologically latest event's timestamp while preserving event identity and attribution. If a chore has no event, correction creates an initial event.

#### Snapshot calculation

```text
ChoreSensor native value / attributes
  -> manager.snapshot(chore_id)
  -> build_snapshot(definition, copied events, current HA time)
  -> freshness, overdue state, completion count, and interval statistics
```

Sensors are non-polling entities, but each sensor schedules a one-minute Home Assistant callback so elapsed values advance even without mutations.

#### Dashboard flow

```text
Integration static path + Lovelace module resource
  -> browser loads time-since-that-card.js
  -> card scans hass.states for matching sensors
  -> card renders attributes and local ephemeral filters
  -> Mark done calls time_since_that.mark_done
  -> HA state propagation assigns a new hass snapshot
  -> full card rerender
```

### Domain model

- `ChoreDefinition` contains immutable ID, display metadata, tags, optional recommended cadence, and elapsed-display settings.
- `CompletionEvent` contains event identity, chore identity, timezone-aware completion time, optional user/context attribution, and source.
- `ChoreSnapshot` is a calculated state string plus Home Assistant attribute dictionary.
- Recommended cadence supports minutes, hours, days, weeks, and fixed 30-day months.
- Elapsed display supports minutes, hours, and days with floor, ceil, or nearest rounding.
- History is event-oriented and retained for removed chores; no restore or purge UI currently exists.

### Storage and concurrency

`TimeSinceThatHistoryRepository` keeps in-memory event buckets and serializes append/correction writes with an `asyncio.Lock`. Each mutation saves the complete v1 event map. Removed chore buckets remain in storage by design. Stored payloads are validated during load and malformed/version-mismatched payloads raise `ValueError`.

### Frontend architecture

`TimeSinceThatCard` and `TimeSinceThatCardEditor` are native custom elements with open Shadow DOM. They depend on a deliberately small Home Assistant browser API:

- `hass.states`
- `hass.callService(domain, service, data)`
- Home Assistant's `config-changed` card-editor event convention
- `window.customCards` metadata registration for card-picker discovery

The card supports:

- automatic aggregate discovery;
- explicit entity lists;
- single-chore mode;
- automatic aggregate ordering by overdue state, raw `elapsed_value`, then name;
- caller-preserved ordering for explicit entity lists;
- local tag filters with synthetic `All` and `No tag` states;
- inline mark-done actions;
- local browser date/time presentation.

Every update rebuilds the card's shadow tree with `replaceChildren`. The filter state is reconciled before rendering and focus is restored for the most recently toggled filter.

## Conventions Observed

### Naming and data shapes

- Python, stored dictionaries, Home Assistant attributes, and service fields use **snake_case**.
- Chore IDs use lowercase snake_case and are treated as immutable identity.
- JavaScript internals use **camelCase**; Home Assistant entity attributes remain snake_case at the browser boundary.
- Stored and service data are plain dictionaries rather than formal JSON Schema objects.
- Domain values use frozen, slotted Python dataclasses.
- Entity unique IDs derive deterministically from chore IDs.

### Error handling

- Form validation converts domain/date errors into translated Home Assistant flow error keys.
- Domain validation raises `ChoreConfigError`, a `ValueError` subtype.
- Invalid persisted history or definitions fail entry setup rather than being skipped or repaired.
- Service target-shape errors use `vol.Invalid`; an explicit unknown chore ID currently bubbles as `ValueError` from the manager.
- User-name lookup is best effort: selected lookup errors are caught, logged at debug, and attribution falls back to `None`.
- The card catches service-call failures, displays the message in a `role="alert"` element, and clears its pending state.
- Frontend resource reconciliation distinguishes mutable storage resources from read-only/YAML resources and falls back to `add_extra_js_url` when persistence is unavailable.

There is no global integration error handler or recovery subsystem. Most unexpected Home Assistant/storage failures bubble to Home Assistant's setup or service machinery.

### API style

There is no REST, GraphQL, or custom HTTP API. The integration uses Home Assistant's internal extension points:

- config-entry/config-flow callbacks;
- entity state and attributes;
- a domain service (`time_since_that.mark_done`), effectively an HA RPC/action boundary;
- Home Assistant Store persistence;
- Lovelace resource collection APIs;
- one static JavaScript path.

The frontend/backend contract is the sensor attribute dictionary plus the service target shape.

### Type safety

- The pure model uses Python type annotations and frozen, slotted dataclasses; manager and entity layers use annotated mutable classes.
- Home Assistant boundary code uses several `Any` annotations and selective `type: ignore` comments to remain importable/testable without Home Assistant installed.
- Pyright runs in `basic` mode and suppresses missing HA imports; current repository CI does not invoke Pyright.
- The frontend is untyped JavaScript with runtime checks only for basic card configuration shape.
- No formal interface/protocol isolates Home Assistant storage, config entries, or Lovelace resources; tests rely on duck-typed fakes.

### Observability

- Python uses standard module loggers.
- Existing logs cover ignored legacy YAML, frontend-resource outcomes/duplicates/fallback, and failed user-name resolution.
- There is no structured logging schema, metrics, health endpoint, tracing, or external telemetry.
- Browser service errors are user-visible but are not emitted to a diagnostic channel.
- Home Assistant supplies the host logging/runtime environment; this integration has no health implementation of its own.

### Testing

- **Pure unit tests:** model normalization, validation, cadence conversion, duration rounding, snapshots, and interval statistics.
- **Adapter unit tests:** Lovelace resource create/update/idempotence/read-only behavior with fake collections.
- **Browser regression tests:** real card JavaScript in a lightweight HTML harness with a fake `hass` object; tests cover filter transitions, adaptive last-done text, editor mode selection, and service payloads.
- **Repository validation:** HACS and Hassfest workflows.

Tests are deterministic and narrow: UTC/fixed clocks, standard-library unittest, duck-typed fakes, and Playwright `expect.poll`. They do not currently boot Home Assistant or exercise the complete config-entry/entity/service lifecycle.

## Integration and Release Boundaries

- **HACS:** consumes `hacs.json`, `manifest.json`, repository layout, and release tags/version metadata.
- **Home Assistant:** supplies config-entry, entity, storage, service, auth, frontend, HTTP, and Lovelace APIs.
- **Lovelace resource modes:** storage-managed resources are reconciled persistently; YAML-managed resources require a documented user-owned module declaration for a durable guarantee.
- **Browser/backend contract:** entity IDs/prefixes, sensor attribute names, and `time_since_that.mark_done` payload.
- **Private deployment:** `LOCAL.md` is intentionally ignored and must not be copied into public artifacts; deployment must use the referenced approved `macos-management` flow rather than ad hoc SSH.

## Signals / Active Considerations

### Higher-priority validation gaps

1. **Home Assistant lifecycle coverage is absent.** Config flow, options flow, setup/unload/reload, service targeting, Store failure behavior, and entity registry behavior are not exercised in a Home Assistant-compatible test environment.
2. **Playwright is not enforced by the GitHub Tests workflow.** `npm test` includes browser regressions, but CI's Tests job runs only Python unittest discovery.
3. **Persistent-data failure behavior is fail-fast.** Malformed storage/config data prevents entry setup, and storage save failure can leave in-memory history ahead of durable history because mutation precedes `async_save`.

### Coupling and evolution risks

1. `hass.data[DOMAIN][DATA_MANAGER]` relies on the manifest's singleton-entry guarantee. Multi-entry support would require entry-scoped service/entity resolution.
2. The card and editor both discover chores by hard-coded `sensor.time_since_that_` prefix plus `attributes.chore_id`. Changes to domain/platform/entity contracts must update backend, card, editor, docs, and browser fixtures together.
3. The frontend rebuilds its entire DOM on every Home Assistant state assignment. This favors simplicity but may become expensive with many chores or frequent global state updates.
4. One card-wide pending action blocks all mark-done buttons until the active call resolves; there is no timeout or confirmation that the next state snapshot reflects the mutation.
5. Frontend resource reconciliation depends on Home Assistant Lovelace collection shapes and intentionally leaves duplicate owned-path records untouched.
6. Every repository mutation saves the full event history. Storage cost grows with retained events and removed-chore buckets.

### Consistency and debt signals

- Version values are duplicated and currently disagree: manifest/card URL use `1.0.4`, while `package.json` and `const.VERSION` use `1.0.0`.
- User-facing card/editor strings and date formatting are hard-coded English and do not use Home Assistant localization.
- `examples/configuration.yaml` and `tools/yaml-generator/` still emit the retired YAML model. README labels the generator legacy, but these artifacts can still imply a supported runtime path unless maintained carefully.
- A large implementation plan is tracked under a sentence-like root filename, and timestamped plan artifacts also exist at the repository root. These are planning/workspace hygiene signals rather than runtime architecture.
- The existing plan identified mixed-unit elapsed sorting as a concern. The current card compares raw `elapsed_value`, so values expressed in different units are not directly comparable after overdue status.
- Listener callbacks are invoked without per-listener exception isolation; one failing listener can prevent later listeners from being notified.
- Removed history has no cleanup or restore path. Reusing a removed chore ID can reconnect the new definition to retained events and suppress initial seeding.
- Pyright exists but is not enforced in CI, and broad `Any` use remains at Home Assistant boundaries.
- GitHub HACS/Hassfest actions follow moving `main`/`master` refs rather than pinned revisions.

## Surprises and Deltas From Surface Documentation

- The repository is not merely a Python integration: it ships a substantial unbundled custom card/editor and therefore has two runtime surfaces and two test ecosystems.
- The v1 model is not purely append-only event sourcing because the explicit correction flow mutates the latest event timestamp while preserving identity/attribution.
- Active definitions and history have separate persistence mechanisms and lifecycles: config-entry data/options versus Home Assistant Store.
- The documented `npm test` baseline is broader than the GitHub Tests workflow.
- The legacy YAML generator remains tracked even though YAML is ignored by the v1 runtime.

## Change Guidance

- Start backend behavior work in `model.py` and `manager.py`, then propagate contract changes through config flow, entities/services, docs, and tests.
- Start lifecycle/integration work in `__init__.py`; verify setup, unload, service registration, and singleton assumptions together.
- Treat sensor attributes and service payloads as a versioned frontend/backend contract even though no explicit schema file exists.
- Update `docs/behavior.md` and Playwright coverage for browser-observable behavior changes.
- Keep legacy-storage isolation and retained-history behavior explicit in any persistence work.
- Validate against the Home Assistant `2024.6.0` compatibility floor before adopting newer APIs.
- Keep this document evidence-based: refresh it when architecture, source-of-truth ownership, runtime dependencies, or major validation strategy changes.
