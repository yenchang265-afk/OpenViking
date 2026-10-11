const trimSlash = (uri: string) => uri.replace(/\/+$/, '')

/** `viking://agent/skills/<name>` or `viking://user/<id>/skills/<name>`. */
export function isSkillRootUri(uri: string): boolean {
  return /^viking:\/\/(?:agent|user\/[^/]+)\/skills\/[^/]+$/.test(
    trimSlash(uri),
  )
}

/** Any directory below the `viking://` root can be a compile source. */
export function isCompileSourceUri(uri: string): boolean {
  return /^viking:\/\/[^/]+/.test(uri)
}

/**
 * Default output for compiling `sourceUri`: a sibling inside a resources
 * tree, otherwise a new directory under `viking://resources`.
 */
export function suggestCompileTarget(
  sourceUri: string,
  skillName: string,
): string {
  const base = trimSlash(sourceUri)
  if (/^viking:\/\/(?:user\/[^/]+\/)?resources\/.+/.test(base))
    return `${base}-${skillName}`
  const name = base.split('/').pop() || 'compiled'
  return `viking://resources/${name}-${skillName}`
}
