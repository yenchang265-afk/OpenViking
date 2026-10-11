import ignore from 'ignore'

import type { FolderGroup } from './folder-upload'

/**
 * Folder filters shared with the CLI (`ov add-resource --ignore-dirs/--include
 * /--exclude`) and the server's directory scan, which applies the same rules
 * after upload. Applying them before upload keeps the count checked against
 * the upload limits equal to what the server will keep.
 */
export type FolderFilters = {
  ignoreDirs: string
  include: string
  exclude: string
}

/**
 * A dropped folder with its .gitignore already applied. That verdict never
 * depends on the folder options, so it runs once per drop; option changes only
 * re-run the cheap ignore dirs / include / exclude checks.
 */
export type FolderSource = FolderGroup

function parsePatterns(value: string): string[] {
  return value
    .split(',')
    .map((pattern) => pattern.trim())
    .filter(Boolean)
}

function dirOf(path: string): string {
  const slash = path.lastIndexOf('/')
  return slash < 0 ? '' : path.slice(0, slash)
}

function baseName(path: string): string {
  return path.slice(path.lastIndexOf('/') + 1)
}

/** "repo/web/a.md" -> "web/a.md", so no rule ever matches the picked folder. */
function innerPath(folder: FolderGroup, path: string): string {
  return path.slice(folder.name.length + 1)
}

/**
 * Port of `_transform_gitignore_line` (openviking/parse/gitignore.py): make a
 * nested .gitignore line root-relative so one spec serves the whole folder.
 */
export function transformGitignoreLine(line: string, baseRel: string): string {
  if (!line || line.startsWith('#') || !baseRel) return line
  const negated = line.startsWith('!')
  const pattern = negated ? line.slice(1) : line
  let scoped: string
  if (pattern.startsWith('/')) {
    const anchored = pattern.replace(/^\/+/, '')
    scoped = anchored ? `${baseRel}/${anchored}` : baseRel
  } else if (pattern.includes('/')) {
    scoped = `${baseRel}/${pattern}`
  } else {
    scoped = pattern ? `${baseRel}/**/${pattern}` : baseRel
  }
  return negated ? `!${scoped}` : scoped
}

/** Read the folder's .gitignore files and drop what they ignore. */
export async function loadFolderSource(
  folder: FolderGroup,
): Promise<FolderSource> {
  const files = [...(folder.ignoreFiles ?? [])].sort(
    (a, b) => a.path.split('/').length - b.path.split('/').length,
  )
  const gitignoreRules: string[] = []
  for (const ignoreFile of files) {
    try {
      const baseRel = dirOf(innerPath(folder, ignoreFile.path))
      const lines = (await ignoreFile.file.text()).split(/\r?\n/)
      gitignoreRules.push(
        ...lines.map((line) => transformGitignoreLine(line, baseRel)),
      )
    } catch {
      // An unreadable .gitignore only means fewer files are skipped.
    }
  }
  const gitignore = ignore().add(gitignoreRules)
  const entries = folder.entries.filter(
    (entry) => !gitignore.ignores(innerPath(folder, entry.path)),
  )
  return {
    name: folder.name,
    entries,
    skippedCount: folder.skippedCount + folder.entries.length - entries.length,
  }
}

/** Python `fnmatch` (case-sensitive, as on the server): `*`, `?`, `[seq]`, `[!seq]`. */
function fnmatchToRegExp(pattern: string): RegExp {
  let source = ''
  for (let i = 0; i < pattern.length; i += 1) {
    const char = pattern[i]
    if (char === '*') {
      source += '.*'
    } else if (char === '?') {
      source += '.'
    } else if (char === '[') {
      const end = pattern.indexOf(']', i + 2)
      if (end < 0) {
        source += '\\['
        continue
      }
      let set = pattern.slice(i + 1, end).replace(/\\/g, '\\\\')
      if (set.startsWith('!')) set = `^${set.slice(1)}`
      else if (set.startsWith('^')) set = `\\${set}`
      source += `[${set}]`
      i = end
    } else {
      source += char.replace(/[.+^${}()|\\/]/g, '\\$&')
    }
  }
  return new RegExp(`^${source}$`, 's')
}

/** `ignore_dirs` as the CLI and server read it: a name anywhere, or a path from the root. */
function isInIgnoredDir(relPath: string, ignoreDirs: string[]): boolean {
  const dirs = relPath.split('/').slice(0, -1)
  return ignoreDirs.some((raw) => {
    const entry = raw.replace(/\\/g, '/')
    if (!entry.includes('/')) return dirs.includes(entry)
    const prefix = entry.replace(/\/+$/, '').replace(/^[./]+/, '')
    return Boolean(prefix) && relPath.startsWith(`${prefix}/`)
  })
}

type ExcludeRule = { prefix: string } | { glob: RegExp }

/** Trailing '/' = path prefix (e.g. "drafts/"), else a glob on the file name. */
function parseExclude(value: string): ExcludeRule[] {
  return parsePatterns(value).map((pattern) =>
    pattern.endsWith('/')
      ? { prefix: pattern.replace(/\/+$/, '').replace(/\\/g, '/') }
      : { glob: fnmatchToRegExp(pattern) },
  )
}

function isExcluded(
  relPath: string,
  name: string,
  rules: ExcludeRule[],
): boolean {
  return rules.some((rule) =>
    'prefix' in rule
      ? relPath === rule.prefix || relPath.startsWith(`${rule.prefix}/`)
      : rule.glob.test(name),
  )
}

/**
 * Keep the files the server's directory scan would keep: not in an
 * ignore_dirs folder, matching include, not matching exclude. The .gitignore
 * part already ran in loadFolderSource.
 */
export function filterFolder(
  source: FolderSource,
  filters: FolderFilters,
): FolderGroup {
  const ignoreDirs = parsePatterns(filters.ignoreDirs)
  const include = parsePatterns(filters.include).map(fnmatchToRegExp)
  const exclude = parseExclude(filters.exclude)

  const entries = source.entries.filter((entry) => {
    const relPath = innerPath(source, entry.path)
    const name = baseName(relPath)
    if (isInIgnoredDir(relPath, ignoreDirs)) return false
    if (include.length && !include.some((pattern) => pattern.test(name))) {
      return false
    }
    return !isExcluded(relPath, name, exclude)
  })
  return {
    name: source.name,
    entries,
    skippedCount: source.skippedCount + source.entries.length - entries.length,
  }
}
