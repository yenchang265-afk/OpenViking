import ignore from 'ignore'
import type { Ignore } from 'ignore'

import type { FolderGroup } from './folder-upload'

// Never worth indexing and the usual reason a picked repo exceeds the upload
// limits, so it is skipped even in folders without a .gitignore.
const BUILT_IN_RULES = 'node_modules/\n'

type Matcher = {
  /** Folder of the .gitignore, relative to the picked folder ('' = root). */
  dir: string
  rules: Ignore
}

function dirOf(path: string): string {
  const slash = path.lastIndexOf('/')
  return slash < 0 ? '' : path.slice(0, slash)
}

function depth(dir: string): number {
  return dir ? dir.split('/').length : 0
}

/** "repo/web/a.md" -> "web/a.md", so a rule never matches the picked folder. */
function innerPath(folder: FolderGroup, path: string): string {
  return path.slice(folder.name.length + 1)
}

async function loadMatchers(folder: FolderGroup): Promise<Matcher[]> {
  const matchers: Matcher[] = [{ dir: '', rules: ignore().add(BUILT_IN_RULES) }]
  for (const ignoreFile of folder.ignoreFiles ?? []) {
    try {
      matchers.push({
        dir: dirOf(innerPath(folder, ignoreFile.path)),
        rules: ignore().add(await ignoreFile.file.text()),
      })
    } catch {
      // An unreadable .gitignore only means fewer files are skipped.
    }
  }
  // Shallow first, so deeper rules decide last, as in git.
  return matchers.sort((a, b) => depth(a.dir) - depth(b.dir))
}

function isIgnored(path: string, matchers: Matcher[]): boolean {
  let ignored = false
  for (const { dir, rules } of matchers) {
    if (dir && !path.startsWith(`${dir}/`)) continue
    const result = rules.test(dir ? path.slice(dir.length + 1) : path)
    if (result.ignored) ignored = true
    else if (result.unignored) ignored = false
  }
  return ignored
}

/**
 * Drop entries the folder's own .gitignore files (plus node_modules) exclude,
 * counting them as skipped.
 */
export async function applyIgnoreRules(
  folder: FolderGroup,
): Promise<FolderGroup> {
  const matchers = await loadMatchers(folder)
  const entries = folder.entries.filter(
    (entry) => !isIgnored(innerPath(folder, entry.path), matchers),
  )
  return {
    ...folder,
    entries,
    skippedCount: folder.skippedCount + folder.entries.length - entries.length,
  }
}
