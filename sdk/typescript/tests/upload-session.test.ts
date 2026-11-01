import { afterEach, describe, expect, it, vi } from "vitest";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { OpenVikingClient, OpenVikingError } from "../src/index.js";
import { partRetry } from "../src/upload-session.js";

// Re-sent parts wait for real backoff in production; tests do not.
partRetry.baseDelayMs = 0;

const ok = (result: unknown) =>
  new Response(JSON.stringify({ status: "ok", result }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

const fail = (status: number) =>
  new Response(
    JSON.stringify({
      status: "error",
      error: { code: "ERR", message: `HTTP ${status}` },
    }),
    { status, headers: { "Content-Type": "application/json" } },
  );

interface Call {
  method: string;
  path: string;
  body: unknown;
}

/** Fake session API: records calls and part bytes; `createStatus`/`failPart` inject errors. */
function sessionServer(options: {
  partSize?: number;
  createStatus?: number;
  failPart?: string;
  /** Status `failPart` answers (default 500). */
  failStatus?: number;
  /** Fail `failPart` only for its first N attempts (default: always). */
  failTimes?: number;
  /** Runs when the session is created: after the listing, before any part. */
  onCreate?: () => Promise<void>;
}) {
  const calls: Call[] = [];
  const parts = new Map<string, Uint8Array>();
  const attempts = new Map<string, number>();
  const fetcher = vi.fn<typeof fetch>(async (input, init) => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    const raw = init?.body;
    const body =
      typeof raw === "string"
        ? JSON.parse(raw)
        : raw instanceof Uint8Array
          ? raw
          : raw;
    calls.push({ method, path: url.pathname, body });
    if (method === "POST" && url.pathname === "/api/v1/uploads") {
      await options.onCreate?.();
      return options.createStatus
        ? fail(options.createStatus)
        : ok({ upload_id: "u1", part_size_bytes: options.partSize ?? 4 });
    }
    if (method === "PUT" && url.pathname.startsWith("/api/v1/uploads/u1/")) {
      const attempt = attempts.get(url.pathname) ?? 0;
      attempts.set(url.pathname, attempt + 1);
      if (
        url.pathname === options.failPart &&
        (options.failTimes === undefined || attempt < options.failTimes)
      )
        return fail(options.failStatus ?? 500);
      parts.set(url.pathname, new Uint8Array(raw as Uint8Array));
      return ok({});
    }
    if (url.pathname === "/api/v1/uploads/u1/complete")
      return ok({ temp_file_id: "session_u1" });
    if (method === "DELETE") return ok({});
    if (url.pathname === "/api/v1/resources/temp_upload")
      return ok({ temp_file_id: "legacy" });
    return ok({ uri: "viking://resources/x" });
  });
  const fileBytes = (index: number) => {
    const prefix = `/api/v1/uploads/u1/files/${index}/parts/`;
    const keys = [...parts.keys()]
      .filter((k) => k.startsWith(prefix))
      .sort(
        (a, b) =>
          Number(a.slice(prefix.length)) - Number(b.slice(prefix.length)),
      );
    return Buffer.concat(keys.map((k) => parts.get(k)!)).toString();
  };
  return { calls, parts, attempts, fetcher, fileBytes };
}

const directories: string[] = [];
afterEach(async () => {
  await Promise.all(
    directories.splice(0).map((d) => rm(d, { recursive: true, force: true })),
  );
});

async function folder(): Promise<string> {
  const base = await mkdtemp(join(tmpdir(), "openviking-session-"));
  directories.push(base);
  const root = join(base, "docs");
  await mkdir(join(root, "sub"), { recursive: true });
  await writeFile(join(root, "a.md"), "0123456789");
  await writeFile(join(root, "sub", "b.txt"), "xyz");
  await writeFile(join(root, "empty.txt"), "");
  return root;
}

const resourceBody = (calls: Call[]) =>
  calls.find((c) => c.path === "/api/v1/resources")?.body as Record<
    string,
    unknown
  >;

describe("chunked upload sessions", () => {
  it("uploads a folder file by file without zipping it", async () => {
    const server = sessionServer({ partSize: 4 });
    const client = new OpenVikingClient({
      baseUrl: "https://example.com",
      fetch: server.fetcher,
    });

    await client.addResource(await folder());

    const created = server.calls[0]!;
    expect(created).toMatchObject({ method: "POST", path: "/api/v1/uploads" });
    expect(created.body).toEqual({
      kind: "directory",
      name: "docs",
      files: [
        { path: "a.md", size: 10 },
        { path: "empty.txt", size: 0 },
        { path: "sub/b.txt", size: 3 },
      ],
    });
    expect(server.fileBytes(0)).toBe("0123456789");
    expect(server.fileBytes(2)).toBe("xyz");
    expect(server.parts.size).toBe(4);
    const put = server.fetcher.mock.calls.find(
      ([, init]) => init?.method === "PUT",
    )!;
    expect(new Headers(put[1]?.headers).get("Content-Type")).toBe(
      "application/octet-stream",
    );
    expect(resourceBody(server.calls)).toMatchObject({
      temp_file_id: "session_u1",
      source_name: "docs",
    });
    expect(server.calls.some((c) => c.path.endsWith("/temp_upload"))).toBe(
      false,
    );
  });

  it.each([404, 405, 409])(
    "falls back to the single-request upload on HTTP %i",
    async (status) => {
      const server = sessionServer({ createStatus: status });
      const client = new OpenVikingClient({
        baseUrl: "https://example.com",
        fetch: server.fetcher,
      });

      await client.addResource(await folder());

      expect(resourceBody(server.calls)).toMatchObject({
        temp_file_id: "legacy",
      });
    },
  );

  it("aborts the session when a part fails", async () => {
    const server = sessionServer({
      partSize: 4,
      failPart: "/api/v1/uploads/u1/files/0/parts/2",
    });
    const client = new OpenVikingClient({
      baseUrl: "https://example.com",
      fetch: server.fetcher,
    });
    const root = await folder();

    await expect(client.addResource(join(root, "a.md"))).rejects.toBeInstanceOf(
      OpenVikingError,
    );

    expect(server.calls.at(-1)).toMatchObject({
      method: "DELETE",
      path: "/api/v1/uploads/u1",
    });
    expect(server.calls.some((c) => c.path.endsWith("/complete"))).toBe(false);
    expect(resourceBody(server.calls)).toBeUndefined();
  });

  it("re-sends a part after a transient failure", async () => {
    const part = "/api/v1/uploads/u1/files/0/parts/2";
    const server = sessionServer({
      partSize: 4,
      failPart: part,
      failStatus: 503,
      failTimes: 2,
    });
    const client = new OpenVikingClient({
      baseUrl: "https://example.com",
      fetch: server.fetcher,
    });
    const root = await folder();

    await client.addResource(join(root, "a.md"));

    expect(server.attempts.get(part)).toBe(3);
    expect(server.fileBytes(0)).toBe("0123456789");
    expect(resourceBody(server.calls)).toMatchObject({
      temp_file_id: "session_u1",
    });
  });

  it("does not re-send a part the server rejected", async () => {
    const part = "/api/v1/uploads/u1/files/0/parts/2";
    const server = sessionServer({
      partSize: 4,
      failPart: part,
      failStatus: 400,
    });
    const client = new OpenVikingClient({
      baseUrl: "https://example.com",
      fetch: server.fetcher,
    });
    const root = await folder();

    await expect(client.addResource(join(root, "a.md"))).rejects.toBeInstanceOf(
      OpenVikingError,
    );
    expect(server.attempts.get(part)).toBe(1);
  });

  it.each([
    [
      "grows",
      "a.md",
      (root: string) => writeFile(join(root, "a.md"), "0123456789-more"),
    ],
    [
      "shrinks",
      "sub/b.txt",
      (root: string) => writeFile(join(root, "sub", "b.txt"), "x"),
    ],
    [
      "is removed",
      "sub/b.txt",
      (root: string) => rm(join(root, "sub", "b.txt")),
    ],
  ] as const)(
    "fails naming a file that %s after the listing",
    async (_label, changed, change) => {
      const root = await folder();
      const server = sessionServer({
        partSize: 4,
        onCreate: () => change(root),
      });
      const client = new OpenVikingClient({
        baseUrl: "https://example.com",
        fetch: server.fetcher,
      });

      const error = await client.addResource(root).catch((e: unknown) => e);

      expect(error).toBeInstanceOf(OpenVikingError);
      expect((error as OpenVikingError).code).toBe("FAILED_PRECONDITION");
      expect((error as Error).message).toContain(
        `'${changed}' changed while uploading`,
      );
      expect(server.calls.at(-1)).toMatchObject({ method: "DELETE" });
      expect(server.calls.some((c) => c.path.endsWith("/complete"))).toBe(
        false,
      );
    },
  );

  it("keeps skills on the single-request upload", async () => {
    const server = sessionServer({});
    const client = new OpenVikingClient({
      baseUrl: "https://example.com",
      fetch: server.fetcher,
    });

    await client.addSkill(await folder());

    expect(server.calls.some((c) => c.path === "/api/v1/uploads")).toBe(false);
    expect(server.calls[0]?.path).toBe("/api/v1/resources/temp_upload");
  });
});
