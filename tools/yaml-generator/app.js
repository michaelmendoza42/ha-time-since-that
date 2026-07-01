const itemsEl = document.querySelector("#items");
const template = document.querySelector("#item-template");
const outputEl = document.querySelector("#yaml-output");
const statusEl = document.querySelector("#status");
const form = document.querySelector("#chore-form");
const addButton = document.querySelector("#add-item");
const copyButton = document.querySelector("#copy-yaml");
const downloadButton = document.querySelector("#download-yaml");
const sampleButton = document.querySelector("#load-sample");

const sampleItems = [
  {
    name: "Scoop cat litter",
    id: "scoop_cat_litter",
    category: "pets",
    area: "Bathroom",
    recommendedValue: "2",
    recommendedUnit: "days",
    displayUnit: "days",
    rounding: "floor",
  },
  {
    name: "Refill humidifier",
    id: "refill_humidifier",
    category: "home",
    area: "Bedroom",
    recommendedValue: "12",
    recommendedUnit: "hours",
    displayUnit: "hours",
    rounding: "floor",
  },
];

function slugify(value) {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_+/g, "_");
  return /^[a-z]/.test(slug) ? slug : slug ? `item_${slug}` : "";
}

function quoteYaml(value) {
  const text = String(value).trim();
  if (/^[a-zA-Z0-9_ -]+$/.test(text) && text !== "") {
    return text;
  }
  return JSON.stringify(text);
}

function numberForYaml(value) {
  const numeric = Number(value);
  return Number.isInteger(numeric) ? String(numeric) : String(numeric);
}

function cardValue(card, name) {
  return card.querySelector(`[name="${name}"]`)?.value || "";
}

function collectItems() {
  return [...itemsEl.querySelectorAll(".item-card")].map((card) => ({
    name: cardValue(card, "name").trim(),
    id: cardValue(card, "id").trim(),
    category: cardValue(card, "category").trim(),
    area: cardValue(card, "area").trim(),
    recommendedValue: cardValue(card, "recommendedValue").trim(),
    recommendedUnit: cardValue(card, "recommendedUnit") || "days",
    displayUnit: cardValue(card, "displayUnit") || "days",
    rounding: cardValue(card, "rounding") || "floor",
  }));
}

function validateItems(items) {
  const errors = [];
  const seen = new Set();

  items.forEach((item, index) => {
    const label = `Item ${index + 1}`;
    if (!item.name) {
      errors.push(`${label}: add a name.`);
    }
    if (!/^[a-z][a-z0-9_]*$/.test(item.id)) {
      errors.push(`${label}: ID must be lowercase snake_case and start with a letter.`);
    }
    if (seen.has(item.id)) {
      errors.push(`${label}: ID '${item.id}' is duplicated.`);
    }
    seen.add(item.id);
    if (item.recommendedValue !== "") {
      const value = Number(item.recommendedValue);
      if (!Number.isFinite(value) || value <= 0) {
        errors.push(`${label}: recommended cadence must be greater than zero.`);
      }
    }
  });

  return errors;
}

function itemToYaml(item) {
  const lines = [
    `  - id: ${item.id}`,
    `    name: ${quoteYaml(item.name)}`,
  ];

  if (item.category) {
    lines.push(`    category: ${quoteYaml(item.category)}`);
  }
  if (item.area) {
    lines.push(`    area: ${quoteYaml(item.area)}`);
  }
  if (item.recommendedValue) {
    lines.push("    recommended_every:");
    lines.push(`      value: ${numberForYaml(item.recommendedValue)}`);
    lines.push(`      unit: ${item.recommendedUnit}`);
  }

  lines.push("    elapsed_display:");
  lines.push(`      unit: ${item.displayUnit}`);
  lines.push(`      rounding: ${item.rounding}`);

  return lines.join("\n");
}

function buildYaml(items) {
  return `chores:\n${items.map(itemToYaml).join("\n\n")}\n`;
}

function setStatus(message, type = "") {
  statusEl.textContent = message;
  statusEl.className = `status${type ? ` status--${type}` : ""}`;
}

function updateIndexes() {
  [...itemsEl.querySelectorAll(".item-card")].forEach((card, index) => {
    card.querySelector(".item-card__index").textContent = `Item ${index + 1}`;
    const removeButton = card.querySelector(".remove-button");
    removeButton.disabled = itemsEl.children.length === 1;
    removeButton.hidden = itemsEl.children.length === 1;
  });
}

function updateOutput() {
  const items = collectItems();
  const errors = validateItems(items);

  if (errors.length > 0) {
    outputEl.textContent = buildYaml(items.filter((item) => item.name && /^[a-z][a-z0-9_]*$/.test(item.id)));
    setStatus(errors[0], "error");
    return;
  }

  outputEl.textContent = buildYaml(items);
  setStatus(`${items.length} item${items.length === 1 ? "" : "s"} ready to copy.`, "success");
}

function fillCard(card, values = {}) {
  for (const [key, value] of Object.entries(values)) {
    const input = card.querySelector(`[name="${key}"]`);
    if (input) {
      input.value = value;
    }
  }
}

function addItem(values = {}) {
  const fragment = template.content.cloneNode(true);
  const card = fragment.querySelector(".item-card");
  fillCard(card, {
    recommendedUnit: "days",
    displayUnit: "days",
    rounding: "floor",
    ...values,
  });

  const nameInput = card.querySelector('[name="name"]');
  const idInput = card.querySelector('[name="id"]');
  let idTouched = Boolean(values.id);

  idInput.addEventListener("input", () => {
    idTouched = true;
  });

  nameInput.addEventListener("input", () => {
    if (!idTouched) {
      idInput.value = slugify(nameInput.value);
    }
  });

  card.querySelector(".remove-button").addEventListener("click", () => {
    card.remove();
    updateIndexes();
    updateOutput();
  });

  card.addEventListener("input", updateOutput);
  card.addEventListener("change", updateOutput);

  itemsEl.append(card);
  updateIndexes();
  updateOutput();
  nameInput.focus({ preventScroll: true });
}

function loadSample() {
  itemsEl.replaceChildren();
  sampleItems.forEach(addItem);
  itemsEl.querySelector('[name="name"]')?.focus({ preventScroll: true });
  updateOutput();
}

async function copyYaml() {
  updateOutput();
  const errors = validateItems(collectItems());
  if (errors.length > 0) {
    setStatus(errors[0], "error");
    return;
  }

  try {
    await navigator.clipboard.writeText(outputEl.textContent);
    setStatus("Copied YAML to clipboard.", "success");
  } catch {
    setStatus("Clipboard unavailable. Select the YAML and copy it manually.", "error");
  }
}

function downloadYaml() {
  updateOutput();
  const errors = validateItems(collectItems());
  if (errors.length > 0) {
    setStatus(errors[0], "error");
    return;
  }

  const blob = new Blob([outputEl.textContent], { type: "text/yaml" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "time_since_that.yaml";
  link.click();
  URL.revokeObjectURL(url);
  setStatus("Downloaded time_since_that.yaml.", "success");
}

form.addEventListener("reset", (event) => {
  event.preventDefault();
  itemsEl.replaceChildren();
  addItem();
});
addButton.addEventListener("click", () => addItem());
sampleButton.addEventListener("click", loadSample);
copyButton.addEventListener("click", copyYaml);
downloadButton.addEventListener("click", downloadYaml);

addItem({
  name: "Scoop cat litter",
  id: "scoop_cat_litter",
  category: "pets",
  area: "Bathroom",
  recommendedValue: "2",
  recommendedUnit: "days",
  displayUnit: "days",
  rounding: "floor",
});
