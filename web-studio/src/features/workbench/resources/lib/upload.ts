export const MAX_UPLOAD_FILES = 10

const BLOCKED_EXTENSIONS = new Set([
  '.pyc',
  '.pyo',
  '.pyd',
  '.so',
  '.dll',
  '.dylib',
  '.exe',
  '.bin',
  '.iso',
  '.img',
  '.db',
  '.sqlite',
  '.tar',
  '.gz',
  '.rar',
  '.7z',
  '.class',
  '.jar',
  '.war',
  '.ear',
  '.ico',
  '.wma',
  '.mid',
  '.midi',
])

/** Files up to this size are read to look for content; larger ones are left to the server. */
const EMPTY_CHECK_MAX_BYTES = 64 * 1024
// The server refuses a file that is empty or only ASCII whitespace (Python bytes.strip()).
const ASCII_WHITESPACE = new Set([0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x20])

/** Whether the server would refuse this file as having nothing to index. */
export async function isEmptyFile(file: File): Promise<boolean> {
  if (file.size === 0) return true
  if (file.size > EMPTY_CHECK_MAX_BYTES) return false
  const bytes = new Uint8Array(await file.arrayBuffer())
  return bytes.every((byte) => ASCII_WHITESPACE.has(byte))
}

const ERROR_CODE_PREFIX_RE = /^([A-Z][A-Z0-9_]{2,})\s*:\s*(.+)$/s
const ERROR_CODE_RE = /\b([A-Z][A-Z0-9_]{2,})\b/

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

export function isBlockedFile(name: string): boolean {
  const dot = name.lastIndexOf('.')
  if (dot <= 0) return false
  return BLOCKED_EXTENSIONS.has(name.slice(dot).toLowerCase())
}

export function parseUploadError(message: string): {
  errorCode: string | null
  errorMessage: string
} {
  const trimmed = message.trim()
  const prefixed = trimmed.match(ERROR_CODE_PREFIX_RE)
  if (prefixed) {
    return {
      errorCode: prefixed[1],
      errorMessage: prefixed[2],
    }
  }

  const matchedCode = trimmed.match(ERROR_CODE_RE)
  return {
    errorCode: matchedCode?.[1] ?? null,
    errorMessage: trimmed,
  }
}
