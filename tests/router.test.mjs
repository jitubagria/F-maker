import assert from "node:assert/strict";
import test from "node:test";
import { applyRoute, normaliseRoute } from "../static/router.mjs";

function item(id, route = null) {
  return {
    id,
    hidden: false,
    dataset: route ? { route } : {},
    classList: {
      values: new Set(),
      toggle(name, enabled) { if (enabled) this.values.add(name); else this.values.delete(name); },
      contains(name) { return this.values.has(name); },
    },
  };
}

function fixtureDocument() {
  const screens = ["dashboard", "create", "exports", "templates", "assets", "brands"].map((id) => item(id));
  const links = screens.map((screen) => item(`nav-${screen.id}`, screen.id));
  return {
    screens,
    links,
    querySelectorAll(selector) {
      return selector === ".screen" ? screens : links;
    },
  };
}

test("empty and unknown hashes safely default to create", () => {
  assert.equal(normaliseRoute(""), "create");
  assert.equal(normaliseRoute("#not-a-screen"), "create");
});

test("a deep-link activates only its matching screen and navigation item", () => {
  const page = fixtureDocument();
  assert.equal(applyRoute(page, "#templates"), "templates");
  assert.deepEqual(page.screens.filter((screen) => !screen.hidden).map((screen) => screen.id), ["templates"]);
  assert.deepEqual(page.links.filter((link) => link.classList.contains("active")).map((link) => link.dataset.route), ["templates"]);
});
