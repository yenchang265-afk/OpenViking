/**
 * What the plugins ship must not include the installer's own code.
 */

import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import { join, relative } from "node:path";
import test from "node:test";

import { ROOT, SHARED_DIR, resolveTargets } from "./sync.mjs";

// `lib/install/` is the installer's own code — the JSONC editor and the
// hooks/mcp cleanup — and no plugin imports it. One `./install/...` import from
// a module that plugins do import would put it in the closure, and from there
// into every vendored copy: installer-time JavaScript shipped to every harness,
// out of reach of a reviewer who reads the diff as runtime.
test("the installer's own modules stay out of what the plugins ship", async () => {
  const installerOnly = readdirSync(join(SHARED_DIR, "install"))
    .filter((file) => file.endsWith(".mjs"));
  assert.ok(installerOnly.length > 0, "expected installer-only modules under lib/install");

  const shipped = (await resolveTargets()).flatMap((target) =>
    target.files.map((file) => ({ file, where: relative(ROOT, target.dir) })));
  assert.deepEqual(
    shipped.filter((entry) => entry.file.startsWith("install/")),
    [],
    "a shipped module imports lib/install; the installer-only code must not be part of the runtime",
  );
});
