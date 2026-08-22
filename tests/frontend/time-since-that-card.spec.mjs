import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { test, expect } from "@playwright/test";

const ROOT = process.cwd();
const PORT = 4173;
let server;

test.use({ timezoneId: "UTC" });

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
};

test.beforeAll(async () => {
  server = http.createServer(async (request, response) => {
    const pathname = new URL(request.url, `http://127.0.0.1:${PORT}`).pathname;
    const filePath = normalize(join(ROOT, pathname));
    if (!filePath.startsWith(ROOT)) {
      response.writeHead(403).end();
      return;
    }
    try {
      const body = await readFile(filePath);
      response.writeHead(200, { "content-type": MIME_TYPES[extname(filePath)] || "text/plain" });
      response.end(body);
    } catch {
      response.writeHead(404).end();
    }
  });
  await new Promise((resolve) => server.listen(PORT, "127.0.0.1", resolve));
});

test.afterAll(async () => {
  await new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
});

test("aggregate card makes All exclusive and supports multiple tag filters", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${PORT}/tests/frontend/time-since-that-card-tags-harness.html`);

  await expect.poll(() => page.evaluate(() => window.cardHarness.filterState())).toEqual([
    { label: "All", pressed: "true" },
    { label: "daily", pressed: "false" },
    { label: "household", pressed: "false" },
    { label: "pets", pressed: "false" },
    { label: "No tag", pressed: "false" },
  ]);

  await page.evaluate(() => window.cardHarness.clickFilter("pets"));
  await expect.poll(() => page.evaluate(() => window.cardHarness.filterState())).toEqual([
    { label: "All", pressed: "false" },
    { label: "daily", pressed: "false" },
    { label: "household", pressed: "false" },
    { label: "pets", pressed: "true" },
    { label: "No tag", pressed: "false" },
  ]);
  await expect.poll(() => page.evaluate(() => window.cardHarness.names())).toEqual(["Scoop cat litter"]);

  await page.evaluate(() => window.cardHarness.clickFilter("daily"));
  await expect.poll(() => page.evaluate(() => window.cardHarness.filterState()[2].pressed)).toBe("false");
  await expect.poll(() => page.evaluate(() => window.cardHarness.filterState()[1].pressed)).toBe("true");

  await page.evaluate(() => window.cardHarness.clickFilter("All"));
  await expect.poll(() => page.evaluate(() => window.cardHarness.filterState())).toEqual([
    { label: "All", pressed: "true" },
    { label: "daily", pressed: "false" },
    { label: "household", pressed: "false" },
    { label: "pets", pressed: "false" },
    { label: "No tag", pressed: "false" },
  ]);
  await expect.poll(() => page.evaluate(() => window.cardHarness.names())).toEqual([
    "Take bins out", "Scoop cat litter", "Refill humidifier",
  ]);
});

test("aggregate card sorts by due date and recommended interval", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${PORT}/tests/frontend/time-since-that-card-tags-harness.html`);
  const sort = page.getByLabel("Sort chores");
  await expect.poll(() => page.evaluate(() => window.cardHarness.names())).toEqual([
    "Take bins out", "Scoop cat litter", "Refill humidifier",
  ]);

  await sort.selectOption("due-desc");
  await expect.poll(() => page.evaluate(() => window.cardHarness.names())).toEqual([
    "Refill humidifier", "Scoop cat litter", "Take bins out",
  ]);
  await sort.selectOption("interval-desc");
  await expect.poll(() => page.evaluate(() => window.cardHarness.names())).toEqual([
    "Refill humidifier", "Scoop cat litter", "Take bins out",
  ]);
  await sort.selectOption("interval-asc");
  await expect.poll(() => page.evaluate(() => window.cardHarness.names())).toEqual([
    "Take bins out", "Scoop cat litter", "Refill humidifier",
  ]);
});

test("completion count opens dates that can be cancelled, edited, and deleted", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-07-26T14:45:00Z"));
  await page.goto(`http://127.0.0.1:${PORT}/tests/frontend/time-since-that-card-tags-harness.html`);
  await page.getByRole("button", { name: "View completed dates for Scoop cat litter" }).click();
  await expect.poll(() => page.evaluate(() => window.cardHarness.historyCalls)).toEqual([
    { type: "time_since_that/completion_history", entity_id: "sensor.time_since_that_scoop_cat_litter" },
  ]);
  const firstDate = page.locator(".completion-history__date").first();
  await firstDate.click();
  const input = page.getByLabel("Completed date and time for Scoop cat litter");
  await input.fill("2026-07-23T10:30");
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(input).toHaveCount(0);
  await expect(firstDate).toBeFocused();
  await expect.poll(() => page.evaluate(() => window.cardHarness.historyCalls)).toHaveLength(1);

  await firstDate.click();
  await page.getByLabel("Completed date and time for Scoop cat litter").fill("2026-07-23T10:30");
  await page.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => page.evaluate(() => window.cardHarness.historyCalls[1])).toEqual({
    type: "time_since_that/update_completion",
    entity_id: "sensor.time_since_that_scoop_cat_litter",
    event_id: "litter-recent",
    completed_at: "2026-07-23T10:30:00.000Z",
  });

  await page.evaluate(() => {
    window.confirm = (message) => {
      window.confirmMessage = message;
      return true;
    };
  });
  await page.locator(".history-delete-button").first().click();
  await expect.poll(() => page.evaluate(() => window.confirmMessage))
    .toContain("This permanently removes the completion");
  await expect.poll(() => page.evaluate(() => window.cardHarness.historyCalls[2])).toEqual({
    type: "time_since_that/delete_completion",
    entity_id: "sensor.time_since_that_scoop_cat_litter",
    event_id: "litter-recent",
  });
  await expect(page.locator(".completion-history__date")).toHaveCount(1);
});

test("card shows adaptive last-done details and concise cadence", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-07-26T14:45:00Z"));
  await page.goto(`http://127.0.0.1:${PORT}/tests/frontend/time-since-that-card-tags-harness.html`);

  const cadence = await page.evaluate(() => window.cardHarness.details()
    .find((item) => item.name === "Scoop cat litter")
    .pills.find((pill) => pill.label?.startsWith("Recommended cadence:")));
  expect(cadence).toEqual({ text: "2 weeks", label: "Recommended cadence: 2 weeks" });

  const details = await page.evaluate(() => window.cardHarness.details());
  expect(details.find((item) => item.name === "Take bins out").pills)
    .not.toContainEqual(expect.objectContaining({ label: expect.stringContaining("Average time") }));
  expect(details.find((item) => item.name === "Take bins out").pills)
    .toContainEqual({ text: "1 completion", label: "View completed dates for Take bins out" });
  expect(details.find((item) => item.name === "Scoop cat litter").pills)
    .toContainEqual({ text: "Avg 9 days", label: "Average time between completions: 9 days" });

  const cases = [
    ["2026-07-26T14:27:00Z", "Last done: 18 minutes ago · 14:27"],
    ["2026-07-26T11:45:00Z", "Last done: 3 hours ago · 11:45"],
    ["2026-07-23T14:45:00Z", "Last done: 3 days ago · 23/07"],
    ["2026-07-12T14:45:00Z", "Last done: 2 weeks ago · 12/07"],
    ["2026-05-26T14:45:00Z", "Last done: 2 months ago · 26/05"],
    [null, "Last done: never"],
  ];
  for (const [lastDoneAt, expected] of cases) {
    await page.evaluate((value) => {
      window.cardHarness.setLastDone("sensor.time_since_that_scoop_cat_litter", value);
    }, lastDoneAt);
    await expect.poll(() => page.evaluate(() => window.cardHarness.details()
      .find((item) => item.name === "Scoop cat litter").lastDone)).toBe(expected);
  }
});

test("card editor offers a chore when switching to one-chore mode", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${PORT}/tests/frontend/time-since-that-card-tags-harness.html`);

  const config = await page.evaluate(() => new Promise((resolve) => {
    const editor = document.createElement("time-since-that-card-editor");
    editor.setConfig({ title: "Household" });
    editor.hass = window.cardHarness.card._hass;
    editor.addEventListener("config-changed", (event) => resolve(event.detail.config), { once: true });
    document.body.append(editor);
    const mode = editor.shadowRoot.querySelector("select");
    mode.value = "single";
    mode.dispatchEvent(new Event("change"));
  }));

  expect(config.entity).toBe("sensor.time_since_that_refill_humidifier");
});

test("card records a completion at an entered local date and time", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-07-26T14:45:00Z"));
  await page.goto(`http://127.0.0.1:${PORT}/tests/frontend/time-since-that-card-tags-harness.html`);
  await page.evaluate(() => window.cardHarness.card.setConfig({
    title: "Cat litter",
    entity: "sensor.time_since_that_scoop_cat_litter",
  }));

  const toggle = page.getByRole("button", { name: "Enter completed date for Scoop cat litter" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  const input = page.getByLabel("Completed date and time for Scoop cat litter");
  await expect(input).toBeFocused();
  await input.fill("2026-07-20T10:30");
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(input).toHaveCount(0);
  await expect(toggle).toBeFocused();
  expect(await page.evaluate(() => window.cardHarness.calls)).toEqual([]);

  await toggle.click();
  await page.getByLabel("Completed date and time for Scoop cat litter")
    .fill("2026-07-20T10:30");
  await page.getByRole("button", { name: "Save completion" }).click();
  await expect.poll(() => page.evaluate(() => window.cardHarness.calls)).toEqual([
    ["time_since_that", "record_completion", {
      entity_id: "sensor.time_since_that_scoop_cat_litter",
      completed_at: "2026-07-20T10:30:00.000Z",
    }],
  ]);
  await expect(page.getByLabel("Completed date and time for Scoop cat litter")).toHaveCount(0);
  await expect(toggle).toBeFocused();
});

test("dated completion keeps its value and disables controls when saving fails", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-07-26T14:45:00Z"));
  await page.goto(`http://127.0.0.1:${PORT}/tests/frontend/time-since-that-card-tags-harness.html`);
  await page.evaluate(() => {
    window.cardHarness.card.setConfig({
      title: "Cat litter",
      entity: "sensor.time_since_that_scoop_cat_litter",
    });
    window.cardHarness.card._hass.callService = () => new Promise((resolve, reject) => {
      window.rejectCompletion = reject;
    });
    window.cardHarness.card.hass = window.cardHarness.card._hass;
  });

  await page.getByRole("button", { name: "Enter completed date for Scoop cat litter" }).click();
  const input = page.getByLabel("Completed date and time for Scoop cat litter");
  await input.fill("2026-07-20T10:30");
  await page.getByRole("button", { name: "Save completion" }).click();
  await expect(input).toBeDisabled();
  await expect(page.getByRole("button", { name: "Enter completed date for Scoop cat litter" }))
    .toBeDisabled();
  await page.evaluate(() => window.rejectCompletion(new Error("Storage unavailable")));
  await expect(page.getByRole("alert")).toHaveText("Storage unavailable");
  await expect(input).toHaveValue("2026-07-20T10:30");
  await expect(input).toBeEnabled();
  await expect(input).toBeFocused();
});

test("dated completion converts browser-local time to an ISO instant", async ({ browser }) => {
  const context = await browser.newContext({ timezoneId: "America/New_York" });
  const page = await context.newPage();
  try {
    await page.clock.setFixedTime(new Date("2026-07-26T14:45:00Z"));
    await page.goto(`http://127.0.0.1:${PORT}/tests/frontend/time-since-that-card-tags-harness.html`);
    await page.evaluate(() => window.cardHarness.card.setConfig({
      title: "Cat litter",
      entity: "sensor.time_since_that_scoop_cat_litter",
    }));
    await page.getByRole("button", { name: "Enter completed date for Scoop cat litter" }).click();
    await page.getByLabel("Completed date and time for Scoop cat litter")
      .fill("2026-07-20T10:30");
    await page.getByRole("button", { name: "Save completion" }).click();
    await expect.poll(() => page.evaluate(() => window.cardHarness.calls[0][2].completed_at))
      .toBe("2026-07-20T14:30:00.000Z");
  } finally {
    await context.close();
  }
});

test("single-chore config limits the card and preserves mark-done payload", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${PORT}/tests/frontend/time-since-that-card-tags-harness.html`);

  await page.evaluate(() => window.cardHarness.card.setConfig({
    title: "Cat litter",
    entity: "sensor.time_since_that_scoop_cat_litter",
  }));
  await expect.poll(() => page.evaluate(() => window.cardHarness.names())).toEqual(["Scoop cat litter"]);

  await page.evaluate(() => window.cardHarness.pressFirst());
  await expect.poll(() => page.evaluate(() => window.cardHarness.calls)).toEqual([
    ["time_since_that", "mark_done", { entity_id: "sensor.time_since_that_scoop_cat_litter" }],
  ]);
});
