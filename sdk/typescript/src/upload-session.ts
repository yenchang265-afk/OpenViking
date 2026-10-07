import { OpenVikingError } from "./errors.js";
import { nodeUploadEntries, readNodeFilePart } from "./node-files.js";
import type { OpenVikingTransport } from "./transport.js";

/** Statuses meaning the server cannot take a chunked upload (no route or shared mode). */
const SESSIONS_UNAVAILABLE = new Set([404, 405, 409]);

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
      for (
        let number = 1, offset = 0;
        offset < entry.size;
        number += 1, offset += partSize
      ) {
        const data = await readNodeFilePart(
          entry.localPath,
          offset,
          Math.min(partSize, entry.size - offset),
        );
        await transport.request(
          "PUT",
          `/api/v1/uploads/${uploadId}/files/${index}/parts/${number}`,
          { raw: { data, contentType: "application/octet-stream" } },
        );
      }
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
