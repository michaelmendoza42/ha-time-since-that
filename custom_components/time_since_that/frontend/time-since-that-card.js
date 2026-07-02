class TimeSinceThatCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = { entities: [] };
    this._hass = undefined;
    this._pendingEntityId = undefined;
    this._error = undefined;
  }

  setConfig(config) {
    if (!config || !Array.isArray(config.entities) || config.entities.length === 0) {
      throw new Error("Time Since That card requires a non-empty entities array.");
    }

    this._config = {
      title: "Time Since That",
      ...config,
      entities: config.entities.map((entry) =>
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
    return Math.max(3, this._config.entities.length * 2);
  }

  static getStubConfig() {
    return {
      title: "Time Since That",
      entities: ["sensor.time_since_that_scoop_cat_litter"],
    };
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
    if (!this.shadowRoot || !this._config) {
      return;
    }

    const style = document.createElement("style");
    style.textContent = CARD_STYLES;

    const card = document.createElement("ha-card");
    const wrap = this._element("div", "card-wrap");
    const header = this._element("header", "card-header");
    const headerText = document.createElement("div");
    const title = this._element("h2", "", this._config.title || "Time Since That");
    const subtitle = this._element(
      "p",
      "subtitle",
      this._config.entities.length
        ? "Press a row button when something is done."
        : "No entities configured.",
    );

    headerText.append(title, subtitle);
    header.append(headerText);

    const items = this._element("div", "items");
    for (const entry of this._config.entities) {
      items.append(this._renderRow(entry));
    }

    wrap.append(header, items);

    if (this._error) {
      const error = this._element("p", "card-error", this._error);
      error.setAttribute("role", "alert");
      wrap.append(error);
    }

    card.append(wrap);
    this.shadowRoot.replaceChildren(style, card);
  }

  _renderRow(entry) {
    const entityId = entry.entity;
    const stateObj = this._hass?.states?.[entityId];
    const row = this._element("article", "item");

    if (!stateObj) {
      row.classList.add("missing");
      const text = document.createElement("div");
      text.append(
        this._element("p", "item__name", entry.name || entityId || "Missing entity"),
        this._element("p", "subtitle", "Entity not found."),
      );
      row.append(text);
      return row;
    }

    const attributes = stateObj.attributes || {};
    const name = entry.name || attributes.friendly_chore_name || attributes.friendly_name || entityId;
    const state = stateObj.state || "unknown";
    const text = document.createElement("div");
    text.append(
      this._element("p", "item__name", name),
      this._element("p", "item__state", state),
      this._metaPills(attributes),
    );

    const button = this._element(
      "button",
      "mark-button",
      this._pendingEntityId === entityId ? "Saving" : "Mark done",
    );
    button.type = "button";
    button.disabled = this._pendingEntityId === entityId;
    button.addEventListener("click", () => this._markDone(entityId));

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

    if (attributes.last_done_by_name) {
      meta.append(this._pill(`Last by ${attributes.last_done_by_name}`));
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

const CARD_STYLES = `
  :host {
    display: block;
  }

  ha-card {
    overflow: hidden;
  }

  .card-wrap {
    padding: 20px;
  }

  .card-header {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
  }

  h2 {
    margin: 0;
    color: var(--primary-text-color);
    font-size: 1.25rem;
    font-weight: 650;
    letter-spacing: -0.02em;
  }

  .subtitle {
    margin: 5px 0 0;
    color: var(--secondary-text-color);
    font-size: 0.9rem;
  }

  .items {
    display: grid;
    gap: 12px;
  }

  .item {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 14px;
    align-items: center;
    padding: 14px;
    border: 1px solid var(--divider-color);
    border-radius: 16px;
    background: var(--card-background-color);
  }

  .item__name {
    margin: 0;
    color: var(--primary-text-color);
    font-size: 1rem;
    font-weight: 650;
    line-height: 1.25;
  }

  .item__state {
    margin: 4px 0 0;
    color: var(--primary-text-color);
    font-size: 1.45rem;
    font-weight: 760;
    letter-spacing: -0.04em;
    line-height: 1.05;
  }

  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 10px;
  }

  .pill {
    display: inline-flex;
    align-items: center;
    min-height: 24px;
    padding: 3px 9px;
    border-radius: 999px;
    background: var(--secondary-background-color);
    color: var(--secondary-text-color);
    font-size: 0.78rem;
    line-height: 1.2;
  }

  .pill--overdue {
    color: var(--error-color, #db4437);
  }

  .mark-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 106px;
    min-height: 42px;
    border: 0;
    border-radius: 999px;
    background: var(--primary-color);
    color: var(--text-primary-color);
    cursor: pointer;
    font: inherit;
    font-size: 0.9rem;
    font-weight: 650;
    padding: 0 16px;
    transition: transform 120ms ease, opacity 120ms ease;
  }

  .mark-button:active {
    transform: translateY(1px) scale(0.99);
  }

  .mark-button[disabled] {
    cursor: wait;
    opacity: 0.65;
  }

  .missing {
    color: var(--error-color, #db4437);
  }

  .card-error {
    margin: 12px 0 0;
    color: var(--error-color, #db4437);
  }

  @media (max-width: 520px) {
    .item {
      grid-template-columns: 1fr;
    }

    .mark-button {
      width: 100%;
    }
  }
`;

if (!customElements.get("time-since-that-card")) {
  customElements.define("time-since-that-card", TimeSinceThatCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "time-since-that-card",
  name: "Time Since That Card",
  description: "Show Time Since That sensors with inline mark-done buttons.",
});
