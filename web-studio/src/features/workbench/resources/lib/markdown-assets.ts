const vikingPrefix = 'viking://'

function dirnameVikingUri(fileUri: string): string {
  if (fileUri === vikingPrefix) {
    return vikingPrefix
  }

  const trimmed = fileUri.endsWith('/') ? fileUri.slice(0, -1) : fileUri
  const idx = trimmed.lastIndexOf('/')
  if (idx < vikingPrefix.length) {
    return vikingPrefix
  }
  return `${trimmed.slice(0, idx + 1)}`
}

/** Resolve a decoded file path without interpreting literal # or percent signs. */
function resolveRelativeVikingUri(
  baseFileUri: string,
  rawPath: string,
): string {
  const baseDir = dirnameVikingUri(baseFileUri)
  const baseBody = baseDir.slice(vikingPrefix.length, -1)

  const baseSegments = baseBody ? baseBody.split('/').filter(Boolean) : []
  const relativeSegments = rawPath.split('/').filter(Boolean)

  const merged = [...baseSegments]
  for (const segment of relativeSegments) {
    if (segment === '.') {
      continue
    }
    if (segment === '..') {
      merged.pop()
      continue
    }
    merged.push(segment)
  }

  const resolved = `${vikingPrefix}${merged.join('/')}`
  return resolved
}

export type MarkdownAssetTarget =
  | { kind: 'external'; value: string }
  | { kind: 'raw'; value: string }
  | { kind: 'viking'; value: string }

export function safeDecodeUri(value: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

export function resolveMarkdownAssetTarget(
  assetPath: string,
  fileUri: string,
): MarkdownAssetTarget {
  const trimmed = assetPath.trim()
  if (!trimmed || trimmed.startsWith('#')) {
    return { kind: 'raw', value: trimmed }
  }

  if (/^(https?:|data:|blob:|mailto:|tel:)/i.test(trimmed)) {
    return { kind: 'external', value: trimmed }
  }

  // Split URL components before decoding; %23 is literal filename data.
  const decoded = safeDecodeUri(trimmed.split(/[?#]/, 1)[0])

  const vikingUri = decoded.startsWith(vikingPrefix)
    ? decoded
    : resolveRelativeVikingUri(fileUri, decoded)
  return { kind: 'viking', value: vikingUri }
}
