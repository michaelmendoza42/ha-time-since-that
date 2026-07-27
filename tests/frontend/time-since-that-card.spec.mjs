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

test("aggregate card applies All, soft-deselect, and tag filters", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${PORT}/tests/frontend/time-since-that-card-tags-harness.html`);

  await expect.poll(() => page.evaluate(() => window.cardHarness.filterState())).toEqual([
    { label: "All", pressed: "true" },
    { label: "daily", pressed: "true" },
    { label: "household", pressed: "true" },
    { label: "pets", pressed: "true" },
    { label: "No tag", pressed: "true" },
  ]);

  await page.evaluate(() => window.cardHarness.clickFilter("pets"));
  await expect.poll(() => page.evaluate(() => window.cardHarness.filterState()[0].pressed)).toBe("mixed");

  await page.evaluate(() => window.cardHarness.clickFilter("All"));
  await expect.poll(() => page.evaluate(() => window.cardHarness.filterState()[0].pressed)).toBe("true");

  await page.evaluate(() => window.cardHarness.clickFilter("All"));
  await expect.poll(() => page.evaluate(() => window.cardHarness.names())).toEqual([]);

  await page.evaluate(() => window.cardHarness.clickFilter("pets"));
  await expect.poll(() => page.evaluate(() => window.cardHarness.names())).toEqual(["Scoop cat litter"]);
});

test("card shows adaptive last-done details and concise cadence", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-07-26T14:45:00Z"));
  await page.goto(`http://127.0.0.1:${PORT}/tests/frontend/time-since-that-card-tags-harness.html`);

  const cadence = await page.evaluate(() => window.cardHarness.details()
    .find((item) => item.name === "Scoop cat litter")
    .pills.find((pill) => pill.label?.startsWith("Recommended cadence:")));
  expect(cadence).toEqual({ text: "2 weeks", label: "Recommended cadence: 2 weeks" });

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
