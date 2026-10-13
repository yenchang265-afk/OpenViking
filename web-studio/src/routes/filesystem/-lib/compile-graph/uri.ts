const SCHEME = 'viking://'

/** POSIX-style `..`/`.` resolution for the path part of a viking:// URI. */
export function normalizeVikingUri(uri: string): string {
  const path = uri.startsWith(SCHEME) ? uri.slice(SCHEME.length) : uri
  const parts: string[] = []
  for (const part of path.split('/')) {
    if (!part || part === '.') continue
    if (part === '..') parts.pop()
    else parts.push(part)
  }
  return SCHEME + parts.join('/')
}

export const trimSlash = (uri: string) => uri.replace(/\/+$/, '')

export function parentDir(uri: string): string {
  const trimmed = trimSlash(uri)
  return trimmed.slice(0, trimmed.lastIndexOf('/'))
}

export function baseName(uri: string): string {
  return trimSlash(uri).split('/').pop() ?? ''
}

/** Path of `uri` below `root`, without a leading slash. */
export function relativeTo(uri: string, root: string): string {
  const base = `${trimSlash(root)}/`
  return uri.startsWith(base) ? uri.slice(base.length) : baseName(uri)
}

/** Hidden files (`.abstract.md`, `.overview.md`, …) and hidden folders. */
export function isHiddenPath(relPath: string): boolean {
  return relPath.split('/').some((part) => part.startsWith('.'))
}
