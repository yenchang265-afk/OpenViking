import {
  normalizeDirUri,
  normalizeFileUri,
  parentUri,
} from '#/routes/resources/-lib/normalize'

import { ROOT_URI } from './constants'

export type EntryNameMode = 'file' | 'folder' | 'rename'

export type EntryNameError =
  | 'extension'
  | 'invalidChars'
  | 'required'
  | 'reserved'
  | 'tooLong'

// Mirrors the server's content-write create allowlist
// (openviking/storage/content_write.py `_CREATE_ALLOWED_EXTENSIONS`).
export const CREATABLE_FILE_EXTENSIONS = [
  '.md',
  '.txt',
  '.json',
  '.yaml',
  '.yml',
  '.toml',
  '.py',
  '.js',
  '.ts',
] as const

const MAX_ENTRY_NAME_LENGTH = 255
// Path separators and control characters can never be part of one segment.
// eslint-disable-next-line no-control-regex
const INVALID_NAME_CHARS = /[/\\\u0000-\u001f\u007f]/

export function validateEntryName(
  rawName: string,
  mode: EntryNameMode,
): EntryNameError | null {
  const name = rawName.trim()
  if (!name) return 'required'
  if (INVALID_NAME_CHARS.test(name)) return 'invalidChars'
  if (name === '.' || name === '..') return 'reserved'
  if (name.length > MAX_ENTRY_NAME_LENGTH) return 'tooLong'
  if (mode === 'file' && !hasCreatableExtension(name)) return 'extension'
  return null
}

function hasCreatableExtension(name: string): boolean {
  const lower = name.toLowerCase()
  return CREATABLE_FILE_EXTENSIONS.some(
    (extension) => lower.endsWith(extension) && lower.length > extension.length,
  )
}

/** URI of a new entry named `name` inside `dirUri`, without a trailing slash. */
export function childEntryUri(dirUri: string, name: string): string {
  return `${normalizeDirUri(dirUri)}${name.trim()}`
}

/** URI `uri` would have after renaming its last segment to `name`. */
export function renamedEntryUri(uri: string, name: string): string {
  return childEntryUri(parentUri(uri), name)
}

export function isUriWithin(uri: string, ancestorUri: string): boolean {
  const target = normalizeFileUri(uri)
  const ancestor = normalizeFileUri(ancestorUri)
  return target === ancestor || target.startsWith(`${ancestor}/`)
}

/** Rewrites `uri` when it is `fromUri` or lives below it; otherwise unchanged. */
export function remapUri(uri: string, fromUri: string, toUri: string): string {
  if (!isUriWithin(uri, fromUri)) return uri
  const from = normalizeFileUri(fromUri)
  const to = normalizeFileUri(toUri)
  return `${to}${normalizeFileUri(uri).slice(from.length)}${
    uri.endsWith('/') ? '/' : ''
  }`
}

export function remapExpandedUris(
  expanded: ReadonlySet<string>,
  fromUri: string,
  toUri: string,
): Set<string> {
  return new Set([...expanded].map((uri) => remapUri(uri, fromUri, toUri)))
}

/** The virtual root only lists namespaces; entries live one level below it. */
export function canCreateInUri(uri: string): boolean {
  return normalizeDirUri(uri) !== ROOT_URI
}
