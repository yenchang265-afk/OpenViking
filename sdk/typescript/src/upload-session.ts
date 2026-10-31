import { OpenVikingError } from "./errors.js";
import { nodeUploadEntries, openNodeFile } from "./node-files.js";
import type { NodeFileReader } from "./node-files.js";
import type { OpenVikingTransport } from "./transport.js";

/** Statuses meaning the server cannot take a chunked upload (no route or shared mode). */
const SESSIONS_UNAVAILABLE = new Set([404, 405, 409]);

/** Statuses (beside 5xx) after which a part is re-sent. */
const TRANSIENT_STATUSES = new Set([408, 429]);
/** Error codes of failures that never reached the server: network down, timeout. */
const TRANSIENT_CODES = new Set(["UNAVAILABLE", "DEADLINE_EXCEEDED"]);

/** Part re-send policy: extra attempts and the first backoff, doubled per attempt. */
export const partRetry = { attempts: 3, baseDelayMs: 500 };

interface UploadEntry {
  path: string;
  size: number;
  localPath: string;
}

function isTransient(error: unknown): boolean {
  if (!(error instanceof OpenVikingError)) return false;
  if (error.statusCode !== undefined)
    return error.statusCode >= 500 || TRANSIENT_STATUSES.has(error.statusCode);
  return TRANSIENT_CODES.has(error.code);
}

/** The file no longer has the size the session was created with. */
function changedWhileUploading(entry: UploadEntry, cause?: unknown) {
  return new OpenVikingError(
    `'${entry.path}' changed while uploading (it was ${entry.size} bytes when ` +
      "the upload started). Retry, or leave out files that are being written, " +
      "such as .git or logs.",
    {
      code: "FAILED_PRECONDITION",
      details: { path: entry.path, size: entry.size },
      cause,
    },
  );
}

/** A file removed after the listing changed; other open errors keep their cause. */
async function openEntry(entry: UploadEntry): Promise<NodeFileReader> {
  try {
    return await openNodeFile(entry.localPath);
  } catch (error) {
    if ((error as { code?: unknown }).code === "ENOENT")
      throw changedWhileUploading(entry, error);
    throw error;
  }
}

async function putPart(
  transport: OpenVikingTransport,
  url: string,
  data: Uint8Array,
): Promise<void> {
  for (let attempt = 0; ; attempt += 1) {
    try {
      await transport.request("PUT", url, {
        raw: { data, contentType: "application/octet-stream" },
      });
      return;
    } catch (error) {
      if (attempt >= partRetry.attempts || !isTransient(error)) throw error;
      await new Promise((resolve) =>
        setTimeout(resolve, partRetry.baseDelayMs * 2 ** attempt),
      );
    }
  }
}

/** Send exactly the `entry.size` bytes the session declared, as numbered parts. */
async function sendFileParts(
  transport: OpenVikingTransport,
  uploadId: string,
  index: number,
  entry: UploadEntry,
  partSize: number,
): Promise<void> {
  // One handle for every part: a file replaced mid-upload cannot mix contents.
  const file = await openEntry(entry);
  try {
    for (
      let number = 1, offset = 0;
      offset < entry.size;
      number += 1, offset += partSize
    ) {
      const length = Math.min(partSize, entry.size - offset);
      const data = await file.read(offset, length);
      if (data.length < length) throw changedWhileUploading(entry);
      await putPart(
        transport,
        `/api/v1/uploads/${uploadId}/files/${index}/parts/${number}`,
        data,
      );
    }
    // A byte past the declared size: the file grew after the listing.
    if ((await file.read(entry.size, 1)).length > 0)
      throw changedWhileUploading(entry);
  } finally {
    await file.close();
  }
}

/**
 * Upload a Node.js local file or directory through /api/v1/uploads, reading one part
 * from disk at a time (directories are not zipped).
 *
 * Returns `null` when the path is local but the server has no chunked uploads (or the
 * directory is empty) so the caller falls back to the single-request upload, and
 * `undefined` when the path is not a local file or directory. A failure after the
 * session is created aborts the session and rethrows.
 */
export async function uploadViaSession(
  transport: OpenVikingTransport,
  path: string,
): Promise<{ tempFileId: string; sourceName: string } | null | undefined> {
  const local = await nodeUploadEntries(path);
  if (!local) return undefined;
  if (transport.uploadMode === "shared" || local.entries.length === 0)
    return null;

  let created: { upload_id: string; part_size_bytes: number };
  try {
    created = await transport.request("POST", "/api/v1/uploads", {
      body: {
        kind: local.kind,
        name: local.name,
        files: local.entries.map(({ path: p, size }) => ({ path: p, size })),
      },
    });
  } catch (error) {
    if (
      error instanceof OpenVikingError &&
      error.statusCode !== undefined &&
      SESSIONS_UNAVAILABLE.has(error.statusCode)
    )
      return null;
    throw error;
  }
  const { upload_id: uploadId, part_size_bytes: partSize } = created;
  if (!uploadId || !(partSize > 0))
    throw new OpenVikingError("Invalid upload session response", {
      code: "INTERNAL",
    });

  try {
    for (const [index, entry] of local.entries.entries()) {
      await sendFileParts(transport, uploadId, index, entry, partSize);
    }
    const done = await transport.request<{ temp_file_id: string }>(
      "POST",
      `/api/v1/uploads/${uploadId}/complete`,
    );
    return { tempFileId: done.temp_file_id, sourceName: local.name };
  } catch (error) {
    await transport
      .request("DELETE", `/api/v1/uploads/${uploadId}`)
      .catch(() => undefined);
    throw error;
  }
}
