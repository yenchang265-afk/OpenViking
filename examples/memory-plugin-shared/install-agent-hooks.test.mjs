import assert from "node:assert/strict";
import { chmodSync, cpSync, existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import test from "node:test";

// `--source dev` installs out of the checkout the installer sits in, and the
// rest of the suite reads that tree while these installs run, so the installs
// here get a copy of their own. The `.git` marker is a file, the way a linked
// worktree keeps it: enough for the installer to recognise a checkout, not
// enough for it to re-run the marketplace tests, which read repo-root files
// this copy does not carry.
const checkout = mkdtempSync(join(tmpdir(), "openviking-checkout-"));
process.on("exit", () => rmSync(checkout, { recursive: true, force: true }));
cpSync(resolve(dirname(fileURLToPath(import.meta.url)), ".."), join(checkout, "examples"), {
  recursive: true,
  filter: (source) => basename(source) !== "node_modules",
});
writeFileSync(join(checkout, ".git"), "gitdir: .\n");

const installer = join(checkout, "examples", "memory-plugin-shared", "install.sh");
const installedNode = spawnSync("bash", ["-c", "command -v node"], { encoding: "utf8" }).stdout.trim();

/** Every `command` string a hooks configuration holds, at any depth. */
function hookCommands(value, out = []) {
  if (Array.isArray(value)) for (const item of value) hookCommands(item, out);
  else if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      if (key === "command" && typeof child === "string") out.push(child);
      else hookCommands(child, out);
    }
  }
  return out;
}

function writeJson(file, value) {
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

function runInstaller(home, args, extraEnv = {}, script = installer) {
  return spawnSync("bash", [script, ...args], {
    cwd: checkout,
    env: {
      ...process.env,
      HOME: home,
      OPENVIKING_HOME: join(home, ".openviking"),
      OPENVIKING_INSTALLER_REEXEC: "0",
      OPENVIKING_DOWNLOAD_BASE: "https://downloads.example.invalid",
      OPENVIKING_SKIP_VERSION_CHECK: "1",
      ...extraEnv,
    },
    encoding: "utf8",
  });
}

function runUninstall(home, harnesses) {
  const result = runInstaller(home, [
    "--harness", harnesses,
    "--uninstall",
    "--yes",
  ]);
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
}

test("TraeCode CLI 2.0 installs the Codex plugin alias and removes the deprecated integration", () => {
  const home = mkdtempSync(join(tmpdir(), "openviking-trae-cli-hooks-"));
  try {
    const binDir = join(home, "bin");
    const cliLog = join(home, "trae-cli.log");
    mkdirSync(binDir, { recursive: true });
    const cliPath = join(binDir, "trae-cli");
    writeFileSync(cliPath, `#!/bin/sh
printf '%s\n' "$*" >> "$TRAE_CLI_TEST_LOG"
case "$*" in
  "plugin marketplace list --json") printf '{"marketplaces":[]}\n' ;;
  "plugin marketplace list") printf 'Marketplaces:\n' ;;
  "plugin list") printf 'openviking-memory\n' ;;
  "plugin add "*) exit 2 ;;
esac
exit 0
`);
    chmodSync(cliPath, 0o755);

    const hooksPath = join(home, ".trae", "cli", "hooks.json");
    const configPath = join(home, ".trae", "traecli.toml");
    writeJson(hooksPath, {
      version: 1,
      hooks: {
        Stop: [
          { hooks: [{ type: "command", command: "third-party stop" }] },
          {
            hooks: [{
              type: "command",
              command: "OPENVIKING_INTEGRATION_ID=openviking-memory node /tmp/agent-integrations/trae-cli/scripts/auto-capture.mjs",
            }],
          },
        ],
      },
    });
    mkdirSync(dirname(configPath), { recursive: true });
    writeFileSync(configPath, [
      'model = "test-model"',
      "",
      "[mcp_servers.third_party]",
      'url = "https://example.com/mcp"',
      "",
      '[mcp_servers."openviking-memory"]',
      'command = "node"',
      'args = ["/tmp/agent-integrations/trae-cli/servers/mcp-proxy.mjs"]',
      "",
    ].join("\n"));
    const integrationRoot = join(home, ".openviking", "agent-integrations", "trae-cli");
    mkdirSync(integrationRoot, { recursive: true });
    writeFileSync(join(integrationRoot, "integration.json"), "{}\n");
    const sharedRoot = join(home, ".openviking", "agent-integrations", "memory-plugin-shared");
    mkdirSync(sharedRoot, { recursive: true });

    const installed = runInstaller(home, [
      "--harness", "trae-cli",
      "--source", "dev",
      "--lang", "en",
      "--url", "http://127.0.0.1:9",
      "--api-key", "",
      "--yes",
    ], {
      PATH: `${binDir}:${dirname(installedNode)}:/usr/bin:/bin`,
      TRAE_CLI_TEST_LOG: cliLog,
    });
    assert.equal(installed.status, 0, `${installed.stdout}\n${installed.stderr}`);
    assert.match(installed.stdout, /Selected harnesses: trae-cli/u);
    assert.doesNotMatch(installed.stdout, /Selected harnesses: codex/u);
    assert.match(installed.stdout, /TraeCode CLI 2.0/);
    assert.doesNotMatch(installed.stdout, /trae-cli harness is deprecated/);
    assert.match(installed.stdout, /Removes the deprecated TRAE CLI Hooks integration: ~\/\.trae\/cli\/hooks\.json, ~\/\.trae\/traecli\.toml, ~\/\.openviking\/agent-integrations\/trae-cli\n/);
    assert.match(installed.stdout, /Uninstall: trae-cli plugin uninstall openviking-memory@openviking && trae-cli plugin marketplace remove openviking\n/);

    const hooks = JSON.parse(readFileSync(hooksPath, "utf8"));
    assert.ok(hooks.hooks.Stop.some((entry) => JSON.stringify(entry).includes("third-party stop")));
    assert.doesNotMatch(JSON.stringify(hooks), /openviking/i);

    const config = readFileSync(configPath, "utf8");
    assert.match(config, /model = "test-model"/);
    assert.match(config, /\[mcp_servers\.third_party\]/);
    assert.doesNotMatch(config, /openviking-memory/);
    assert.equal(existsSync(integrationRoot), false);
    assert.equal(existsSync(sharedRoot), false);

    const commands = readFileSync(cliLog, "utf8");
    assert.match(commands, /plugin marketplace add .*\/examples/mu);
    assert.match(commands, /plugin install openviking-memory@openviking/mu);
    assert.match(commands, /plugin enable openviking-memory@openviking/mu);
  } finally {
    rmSync(home, { recursive: true, force: true });
  }
});

test("TraeCode CLI 2.0 keeps the deprecated integration when plugin installation fails", () => {
  const home = mkdtempSync(join(tmpdir(), "openviking-trae-cli-failed-migration-"));
  try {
    const binDir = join(home, "bin");
    mkdirSync(binDir, { recursive: true });
    const cliPath = join(binDir, "trae-cli");
    writeFileSync(cliPath, `#!/bin/sh
case "$*" in
  "plugin marketplace list --json") printf '{"marketplaces":[]}\n' ;;
  "plugin marketplace list") printf 'Marketplaces:\n' ;;
  "plugin add "*|"plugin install "*) exit 1 ;;
esac
exit 0
`);
    chmodSync(cliPath, 0o755);

    const hooksPath = join(home, ".trae", "cli", "hooks.json");
    const configPath = join(home, ".trae", "traecli.toml");
    writeJson(hooksPath, { hooks: { Stop: [{ hooks: [{
      type: "command",
      command: "OPENVIKING_INTEGRATION_ID=openviking-memory node /tmp/agent-integrations/trae-cli/scripts/auto-capture.mjs",
    }] }] } });
    mkdirSync(dirname(configPath), { recursive: true });
    writeFileSync(configPath, '[mcp_servers."openviking-memory"]\ncommand = "node"\n');
    const integrationRoot = join(home, ".openviking", "agent-integrations", "trae-cli");
    mkdirSync(integrationRoot, { recursive: true });

    const installed = runInstaller(home, [
      "--harness", "trae-cli",
      "--source", "dev",
      "--lang", "en",
      "--url", "http://127.0.0.1:9",
      "--api-key", "",
      "--yes",
    ], { PATH: `${binDir}:${dirname(installedNode)}:/usr/bin:/bin` });

    assert.equal(installed.status, 0, `${installed.stdout}\n${installed.stderr}`);
    assert.match(installed.stdout, /plugin add\/install returned non-zero/u);
    assert.match(readFileSync(hooksPath, "utf8"), /openviking-memory/u);
    assert.match(readFileSync(configPath, "utf8"), /openviking-memory/u);
    assert.equal(existsSync(integrationRoot), true);
  } finally {
    rmSync(home, { recursive: true, force: true });
  }
});

test("TraeCode CLI 2.0 keeps the deprecated integration when plugin enable fails", () => {
  const home = mkdtempSync(join(tmpdir(), "openviking-trae-cli-failed-enable-"));
  try {
    const binDir = join(home, "bin");
    mkdirSync(binDir, { recursive: true });
    const cliPath = join(binDir, "trae-cli");
    writeFileSync(cliPath, `#!/bin/sh
case "$*" in
  "plugin marketplace list --json") printf '{"marketplaces":[]}\n' ;;
  "plugin marketplace list") printf 'Marketplaces:\n' ;;
  "plugin add "*) exit 2 ;;
  "plugin enable "*) exit 1 ;;
esac
exit 0
`);
    chmodSync(cliPath, 0o755);

    const hooksPath = join(home, ".trae", "cli", "hooks.json");
    const configPath = join(home, ".trae", "traecli.toml");
    writeJson(hooksPath, { hooks: { Stop: [{ hooks: [{
      type: "command",
      command: "OPENVIKING_INTEGRATION_ID=openviking-memory node /tmp/agent-integrations/trae-cli/scripts/auto-capture.mjs",
    }] }] } });
    mkdirSync(dirname(configPath), { recursive: true });
    writeFileSync(configPath, '[mcp_servers."openviking-memory"]\ncommand = "node"\n');
    const integrationRoot = join(home, ".openviking", "agent-integrations", "trae-cli");
    mkdirSync(integrationRoot, { recursive: true });

    const installed = runInstaller(home, [
      "--harness", "trae-cli",
      "--source", "dev",
      "--lang", "en",
      "--url", "http://127.0.0.1:9",
      "--api-key", "",
      "--yes",
    ], { PATH: `${binDir}:${dirname(installedNode)}:/usr/bin:/bin` });

    assert.equal(installed.status, 0, `${installed.stdout}\n${installed.stderr}`);
    assert.match(installed.stdout, /could not be enabled/u);
    assert.match(readFileSync(hooksPath, "utf8"), /openviking-memory/u);
    assert.match(readFileSync(configPath, "utf8"), /openviking-memory/u);
    assert.equal(existsSync(integrationRoot), true);
  } finally {
    rmSync(home, { recursive: true, force: true });
  }
});


// The hook hosts (Cursor, TRAE, TRAE CN, ZCode, Kimi Code, CodeBuddy Code) are
// no longer installed, but `--uninstall` still removes what an earlier
// installer set up. These seed the files that install wrote.
function seedCursorInstall(home, ovHome = join(home, ".openviking")) {
  const root = join(ovHome, "agent-integrations", "cursor");
  const hook = `OPENVIKING_INTEGRATION_ID=openviking-memory node ${join(root, "scripts", "hook.mjs")} stop cursor # openviking-memory`;
  mkdirSync(join(root, "scripts"), { recursive: true });
  writeFileSync(join(root, "scripts", "hook.mjs"), "");
  writeJson(join(home, ".cursor", "hooks.json"), {
    version: 1,
    hooks: { stop: [{ command: "third-party" }, { command: hook }], sessionStart: [{ command: hook }] },
  });
  writeJson(join(home, ".cursor", "mcp.json"), {
    mcpServers: {
      openviking: { command: "node", args: [join(root, "servers", "mcp-proxy.mjs")] },
      other: { command: "other-server" },
    },
  });
  mkdirSync(join(home, ".cursor", "rules"), { recursive: true });
  writeFileSync(join(home, ".cursor", "rules", "openviking-memory.mdc"), "");
  for (const skill of ["openviking-memory", "openviking-skills", "ov-experience-memory"]) {
    mkdirSync(join(home, ".cursor", "skills", skill), { recursive: true });
  }
  return root;
}

function seedSharedRuntime(ovHome) {
  const shared = join(ovHome, "agent-integrations", "memory-plugin-shared", "lib");
  cpSync(join(checkout, "examples", "memory-plugin-shared", "lib", "install"), join(shared, "install"), { recursive: true });
  return dirname(shared);
}

const ownCommands = (file) => hookCommands(JSON.parse(readFileSync(file, "utf8")))
  .filter((command) => command.includes("openviking-memory"));

test("installing a hook host is refused and points at --uninstall", () => {
  const home = mkdtempSync(join(tmpdir(), "openviking-hook-host-refused-"));
  try {
    for (const host of ["cursor", "trae", "trae-cn", "zcode", "kimicode", "codebuddy"]) {
      const result = runInstaller(home, [
        "--harness", host, "--source", "dev", "--lang", "en", "--url", "http://127.0.0.1:9", "--api-key", "", "--yes",
      ]);
      assert.equal(result.status, 2, `${host}: ${result.stdout}\n${result.stderr}`);
      assert.match(result.stderr, new RegExp(`no longer installs ${host}; --uninstall removes an earlier install`));
    }
    assert.equal(existsSync(join(home, ".openviking")), false);
  } finally {
    rmSync(home, { recursive: true, force: true });
  }
});

test("uninstall removes an earlier hook-host install, keeps unrelated entries and is idempotent", () => {
  const home = mkdtempSync(join(tmpdir(), "openviking-uninstall-hooks-"));
  try {
    const ovHome = join(home, ".openviking");
    const root = seedCursorInstall(home);
    const shared = seedSharedRuntime(ovHome);
    const traeHooks = join(home, ".trae", "hooks.json");
    writeJson(traeHooks, {
      hooks: { "session-start": [{ command: `node ${join(ovHome, "agent-integrations", "trae", "scripts", "hook.mjs")} session-start trae # openviking-memory` }] },
    });
    mkdirSync(join(ovHome, "agent-integrations", "trae"), { recursive: true });

    runUninstall(home, "cursor,trae");
    const hooksPath = join(home, ".cursor", "hooks.json");
    const mcp = JSON.parse(readFileSync(join(home, ".cursor", "mcp.json"), "utf8"));
    assert.deepEqual(ownCommands(hooksPath), []);
    assert.deepEqual(hookCommands(JSON.parse(readFileSync(hooksPath, "utf8"))), ["third-party"]);
    assert.equal(Boolean(mcp.mcpServers.openviking), false);
    assert.ok(mcp.mcpServers.other);
    assert.deepEqual(ownCommands(traeHooks), []);
    assert.equal(existsSync(join(home, ".cursor", "rules", "openviking-memory.mdc")), false);
    assert.equal(existsSync(join(home, ".cursor", "skills", "openviking-memory")), false);
    assert.equal(existsSync(root), false);
    assert.equal(existsSync(join(ovHome, "agent-integrations", "trae")), false);
    // The last hook host gone, the shared runtime goes with it.
    assert.equal(existsSync(shared), false);

    runUninstall(home, "cursor,trae");
    assert.deepEqual(hookCommands(JSON.parse(readFileSync(hooksPath, "utf8"))), ["third-party"]);
  } finally {
    rmSync(home, { recursive: true, force: true });
  }
});

test("uninstall without --harness removes the hook hosts it detects", () => {
  const home = mkdtempSync(join(tmpdir(), "openviking-uninstall-detected-"));
  try {
    seedCursorInstall(home);
    const result = runInstaller(home, ["--uninstall", "--lang", "en", "--yes"]);
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
    assert.match(result.stdout, /Selected harnesses: cursor\n/);
    assert.deepEqual(ownCommands(join(home, ".cursor", "hooks.json")), []);

    const empty = mkdtempSync(join(tmpdir(), "openviking-uninstall-nothing-"));
    try {
      const none = runInstaller(empty, ["--uninstall", "--lang", "en", "--yes"]);
      assert.equal(none.status, 0, `${none.stdout}\n${none.stderr}`);
      assert.match(none.stdout, /No integration to uninstall was found/);
    } finally {
      rmSync(empty, { recursive: true, force: true });
    }
  } finally {
    rmSync(home, { recursive: true, force: true });
  }
});

// The documented uninstall pipes install.sh from a URL, so the running script
// has no lib/ sibling, and the first uninstall drops the assembled copy under
// $OV_HOME. Nothing left to read is not a reason to abort — and never a reason
// to fetch sources.
test("uninstall with no installer runtime on disk removes what it can and fetches nothing", () => {
  const home = mkdtempSync(join(tmpdir(), "openviking-uninstall-sourceless-"));
  try {
    const root = seedCursorInstall(home);
    const detached = join(home, "install.sh");
    cpSync(installer, detached);
    const result = runInstaller(home, ["--harness", "cursor", "--uninstall", "--lang", "en", "--yes"], {
      OPENVIKING_DOWNLOAD_BASE: "file:///nonexistent",
    }, detached);
    const output = `${result.stdout}\n${result.stderr}`;
    assert.equal(result.status, 0, output);
    assert.equal(existsSync(join(home, ".openviking", "memory-plugin-marketplace")), false);
    assert.equal(existsSync(root), false);
    assert.equal(existsSync(join(home, ".cursor", "rules", "openviking-memory.mdc")), false);
    // The host's own files could not be edited, so the uninstall has to name them.
    assert.match(result.stdout, /by hand from:.*\.cursor\/hooks\.json/u, output);
  } finally {
    rmSync(home, { recursive: true, force: true });
  }
});

// A symlinked OPENVIKING_HOME puts a symlink in every helper path the installer
// resolves under it; a detached script (no lib/ sibling) reads its helpers
// from there, as the documented piped uninstall does.
test("uninstall reads its helpers through a symlinked OPENVIKING_HOME", () => {
  const home = mkdtempSync(join(tmpdir(), "openviking-symlinked-home-"));
  try {
    const realOvHome = join(home, "real-openviking");
    mkdirSync(realOvHome);
    const ovHome = join(home, ".openviking");
    symlinkSync(realOvHome, ovHome, "dir");
    seedCursorInstall(home, ovHome);
    seedSharedRuntime(ovHome);
    const detached = join(home, "install.sh");
    cpSync(installer, detached);

    const removed = runInstaller(home, ["--harness", "cursor", "--uninstall", "--lang", "en", "--yes"], {
      OPENVIKING_HOME: ovHome,
    }, detached);
    assert.equal(removed.status, 0, `${removed.stdout}\n${removed.stderr}`);
    assert.deepEqual(ownCommands(join(home, ".cursor", "hooks.json")), []);
    assert.equal(Boolean(JSON.parse(readFileSync(join(home, ".cursor", "mcp.json"), "utf8")).mcpServers?.openviking), false);
  } finally {
    rmSync(home, { recursive: true, force: true });
  }
});

test("malformed existing agent JSON fails the uninstall without overwriting user configuration", () => {
  const home = mkdtempSync(join(tmpdir(), "openviking-agent-invalid-json-"));
  try {
    const hooks = join(home, ".cursor", "hooks.json");
    mkdirSync(dirname(hooks), { recursive: true });
    const original = '{"hooks":{"stop":[{"command":"third-party"}]},}';
    writeFileSync(hooks, original);
    const result = runInstaller(home, ["--harness", "cursor", "--uninstall", "--lang", "en", "--yes"]);
    assert.notEqual(result.status, 0, `${result.stdout}\n${result.stderr}`);
    assert.equal(readFileSync(hooks, "utf8"), original);
  } finally {
    rmSync(home, { recursive: true, force: true });
  }
});
