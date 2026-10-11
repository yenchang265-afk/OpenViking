import { describe, expect, it } from 'vitest'

import { applyIgnoreRules } from './folder-ignore'
import type { FolderEntry, FolderGroup } from './folder-upload'

function entry(path: string, content = ''): FolderEntry {
  return { path, file: new File([content], path.split('/').pop() ?? path) }
}

function folder(
  paths: string[],
  ignoreFiles: FolderEntry[] = [],
  skippedCount = 0,
): FolderGroup {
  return {
    name: 'repo',
    entries: paths.map((path) => entry(path)),
    ignoreFiles,
    skippedCount,
  }
}

function kept(group: FolderGroup): string[] {
  return group.entries.map((item) => item.path)
}

describe('applyIgnoreRules', () => {
  it('drops what the root .gitignore ignores and counts it as skipped', async () => {
    const result = await applyIgnoreRules(
      folder(
        [
          'repo/src/a.md',
          'repo/target/debug/app',
          'repo/dist/app.js',
          'repo/notes.log',
        ],
        [entry('repo/.gitignore', 'target/\n/dist\n*.log\n')],
        1,
      ),
    )

    expect(kept(result)).toEqual(['repo/src/a.md'])
    expect(result.skippedCount).toBe(4)
  })

  it('applies a nested .gitignore relative to its own folder', async () => {
    const result = await applyIgnoreRules(
      folder(
        ['repo/web/build/x.js', 'repo/build/keep.md', 'repo/web/src/a.ts'],
        [entry('repo/web/.gitignore', '/build\n')],
      ),
    )

    expect(kept(result)).toEqual(['repo/build/keep.md', 'repo/web/src/a.ts'])
  })

  it('lets a deeper .gitignore re-include what a parent ignores', async () => {
    const result = await applyIgnoreRules(
      folder(
        ['repo/docs/a.md', 'repo/docs/keep.md'],
        [
          entry('repo/.gitignore', 'docs/*.md\n'),
          entry('repo/docs/.gitignore', '!keep.md\n'),
        ],
      ),
    )

    expect(kept(result)).toEqual(['repo/docs/keep.md'])
  })

  it('always skips node_modules, even without a .gitignore', async () => {
    const result = await applyIgnoreRules(
      folder([
        'repo/a.md',
        'repo/node_modules/pkg/index.js',
        'repo/web/node_modules/x.js',
      ]),
    )

    expect(kept(result)).toEqual(['repo/a.md'])
    expect(result.skippedCount).toBe(2)
  })

  it('keeps a folder whose name matches a rule when it is the picked folder', async () => {
    const group = {
      ...folder([]),
      name: 'node_modules',
      entries: [entry('node_modules/readme.md')],
    }

    expect(kept(await applyIgnoreRules(group))).toEqual([
      'node_modules/readme.md',
    ])
  })
})
