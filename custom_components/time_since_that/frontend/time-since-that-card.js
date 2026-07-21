const NO_TAG_FILTER = "__time_since_that_no_tag__";

class TimeSinceThatCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = undefined;
    this._pendingEntityId = undefined;
    this._error = undefined;
    this._selectedFilters = new Set();
    this._previousFilterKeys = new Set();
    this._filtersInitialized = false;
    this._focusFilterKey = undefined;
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
      return [{ entity: this._config.entity }];
    }
    if (this._config.entities) {
      return this._config.entities;
    }

    return Object.entries(this._hass?.states || {})
      .filter(
        ([entityId, stateObj]) =>
          entityId.startsWith("sensor.time_since_that_") &&
          Boolean(stateObj.attributes?.chore_id),
      )
      .map(([entity]) => ({ entity }))
      .sort((left, right) => this._compareEntries(left, right));
  }

  _compareEntries(left, right) {
    const leftState = this._hass.states[left.entity];
    const rightState = this._hass.states[right.entity];
    const overdueDelta =
      Number(rightState.attributes.over_recommended === true) -
      Number(leftState.attributes.over_recommended === true);
    if (overdueDelta) {
      return overdueDelta;
    }
    const elapsedDelta =
      Number(rightState.attributes.elapsed_value || 0) -
      Number(leftState.attributes.elapsed_value || 0);
    if (elapsedDelta) {
      return elapsedDelta;
    }
    return String(leftState.attributes.friendly_chore_name || left.entity).localeCompare(
      String(rightState.attributes.friendly_chore_name || right.entity),
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
    const wasComplete =
      this._previousFilterKeys.size > 0 &&
      [...this._previousFilterKeys].every((key) => this._selectedFilters.has(key));

    if (!this._filtersInitialized && current.size > 0) {
      this._selectedFilters = new Set(current);
      this._filtersInitialized = true;
    } else if (current.size > 0) {
      this._selectedFilters = new Set(
        [...this._selectedFilters].filter((key) => current.has(key)),
      );
      if (wasComplete) {
        this._selectedFilters = new Set(current);
      }
    } else {
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
    if (!filters.length || this._selectedFilters.size === 0) {
      return "false";
    }
    return filters.every((key) => this._selectedFilters.has(key)) ? "true" : "mixed";
  }

  _toggleAll(filters) {
    if (this._allState(filters) === "true") {
      this._selectedFilters.clear();
    } else {
      this._selectedFilters = new Set(filters);
    }
    this._focusFilterKey = "all";
    this._render();
  }

  _toggleFilter(key) {
    if (this._selectedFilters.has(key)) {
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
    } catch (error) {
      this._error = error?.message || "Could not mark item done.";
    } finally {
      this._pendingEntityId = undefined;
      this._render();
    }
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
  }

  _renderFilters(filters) {
    const group = this._element("div", "filters");
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", "Filter chores by tag");
    const all = this._filterButton("all", "All", this._allState(filters));
    all.addEventListener("click", () => this._toggleAll(filters));
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
      this._element("p", "item__state", stateObj.state || "unknown"),
      this._metaPills(attributes),
    );
    const button = this._element(
      "button",
      "mark-button",
      this._pendingEntityId === entry.entity ? "Saving" : "Mark done",
    );
    button.type = "button";
    button.disabled = this._pendingEntityId === entry.entity;
    button.addEventListener("click", () => this._markDone(entry.entity));
    row.append(text, button);
    return row;
  }

  _metaPills(attributes) {
    const meta = this._element("div", "meta");
    if (attributes.recommended_every) {
      meta.append(this._pill(`Recommended ${attributes.recommended_every}`));
    }
    if (attributes.over_recommended === true && attributes.over_by) {
      meta.append(this._pill(`Overdue ${attributes.over_by}`, "pill--overdue"));
    }
    if (attributes.completion_count !== undefined) {
      meta.append(this._pill(`${attributes.completion_count} completions`));
    }
    const tags = Array.isArray(attributes.tags) ? attributes.tags : [];
    for (const tag of tags) {
      meta.append(this._pill(tag, "pill--tag"));
    }
    return meta;
  }

  _pill(text, extraClass = "") {
    const pill = this._element("span", "pill", text);
    if (extraClass) {
      pill.classList.add(extraClass);
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
  .filter-button, .mark-button { border: 0; cursor: pointer; font: inherit; }
  .filter-button { border: 1px solid var(--divider-color); border-radius: 999px; background: var(--card-background-color); color: var(--primary-text-color); padding: 7px 11px; }
  .filter-button--selected { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color); }
  .filter-button--mixed { border-color: var(--primary-color); color: var(--primary-color); }
  .filter-button:focus-visible, .mark-button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .items { display: grid; gap: 12px; }
  .item { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 14px; align-items: center; padding: 14px; border: 1px solid var(--divider-color); border-radius: 16px; background: var(--card-background-color); }
  .item__name { margin: 0; color: var(--primary-text-color); font-size: 1rem; font-weight: 650; }
  .item__state { margin: 4px 0 0; color: var(--primary-text-color); font-size: 1.45rem; font-weight: 760; }
  .meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  .pill { display: inline-flex; min-height: 24px; padding: 3px 9px; border-radius: 999px; background: var(--secondary-background-color); color: var(--secondary-text-color); font-size: 0.78rem; }
  .pill--overdue { color: var(--error-color, #db4437); }
  .pill--tag { color: var(--primary-color); }
  .mark-button { min-width: 106px; min-height: 42px; border-radius: 999px; background: var(--primary-color); color: var(--text-primary-color); font-size: 0.9rem; font-weight: 650; padding: 0 16px; }
  .mark-button[disabled] { cursor: wait; opacity: 0.65; }
  .empty-state, .card-error { margin: 14px 0 0; color: var(--secondary-text-color); }
  .card-error, .missing { color: var(--error-color, #db4437); }
  @media (max-width: 520px) { .item { grid-template-columns: 1fr; } .mark-button { width: 100%; } }
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
