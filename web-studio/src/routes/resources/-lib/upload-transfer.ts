import i18n from '#/i18n'
import { getOvResult, postResourcesTempUpload } from '#/lib/ov-client'
import {
  SessionsUnavailableError,
  UploadSessionError,
  resumeUploadSession,
  uploadSession,
} from './chunked-upload'
import type { ChunkedUploadOptions } from './chunked-upload'
import { getFolderSize, zipFolder } from './folder-upload'
import type { FolderGroup } from './folder-upload'
import type { TempUploadResult } from './resource-import-types'
import { BROWSER_ZIP_MAX_BYTES } from './upload-limits'

/** A selected upload: a single file, or a folder (whose `file` is only a label). */
export interface UploadItem {
  file: File
  folder?: FolderGroup
}

export interface TransferResult {
  tempFileId: string
  /** Name to record as the resource's source_name. */
  sourceName: string
}

/** A folder that needs the zip fallback is too large to zip in the browser. */
export class FolderTooLargeForZipError extends Error {
  constructor(name: string) {
    super(
      `"${name}" is too large to upload as a zip; this server does not accept chunked uploads.`,
    )
    this.name = 'FolderTooLargeForZipError'
  }
}

function sessionOptions(
  item: UploadItem,
): Pick<ChunkedUploadOptions, 'kind' | 'name' | 'sources'> {
  if (!item.folder) {
    return {
      kind: 'file',
      name: item.file.name,
      sources: [{ path: item.file.name, file: item.file }],
    }
  }
  const prefix = `${item.folder.name}/`
  return {
    kind: 'directory',
    name: item.folder.name,
    sources: item.folder.entries.map(({ path, file }) => ({
      path: path.startsWith(prefix) ? path.slice(prefix.length) : path,
      file,
    })),
  }
}

function readTempFileId(result: unknown): string {
  const tempFileId =
    typeof result === 'object' && result !== null
      ? (result as { temp_file_id?: unknown }).temp_file_id
      : undefined
  if (typeof tempFileId !== 'string' || !tempFileId.trim()) {
    throw new Error(
      i18n.t('resources:processingTasks.errors.tempUploadMissingId'),
    )
  }
  return tempFileId
}

async function legacyTempUpload(
  item: UploadItem,
  onProgress?: (percent: number) => void,
): Promise<TransferResult> {
  let file = item.file
  if (item.folder) {
    if (getFolderSize(item.folder) > BROWSER_ZIP_MAX_BYTES) {
      throw new FolderTooLargeForZipError(item.folder.name)
    }
    file = await zipFolder(item.folder)
  }
  const result = await getOvResult<TempUploadResult>(
    postResourcesTempUpload({
      body: { file, telemetry: true },
      onUploadProgress: (event: { loaded: number; total?: number }) => {
        if (event.total) {
          onProgress?.(Math.round((event.loaded / event.total) * 100))
        }
      },
    }),
  )
  return { tempFileId: readTempFileId(result), sourceName: file.name }
}

/**
 * Upload one selected file or folder and return its temp_file_id.
 *
 * Uses a chunked session (folders are sent file by file, never zipped), resumes
 * it once if parts keep failing, and falls back to the single-request upload
 * (zipping folders) when the server has no chunked uploads.
 */
export async function transferUpload(
  item: UploadItem,
  onProgress?: (percent: number) => void,
): Promise<TransferResult> {
  const options: ChunkedUploadOptions = {
    ...sessionOptions(item),
    onProgress: (sent, total) =>
      onProgress?.(total ? Math.round((sent / total) * 100) : 100),
  }
  try {
    return {
      tempFileId: await uploadSession(options),
      sourceName: options.name,
    }
  } catch (error) {
    if (error instanceof UploadSessionError) {
      return {
        tempFileId: await resumeUploadSession(error.uploadId, options),
        sourceName: options.name,
      }
    }
    if (!(error instanceof SessionsUnavailableError)) throw error
  }
  return legacyTempUpload(item, onProgress)
}
