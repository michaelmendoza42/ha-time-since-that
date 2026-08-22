const NO_TAG_FILTER = "__time_since_that_no_tag__";
const ALL_FILTER = "__time_since_that_all__";
const SORT_OPTIONS = [
  ["due-asc", "Due date: soonest first"],
  ["due-desc", "Due date: latest first"],
  ["interval-asc", "Recommended interval: shortest first"],
  ["interval-desc", "Recommended interval: longest first"],
];

class TimeSinceThatCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = undefined;
    this._pendingEntityId = undefined;
    this._dateEntryEntityId = undefined;
    this._dateEntryValues = new Map();
    this._focusDateEntityId = undefined;
    this._focusDateTarget = undefined;
    this._error = undefined;
    this._selectedFilters = new Set();
    this._previousFilterKeys = new Set();
    this._filtersInitialized = false;
    this._focusFilterKey = undefined;
    this._sort = "due-asc";
    this._historyByEntity = new Map();
    this._historyOpenEntityId = undefined;
    this._historyLoadingEntityId = undefined;
    this._historyEditEventId = undefined;
    this._historyEditValues = new Map();
    this._focusHistoryEventId = undefined;
    this._focusHistoryTarget = undefined;
  }

  setConfig(config) {
    if (!config) {
      throw new Error("Time Since That card needs a configuration object.");
    }
    if (config.entities !== undefined && !Array.isArray(config.entities)) {
      throw new Error("The optional entities value must be an array.");
    }

    this._config = {
      title: "Time Since That",
      show_tag_filters: true,
      ...config,
      entities: config.entities?.map((entry) =>
        typeof entry === "string" ? { entity: entry } : entry,
      ),
    };
    this._sort = SORT_OPTIONS.some(([value]) => value === config.sort)
      ? config.sort
      : "due-asc";
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return Math.max(3, this._visibleEntries().entries.length * 2);
  }

  static getStubConfig() {
    return { title: "Time Since That" };
  }

  static getConfigElement() {
    return document.createElement("time-since-that-card-editor");
  }

  _isSingleMode() {
    return Boolean(this._config.entity);
  }

  _sourceEntries() {
    if (this._config.entity) {
      return this._sortEntries([{ entity: this._config.entity }]);
    }
    if (this._config.entities) {
      return this._sortEntries(this._config.entities);
    }

    return this._sortEntries(Object.entries(this._hass?.states || {})
      .filter(
        ([entityId, stateObj]) =>
          entityId.startsWith("sensor.time_since_that_") &&
          Boolean(stateObj.attributes?.chore_id),
      )
      .map(([entity]) => ({ entity })));
  }

  _sortEntries(entries) {
    return [...entries].sort((left, right) => this._compareEntries(left, right));
  }

  _compareEntries(left, right) {
    const leftValue = this._sortValue(left);
    const rightValue = this._sortValue(right);
    if (leftValue === null || rightValue === null) {
      if (leftValue === rightValue) {
        return this._compareNames(left, right);
      }
      return leftValue === null ? 1 : -1;
    }
    const direction = this._sort.endsWith("-desc") ? -1 : 1;
    const valueDelta = (leftValue - rightValue) * direction;
    return valueDelta || this._compareNames(left, right);
  }

  _sortValue(entry) {
    const attributes = this._hass?.states?.[entry.entity]?.attributes || {};
    if (this._sort.startsWith("interval")) {
      const value = Number(attributes.recommended_every_value);
      const unit = attributes.recommended_every_unit;
      const unitMs = { minutes: 60_000, hours: 3_600_000, days: 86_400_000, weeks: 604_800_000, months: 2_592_000_000 }[unit];
      return Number.isFinite(value) && value > 0 && unitMs ? value * unitMs : null;
    }
    const lastDoneAt = new Date(attributes.last_done_at).getTime();
    const cadenceValue = Number(attributes.recommended_every_value);
    const cadenceUnit = attributes.recommended_every_unit;
    const cadenceMs = { minutes: 60_000, hours: 3_600_000, days: 86_400_000, weeks: 604_800_000, months: 2_592_000_000 }[cadenceUnit];
    return Number.isFinite(lastDoneAt) && Number.isFinite(cadenceValue) && cadenceValue > 0 && cadenceMs
      ? lastDoneAt + cadenceValue * cadenceMs
      : null;
  }

  _compareNames(left, right) {
    const leftState = this._hass?.states?.[left.entity];
    const rightState = this._hass?.states?.[right.entity];
    return String(leftState?.attributes?.friendly_chore_name || left.entity).localeCompare(
      String(rightState?.attributes?.friendly_chore_name || right.entity),
    );
  }

  _effectiveTags(entry) {
    const tags = this._hass?.states?.[entry.entity]?.attributes?.tags;
    if (!Array.isArray(tags)) {
      return [];
    }
    return [...new Set(tags.map((tag) => String(tag).trim().toLowerCase()).filter(Boolean))];
  }

  _filters(entries) {
    const tags = new Set();
    let hasNoTag = false;
    for (const entry of entries) {
      const entryTags = this._effectiveTags(entry);
      if (entryTags.length === 0) {
        hasNoTag = true;
      }
      entryTags.forEach((tag) => tags.add(tag));
    }
    const filters = [...tags].sort((left, right) => left.localeCompare(right));
    if (hasNoTag) {
      filters.push(NO_TAG_FILTER);
    }
    return filters;
  }

  _reconcileFilters(filters) {
    const current = new Set(filters);
    if (!this._filtersInitialized && current.size > 0) {
      this._selectedFilters = new Set([ALL_FILTER]);
      this._filtersInitialized = true;
    } else if (current.size > 0 && !this._selectedFilters.has(ALL_FILTER)) {
      this._selectedFilters = new Set(
        [...this._selectedFilters].filter((key) => current.has(key)),
      );
    } else if (current.size === 0) {
      this._selectedFilters.clear();
      this._filtersInitialized = false;
    }
    this._previousFilterKeys = current;
  }

  _visibleEntries() {
    const source = this._sourceEntries();
    if (this._isSingleMode() || this._config.show_tag_filters === false) {
      return { entries: source, filters: [], source };
    }

    const filters = this._filters(source);
    this._reconcileFilters(filters);
    if (this._selectedFilters.has(ALL_FILTER)) {
      return { entries: source, filters, source };
    }
    if (this._selectedFilters.size === 0) {
      return { entries: [], filters, source, empty: "none_selected" };
    }

    const entries = source.filter((entry) => {
      const tags = this._effectiveTags(entry);
      if (tags.length === 0) {
        return this._selectedFilters.has(NO_TAG_FILTER);
      }
      return tags.some((tag) => this._selectedFilters.has(tag));
    });
    return { entries, filters, source, empty: entries.length ? undefined : "no_match" };
  }

  _allState(filters) {
    return filters.length && this._selectedFilters.has(ALL_FILTER) ? "true" : "false";
  }

  _toggleAll() {
    this._selectedFilters = new Set([ALL_FILTER]);
    this._focusFilterKey = "all";
    this._render();
  }

  _toggleFilter(key) {
    if (this._selectedFilters.has(ALL_FILTER)) {
      this._selectedFilters = new Set([key]);
    } else if (this._selectedFilters.has(key)) {
      this._selectedFilters.delete(key);
    } else {
      this._selectedFilters.add(key);
    }
    this._focusFilterKey = key;
    this._render();
  }

  async _markDone(entityId) {
    if (!this._hass || this._pendingEntityId) {
      return;
    }
    this._pendingEntityId = entityId;
    this._error = undefined;
    this._render();
    try {
      await this._hass.callService("time_since_that", "mark_done", {
        entity_id: entityId,
      });
      this._historyByEntity.delete(entityId);
      this._historyOpenEntityId = undefined;
    } catch (error) {
      this._error = error?.message || "Could not mark item done.";
    } finally {
      this._pendingEntityId = undefined;
      this._render();
    }
  }

  _toggleDateEntry(entityId) {
    if (this._pendingEntityId) {
      return;
    }
    if (this._dateEntryEntityId === entityId) {
      this._dateEntryEntityId = undefined;
      this._dateEntryValues.delete(entityId);
      this._requestDateFocus(entityId, "toggle");
    } else {
      this._dateEntryEntityId = entityId;
      this._requestDateFocus(entityId, "input");
    }
    this._error = undefined;
    this._render();
  }

  async _recordCompletion(entityId) {
    if (!this._hass || this._pendingEntityId) {
      return;
    }
    const value = this._dateEntryValues.get(entityId) || "";
    const completedAt = new Date(value);
    if (!value || Number.isNaN(completedAt.getTime())) {
      this._error = "Choose a valid completed date and time.";
      this._requestDateFocus(entityId, "input");
      this._render();
      return;
    }
    if (completedAt.getTime() > Date.now()) {
      this._error = "Completed date and time cannot be in the future.";
      this._requestDateFocus(entityId, "input");
      this._render();
      return;
    }

    this._pendingEntityId = entityId;
    this._error = undefined;
    this._render();
    try {
      await this._hass.callService("time_since_that", "record_completion", {
        entity_id: entityId,
        completed_at: completedAt.toISOString(),
      });
      this._dateEntryEntityId = undefined;
      this._dateEntryValues.delete(entityId);
      this._historyByEntity.delete(entityId);
      this._historyOpenEntityId = undefined;
    } catch (error) {
      this._error = error?.message || "Could not record completed date.";
    } finally {
      this._pendingEntityId = undefined;
      this._requestDateFocus(
        entityId,
        this._dateEntryEntityId === entityId ? "input" : "toggle",
      );
      this._render();
    }
  }

  _requestDateFocus(entityId, target) {
    this._focusDateEntityId = entityId;
    this._focusDateTarget = target;
  }

  _render() {
    if (!this.shadowRoot) {
      return;
    }
    const { entries, filters, source, empty } = this._visibleEntries();
    const style = document.createElement("style");
    style.textContent = CARD_STYLES;
    const card = document.createElement("ha-card");
    const wrap = this._element("div", "card-wrap");
    const header = this._element("header", "card-header");
    const titleWrap = document.createElement("div");
    titleWrap.append(
      this._element("h2", "", this._config.title || "Time Since That"),
      this._element(
        "p",
        "subtitle",
        source.length
          ? "Press a row button when something is done."
          : "No tracked Time Since That items found.",
      ),
    );
    header.append(titleWrap);
    wrap.append(header);

    if (!this._isSingleMode() && this._config.show_tag_filters !== false && filters.length) {
      wrap.append(this._renderFilters(filters));
    }
    if (!this._isSingleMode()) {
      wrap.append(this._renderSort());
    }

    const items = this._element("div", "items");
    for (const entry of entries) {
      items.append(this._renderRow(entry));
    }
    wrap.append(items);

    if (source.length && entries.length === 0) {
      wrap.append(
        this._element(
          "p",
          "empty-state",
          empty === "none_selected"
            ? "No tags selected. Choose a tag or select All."
            : "No chores match the selected tags.",
        ),
      );
    }
    if (this._error) {
      const error = this._element("p", "card-error", this._error);
      error.setAttribute("role", "alert");
      wrap.append(error);
    }

    card.append(wrap);
    this.shadowRoot.replaceChildren(style, card);
    if (this._focusFilterKey) {
      const key = this._focusFilterKey;
      this._focusFilterKey = undefined;
      queueMicrotask(() => this.shadowRoot.querySelector(`[data-filter-key="${key}"]`)?.focus());
    }
    if (this._focusDateEntityId && this._focusDateTarget) {
      const entityId = this._focusDateEntityId;
      const target = this._focusDateTarget;
      this._focusDateEntityId = undefined;
      this._focusDateTarget = undefined;
      queueMicrotask(() => {
        const control = target === "input"
          ? this.shadowRoot.querySelector(`#${this._dateInputId(entityId)}`)
          : [...this.shadowRoot.querySelectorAll(".date-toggle-button")]
            .find((button) => button.dataset.entityId === entityId);
        control?.focus();
      });
    }
    if (this._focusHistoryEventId && this._focusHistoryTarget) {
      const eventId = this._focusHistoryEventId;
      const target = this._focusHistoryTarget;
      this._focusHistoryEventId = undefined;
      this._focusHistoryTarget = undefined;
      queueMicrotask(() => {
        const control = target === "input"
          ? this.shadowRoot.querySelector(`#${this._historyInputId(eventId)}`)
          : [...this.shadowRoot.querySelectorAll(".completion-history__date")]
            .find((button) => button.dataset.eventId === eventId);
        control?.focus();
      });
    }
  }

  _renderFilters(filters) {
    const group = this._element("div", "filters");
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", "Filter chores by tag");
    const all = this._filterButton("all", "All", this._allState(filters));
    all.addEventListener("click", () => this._toggleAll());
    group.append(all);
    for (const filter of filters) {
      const label = filter === NO_TAG_FILTER ? "No tag" : filter;
      const button = this._filterButton(
        filter,
        label,
        this._selectedFilters.has(filter) ? "true" : "false",
      );
      button.addEventListener("click", () => this._toggleFilter(filter));
      group.append(button);
    }
    return group;
  }

  _renderSort() {
    const label = this._element("label", "sort-control", "Sort chores");
    const select = document.createElement("select");
    select.setAttribute("aria-label", "Sort chores");
    for (const [value, text] of SORT_OPTIONS) {
      select.append(new Option(text, value));
    }
    select.value = this._sort;
    select.addEventListener("change", () => {
      this._sort = select.value;
      this._render();
    });
    label.append(select);
    return label;
  }

  _filterButton(key, label, state) {
    const button = this._element("button", "filter-button", label);
    button.type = "button";
    button.dataset.filterKey = key;
    button.setAttribute("aria-pressed", state);
    if (state === "true") {
      button.classList.add("filter-button--selected");
    }
    if (state === "mixed") {
      button.classList.add("filter-button--mixed");
    }
    return button;
  }

  _lastDoneText(lastDoneAt) {
    if (!lastDoneAt) {
      return "Last done: never";
    }

    const doneAt = new Date(lastDoneAt);
    if (Number.isNaN(doneAt.getTime())) {
      return "Last done: unknown";
    }

    const elapsedMs = Math.max(0, Date.now() - doneAt.getTime());
    const minute = 60 * 1000;
    const hour = 60 * minute;
    const day = 24 * hour;
    let relative;
    if (elapsedMs < minute) {
      relative = "just now";
    } else if (elapsedMs < hour) {
      relative = this._relativeDuration(elapsedMs, minute, "minute");
    } else if (elapsedMs < day) {
      relative = this._relativeDuration(elapsedMs, hour, "hour");
    } else if (elapsedMs < 7 * day) {
      relative = this._relativeDuration(elapsedMs, day, "day");
    } else if (elapsedMs < 30 * day) {
      relative = this._relativeDuration(elapsedMs, 7 * day, "week");
    } else {
      relative = this._relativeDuration(elapsedMs, 30 * day, "month");
    }

    const exact = elapsedMs < day
      ? `${this._twoDigits(doneAt.getHours())}:${this._twoDigits(doneAt.getMinutes())}`
      : `${this._twoDigits(doneAt.getDate())}/${this._twoDigits(doneAt.getMonth() + 1)}`;
    return `Last done: ${relative} · ${exact}`;
  }

  _relativeDuration(elapsedMs, unitMs, unit) {
    const value = Math.max(1, Math.floor(elapsedMs / unitMs));
    return `${value} ${unit}${value === 1 ? "" : "s"} ago`;
  }

  _twoDigits(value) {
    return String(value).padStart(2, "0");
  }

  _dateInputId(entityId) {
    return `completed-at-${String(entityId).replace(/[^a-z0-9_-]/gi, "-")}`;
  }

  _historyInputId(eventId) {
    return `completion-history-${String(eventId).replace(/[^a-z0-9_-]/gi, "-")}`;
  }

  _connection() {
    return this._hass?.connection?.sendMessagePromise?.bind(this._hass.connection);
  }

  async _toggleHistory(entityId) {
    if (this._historyOpenEntityId === entityId) {
      this._historyOpenEntityId = undefined;
      this._historyEditEventId = undefined;
      this._render();
      return;
    }
    this._historyOpenEntityId = entityId;
    this._historyEditEventId = undefined;
    this._error = undefined;
    if (this._historyByEntity.has(entityId)) {
      this._render();
      return;
    }
    const sendMessage = this._connection();
    if (!sendMessage) {
      this._error = "Completion history requires a Home Assistant WebSocket connection.";
      this._render();
      return;
    }
    this._historyLoadingEntityId = entityId;
    this._render();
    try {
      const result = await sendMessage({ type: "time_since_that/completion_history", entity_id: entityId });
      this._historyByEntity.set(entityId, Array.isArray(result?.events) ? result.events : []);
    } catch (error) {
      this._error = error?.message || "Could not load completion history.";
    } finally {
      this._historyLoadingEntityId = undefined;
      this._render();
    }
  }

  _toggleHistoryEdit(event) {
    if (this._pendingEntityId) {
      return;
    }
    this._focusHistoryEventId = event.event_id;
    if (this._historyEditEventId === event.event_id) {
      this._historyEditEventId = undefined;
      this._historyEditValues.delete(event.event_id);
      this._focusHistoryTarget = "date";
    } else {
      this._historyEditEventId = event.event_id;
      this._historyEditValues.set(event.event_id, this._localDateTimeValue(new Date(event.completed_at)));
      this._focusHistoryTarget = "input";
    }
    this._error = undefined;
    this._render();
  }

  async _updateCompletion(entityId, eventId) {
    const value = this._historyEditValues.get(eventId) || "";
    const completedAt = new Date(value);
    if (!value || Number.isNaN(completedAt.getTime()) || completedAt.getTime() > Date.now()) {
      this._error = "Choose a valid completed date and time that is not in the future.";
      this._render();
      return;
    }
    const sendMessage = this._connection();
    if (!sendMessage) {
      this._error = "Completion history requires a Home Assistant WebSocket connection.";
      this._render();
      return;
    }
    this._pendingEntityId = entityId;
    this._error = undefined;
    this._render();
    try {
      const result = await sendMessage({
        type: "time_since_that/update_completion",
        entity_id: entityId,
        event_id: eventId,
        completed_at: completedAt.toISOString(),
      });
      const events = this._historyByEntity.get(entityId) || [];
      this._historyByEntity.set(entityId, events
        .map((event) => event.event_id === eventId ? result : event)
        .sort((left, right) => new Date(right.completed_at) - new Date(left.completed_at)));
      this._historyEditEventId = undefined;
      this._historyEditValues.delete(eventId);
      this._focusHistoryEventId = eventId;
      this._focusHistoryTarget = "date";
    } catch (error) {
      this._error = error?.message || "Could not update completed date.";
    } finally {
      this._pendingEntityId = undefined;
      this._render();
    }
  }

  async _deleteCompletion(entityId, eventId, dateText, name) {
    if (this._pendingEntityId) {
      return;
    }
    if (!window.confirm(`Delete ${dateText} for ${name}? This permanently removes the completion and recalculates statistics.`)) {
      return;
    }
    const sendMessage = this._connection();
    if (!sendMessage) {
      this._error = "Completion history requires a Home Assistant WebSocket connection.";
      this._render();
      return;
    }
    this._pendingEntityId = entityId;
    this._error = undefined;
    this._render();
    try {
      await sendMessage({
        type: "time_since_that/delete_completion",
        entity_id: entityId,
        event_id: eventId,
      });
      const events = this._historyByEntity.get(entityId) || [];
      this._historyByEntity.set(entityId, events.filter((event) => event.event_id !== eventId));
      this._historyEditEventId = undefined;
      this._historyEditValues.delete(eventId);
    } catch (error) {
      this._historyByEntity.delete(entityId);
      this._historyOpenEntityId = undefined;
      this._error = error?.message || "Could not delete completed date.";
    } finally {
      this._pendingEntityId = undefined;
      this._render();
    }
  }

  _renderHistory(entityId, name) {
    const history = this._element("section", "completion-history");
    history.setAttribute("aria-label", `Completed dates for ${name}`);
    if (this._historyLoadingEntityId === entityId) {
      history.append(this._element("p", "subtitle", "Loading completed dates…"));
      return history;
    }
    const events = this._historyByEntity.get(entityId) || [];
    if (!events.length) {
      history.append(this._element("p", "subtitle", "No completed dates yet."));
      return history;
    }
    const list = this._element("ol", "completion-history__list");
    for (const event of events) {
      const item = this._element("li", "completion-history__item");
      const date = new Date(event.completed_at);
      const dateButton = this._element(
        "button",
        "completion-history__date",
        Number.isNaN(date.getTime()) ? "Unknown date" : date.toLocaleString(),
      );
      dateButton.type = "button";
      dateButton.dataset.eventId = event.event_id;
      dateButton.disabled = Boolean(this._pendingEntityId);
      dateButton.setAttribute("aria-expanded", String(this._historyEditEventId === event.event_id));
      dateButton.setAttribute("aria-label", `Edit completed date ${dateButton.textContent} for ${name}`);
      dateButton.addEventListener("click", () => this._toggleHistoryEdit(event));
      const deleteButton = this._element("button", "history-delete-button", "×");
      deleteButton.type = "button";
      deleteButton.disabled = Boolean(this._pendingEntityId);
      deleteButton.setAttribute("aria-label", `Delete completed date ${dateButton.textContent} for ${name}`);
      deleteButton.addEventListener("click", () => this._deleteCompletion(
        entityId,
        event.event_id,
        dateButton.textContent,
        name,
      ));
      item.append(dateButton, deleteButton);
      if (this._historyEditEventId === event.event_id) {
        const form = this._element("form", "history-edit-form");
        const input = this._element("input", "date-entry__input");
        input.id = this._historyInputId(event.event_id);
        input.type = "datetime-local";
        input.step = "1";
        input.required = true;
        input.max = this._localDateTimeValue(new Date());
        input.value = this._historyEditValues.get(event.event_id) || "";
        input.setAttribute("aria-label", `Completed date and time for ${name}`);
        input.addEventListener("input", () => this._historyEditValues.set(event.event_id, input.value));
        const save = this._element("button", "history-save-button", this._pendingEntityId ? "Saving" : "Save");
        save.type = "submit";
        save.disabled = Boolean(this._pendingEntityId);
        const cancel = this._element("button", "history-cancel-button", "Cancel");
        cancel.type = "button";
        cancel.disabled = Boolean(this._pendingEntityId);
        cancel.addEventListener("click", () => this._toggleHistoryEdit(event));
        form.append(input, save, cancel);
        form.addEventListener("submit", (eventSubmit) => {
          eventSubmit.preventDefault();
          this._updateCompletion(entityId, event.event_id);
        });
        item.append(form);
      }
      list.append(item);
    }
    history.append(list);
    return history;
  }

  _dateEntry(entityId, name) {
    const form = this._element("form", "date-entry");
    const inputId = this._dateInputId(entityId);
    const label = this._element("label", "date-entry__label", "Completed date and time");
    label.htmlFor = inputId;
    const input = this._element("input", "date-entry__input");
    input.id = inputId;
    input.name = "completed_at";
    input.type = "datetime-local";
    input.required = true;
    input.disabled = Boolean(this._pendingEntityId);
    input.max = this._localDateTimeValue(new Date());
    input.value = this._dateEntryValues.get(entityId) || "";
    input.setAttribute("aria-label", `Completed date and time for ${name}`);
    input.addEventListener("input", () => this._dateEntryValues.set(entityId, input.value));

    const buttons = this._element("div", "date-entry__buttons");
    const save = this._element(
      "button",
      "date-save-button",
      this._pendingEntityId === entityId ? "Saving" : "Save completion",
    );
    save.type = "submit";
    save.disabled = Boolean(this._pendingEntityId);
    const cancel = this._element("button", "date-cancel-button", "Cancel");
    cancel.type = "button";
    cancel.disabled = Boolean(this._pendingEntityId);
    cancel.addEventListener("click", () => this._toggleDateEntry(entityId));
    buttons.append(save, cancel);
    form.append(label, input, buttons);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      this._recordCompletion(entityId);
    });
    return form;
  }

  _localDateTimeValue(date) {
    return `${date.getFullYear()}-${this._twoDigits(date.getMonth() + 1)}-${this._twoDigits(date.getDate())}T${this._twoDigits(date.getHours())}:${this._twoDigits(date.getMinutes())}:${this._twoDigits(date.getSeconds())}`;
  }

  _renderRow(entry) {
    const stateObj = this._hass?.states?.[entry.entity];
    const row = this._element("article", "item");
    if (!stateObj) {
      row.classList.add("missing");
      row.append(
        this._element("p", "item__name", entry.name || entry.entity || "Missing entity"),
        this._element("p", "subtitle", "Entity not found."),
      );
      return row;
    }

    const attributes = stateObj.attributes || {};
    const name = entry.name || attributes.friendly_chore_name || attributes.friendly_name || entry.entity;
    const text = document.createElement("div");
    text.append(
      this._element("p", "item__name", name),
      this._element("p", "item__state", this._lastDoneText(attributes.last_done_at)),
      this._metaPills(attributes, entry.entity, name),
    );
    const actions = this._element("div", "item__actions");
    const button = this._element(
      "button",
      "mark-button",
      this._pendingEntityId === entry.entity ? "Saving" : "Mark done",
    );
    button.type = "button";
    button.disabled = Boolean(this._pendingEntityId);
    button.addEventListener("click", () => this._markDone(entry.entity));
    const dateButton = this._element("button", "date-toggle-button", "Enter completed date");
    dateButton.type = "button";
    dateButton.disabled = Boolean(this._pendingEntityId);
    dateButton.dataset.entityId = entry.entity;
    dateButton.setAttribute("aria-expanded", String(this._dateEntryEntityId === entry.entity));
    dateButton.setAttribute("aria-label", `Enter completed date for ${name}`);
    dateButton.addEventListener("click", () => this._toggleDateEntry(entry.entity));
    actions.append(button, dateButton);
    if (this._dateEntryEntityId === entry.entity) {
      actions.append(this._dateEntry(entry.entity, name));
    }
    if (this._historyOpenEntityId === entry.entity) {
      actions.append(this._renderHistory(entry.entity, name));
    }
    row.append(text, actions);
    return row;
  }

  _metaPills(attributes, entityId, name) {
    const meta = this._element("div", "meta");
    if (attributes.recommended_every) {
      meta.append(this._pill(
        attributes.recommended_every,
        "",
        `Recommended cadence: ${attributes.recommended_every}`,
      ));
    }
    if (attributes.over_recommended === true && attributes.over_by) {
      meta.append(this._pill(`Overdue ${attributes.over_by}`, "pill--overdue"));
    }
    if (attributes.completion_count >= 2 && attributes.average_interval) {
      meta.append(this._pill(
        `Avg ${attributes.average_interval}`,
        "",
        `Average time between completions: ${attributes.average_interval}`,
      ));
    }
    if (attributes.completion_count !== undefined) {
      const completionLabel = attributes.completion_count === 1 ? "completion" : "completions";
      const completionButton = this._element(
        "button",
        "pill completion-history-toggle-pill",
        `${attributes.completion_count} ${completionLabel}`,
      );
      completionButton.type = "button";
      completionButton.disabled = Boolean(this._pendingEntityId);
      completionButton.setAttribute("aria-expanded", String(this._historyOpenEntityId === entityId));
      completionButton.setAttribute("aria-label", `View completed dates for ${name}`);
      completionButton.addEventListener("click", () => this._toggleHistory(entityId));
      meta.append(completionButton);
    }
    const tags = Array.isArray(attributes.tags) ? attributes.tags : [];
    for (const tag of tags) {
      meta.append(this._pill(tag, "pill--tag"));
    }
    return meta;
  }

  _pill(text, extraClass = "", accessibleLabel = "") {
    const pill = this._element("span", "pill", text);
    if (extraClass) {
      pill.classList.add(extraClass);
    }
    if (accessibleLabel) {
      pill.title = accessibleLabel;
      pill.setAttribute("aria-label", accessibleLabel);
    }
    return pill;
  }

  _element(tagName, className = "", text = undefined) {
    const element = document.createElement(tagName);
    if (className) {
      element.className = className;
    }
    if (text !== undefined) {
      element.textContent = text;
    }
    return element;
  }
}

class TimeSinceThatCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = undefined;
  }

  setConfig(config) {
    this._config = { title: "Time Since That", show_tag_filters: true, ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _mode() {
    return this._config.entity ? "single" : "all";
  }

  _choreOptions() {
    return Object.entries(this._hass?.states || {})
      .filter(([entityId, state]) => entityId.startsWith("sensor.time_since_that_") && state.attributes?.chore_id)
      .map(([entity, state]) => ({
        entity,
        name: state.attributes.friendly_chore_name || state.attributes.friendly_name || entity,
      }))
      .sort((left, right) => left.name.localeCompare(right.name));
  }

  _emit(changes) {
    const config = { ...this._config, ...changes };
    if (config.entity === undefined || config.entity === "") {
      delete config.entity;
    }
    this._config = config;
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config }, bubbles: true, composed: true,
    }));
    this._render();
  }

  _render() {
    if (!this.shadowRoot) {
      return;
    }
    const style = document.createElement("style");
    style.textContent = EDITOR_STYLES;
    const form = document.createElement("div");
    form.className = "editor";

    const title = document.createElement("input");
    title.value = this._config.title || "";
    title.placeholder = "Card title";
    title.addEventListener("change", () => this._emit({ title: title.value }));
    form.append(this._label("Title", title));

    const mode = document.createElement("select");
    mode.append(new Option("All chores", "all"), new Option("One chore", "single"));
    mode.value = this._mode();
    mode.addEventListener("change", () => this._emit({ entity: mode.value === "single" ? this._choreOptions()[0]?.entity : undefined }));
    form.append(this._label("Show", mode));

    if (this._mode() === "single") {
      const entity = document.createElement("select");
      for (const option of this._choreOptions()) {
        entity.append(new Option(option.name, option.entity));
      }
      entity.value = this._config.entity || "";
      entity.addEventListener("change", () => this._emit({ entity: entity.value }));
      form.append(this._label("Chore", entity));
    } else {
      const toggle = document.createElement("input");
      toggle.type = "checkbox";
      toggle.checked = this._config.show_tag_filters !== false;
      toggle.addEventListener("change", () => this._emit({ show_tag_filters: toggle.checked }));
      form.append(this._label("Show tag filters", toggle));
    }

    this.shadowRoot.replaceChildren(style, form);
  }

  _label(text, control) {
    const label = document.createElement("label");
    label.textContent = text;
    label.append(control);
    return label;
  }
}

const CARD_STYLES = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  .card-wrap { padding: 20px; }
  .card-header { margin-bottom: 16px; }
  h2 { margin: 0; color: var(--primary-text-color); font-size: 1.25rem; font-weight: 650; }
  .subtitle { margin: 5px 0 0; color: var(--secondary-text-color); font-size: 0.9rem; }
  .filters { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 16px; }
  .sort-control { display: grid; gap: 4px; margin: 0 0 16px; color: var(--secondary-text-color); font-size: 0.8rem; }
  .sort-control select { min-height: 38px; border: 1px solid var(--divider-color); border-radius: 8px; background: var(--card-background-color); color: var(--primary-text-color); font: inherit; }
  .filter-button, .mark-button, .date-toggle-button, .date-save-button, .date-cancel-button, .completion-history-toggle-pill, .completion-history__date, .history-delete-button, .history-save-button, .history-cancel-button { border: 0; cursor: pointer; font: inherit; }
  .filter-button { border: 1px solid var(--divider-color); border-radius: 999px; background: var(--card-background-color); color: var(--primary-text-color); padding: 7px 11px; }
  .filter-button--selected { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color); }
  .filter-button--mixed { border-color: var(--primary-color); color: var(--primary-color); }
  .filter-button:focus-visible, .sort-control select:focus-visible, .mark-button:focus-visible, .date-toggle-button:focus-visible, .completion-history-toggle-pill:focus-visible, .completion-history__date:focus-visible, .history-delete-button:focus-visible, .date-save-button:focus-visible, .date-cancel-button:focus-visible, .history-save-button:focus-visible, .history-cancel-button:focus-visible, .date-entry__input:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .items { display: grid; gap: 12px; }
  .item { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 14px; align-items: center; padding: 14px; border: 1px solid var(--divider-color); border-radius: 16px; background: var(--card-background-color); }
  .item__name { margin: 0; color: var(--primary-text-color); font-size: 1rem; font-weight: 650; }
  .item__state { margin: 4px 0 0; color: var(--primary-text-color); font-size: clamp(1rem, 4vw, 1.25rem); font-weight: 760; }
  .meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  .pill { display: inline-flex; min-height: 24px; padding: 3px 9px; border-radius: 999px; background: var(--secondary-background-color); color: var(--secondary-text-color); font-size: 0.78rem; }
  .completion-history-toggle-pill { align-items: center; }
  .pill--overdue { color: var(--error-color, #db4437); }
  .pill--tag { color: var(--primary-color); }
  .item__actions { display: grid; gap: 8px; min-width: 190px; }
  .mark-button, .date-toggle-button, .date-save-button, .date-cancel-button { min-height: 42px; border-radius: 999px; font-size: 0.9rem; font-weight: 650; padding: 0 16px; }
  .mark-button, .date-save-button, .history-save-button { background: var(--primary-color); color: var(--text-primary-color); }
  .date-toggle-button, .date-cancel-button, .completion-history__date, .history-cancel-button { border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
  .completion-history { display: grid; gap: 8px; padding-top: 4px; }
  .completion-history__list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
  .completion-history__item { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; }
  .completion-history__date { min-height: 34px; border-radius: 8px; padding: 0 10px; text-align: left; color: var(--secondary-text-color); font-size: 0.85rem; }
  .history-delete-button { min-width: 34px; min-height: 34px; border-radius: 999px; background: transparent; color: var(--error-color, #db4437); font-size: 1.2rem; }
  .history-save-button, .history-cancel-button { min-height: 34px; border-radius: 999px; padding: 0 12px; }
  .history-edit-form { grid-column: 1 / -1; display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 8px; }
  .date-entry { display: grid; gap: 8px; margin-top: 4px; }
  .date-entry__label { color: var(--secondary-text-color); font-size: 0.8rem; }
  .date-entry__input { box-sizing: border-box; width: 100%; min-height: 42px; padding: 8px; border: 1px solid var(--divider-color); border-radius: 8px; background: var(--card-background-color); color: var(--primary-text-color); font: inherit; }
  .date-entry__buttons { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .mark-button[disabled], .date-toggle-button[disabled], .completion-history-toggle-pill[disabled], .completion-history__date[disabled], .history-delete-button[disabled], .date-save-button[disabled], .date-cancel-button[disabled], .history-save-button[disabled], .history-cancel-button[disabled] { cursor: wait; opacity: 0.65; }
  .empty-state, .card-error { margin: 14px 0 0; color: var(--secondary-text-color); }
  .card-error, .missing { color: var(--error-color, #db4437); }
  @media (max-width: 520px) { .item { grid-template-columns: 1fr; } .item__actions { width: 100%; } }
`;

const EDITOR_STYLES = `
  .editor { display: grid; gap: 16px; padding: 8px; }
  label { display: grid; gap: 8px; color: var(--primary-text-color); }
  input, select { box-sizing: border-box; width: 100%; padding: 10px; border: 1px solid var(--divider-color); border-radius: 8px; background: var(--card-background-color); color: var(--primary-text-color); }
  input[type="checkbox"] { width: auto; }
`;

if (!customElements.get("time-since-that-card")) {
  customElements.define("time-since-that-card", TimeSinceThatCard);
}
if (!customElements.get("time-since-that-card-editor")) {
  customElements.define("time-since-that-card-editor", TimeSinceThatCardEditor);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "time-since-that-card",
  name: "Time Since That Card",
  description: "Show Time Since That chores with inline mark-done actions and tag filters.",
});
