import { describe, expect, it } from 'vitest'

import {
  filterFolder,
  loadFolderSource,
  transformGitignoreLine,
} from './folder-filter'
import type { FolderFilters } from './folder-filter'
import type { FolderEntry, FolderGroup } from './folder-upload'

const NO_FILTERS: FolderFilters = { ignoreDirs: '', include: '', exclude: '' }

function entry(path: string, content = ''): FolderEntry {
  return { path, file: new File([content], path.split('/').pop() ?? path) }
}

async function keptPaths(
  paths: string[],
  gitignores: Record<string, string> = {},
  filters: Partial<FolderFilters> = {},
): Promise<string[]> {
  const group: FolderGroup = {
    name: 'repo',
    entries: paths.map((path) => entry(path)),
    ignoreFiles: Object.entries(gitignores).map(([path, content]) =>
      entry(path, content),
    ),
    skippedCount: 0,
  }
  const source = await loadFolderSource(group)
  return filterFolder(source, { ...NO_FILTERS, ...filters }).entries.map(
    (item) => item.path,
  )
}

describe('transformGitignoreLine (server parity)', () => {
  it('scopes nested patterns like openviking/parse/gitignore.py', () => {
    expect(transformGitignoreLine('*.log', '')).toBe('*.log')
    expect(transformGitignoreLine('*.log', 'web')).toBe('web/**/*.log')
    expect(transformGitignoreLine('/build', 'web')).toBe('web/build')
    expect(transformGitignoreLine('out/x', 'web')).toBe('web/out/x')
    expect(transformGitignoreLine('!keep.md', 'docs')).toBe('!docs/**/keep.md')
    expect(transformGitignoreLine('# note', 'web')).toBe('# note')
  })
})

describe('filterFolder', () => {
  it('keeps everything, node_modules included, when nothing excludes it', async () => {
    expect(
      await keptPaths(['repo/a.md', 'repo/node_modules/x/index.js']),
    ).toEqual(['repo/a.md', 'repo/node_modules/x/index.js'])
  })

  it('honours the root .gitignore', async () => {
    expect(
      await keptPaths(
        [
          'repo/src/a.md',
          'repo/target/debug/app',
          'repo/dist/app.js',
          'repo/x.log',
        ],
        { 'repo/.gitignore': 'target/\n/dist\n*.log\n' },
      ),
    ).toEqual(['repo/src/a.md'])
  })

  it('scopes a nested .gitignore to its folder', async () => {
    expect(
      await keptPaths(
        [
          'repo/web/build/x.js',
          'repo/build/keep.md',
          'repo/web/a.log',
          'repo/a.log',
        ],
        { 'repo/web/.gitignore': '/build\n*.log\n' },
      ),
    ).toEqual(['repo/build/keep.md', 'repo/a.log'])
  })

  it('lets a deeper negation re-include, but not inside an ignored folder', async () => {
    expect(
      await keptPaths(
        ['repo/docs/a.md', 'repo/docs/keep.md', 'repo/out/keep.md'],
        {
          'repo/.gitignore': 'docs/*.md\nout/\n',
          'repo/docs/.gitignore': '!keep.md\n',
          'repo/out/.gitignore': '!keep.md\n',
        },
      ),
    ).toEqual(['repo/docs/keep.md'])
  })

  it('skips ignore_dirs by name anywhere and by path from the root', async () => {
    expect(
      await keptPaths(
        [
          'repo/a.md',
          'repo/web/node_modules/x.js',
          'repo/storage/vectordb/y',
          'repo/vectordb/z.md',
        ],
        {},
        { ignoreDirs: 'node_modules, ./storage/vectordb' },
      ),
    ).toEqual(['repo/a.md', 'repo/vectordb/z.md'])
  })

  it('applies include as file-name globs', async () => {
    expect(
      await keptPaths(
        ['repo/a.md', 'repo/docs/b.pdf', 'repo/c.ts', 'repo/README'],
        {},
        { include: '*.md,*.pdf' },
      ),
    ).toEqual(['repo/a.md', 'repo/docs/b.pdf'])
  })

  it('applies exclude as name globs or path prefixes ending in /', async () => {
    expect(
      await keptPaths(
        ['repo/a.md', 'repo/a.tmp', 'repo/drafts/b.md', 'repo/draftsx/c.md'],
        {},
        { exclude: '*.tmp, drafts/' },
      ),
    ).toEqual(['repo/a.md', 'repo/draftsx/c.md'])
  })

  it('matches fnmatch character classes and is case-sensitive', async () => {
    expect(
      await keptPaths(
        ['repo/a1.md', 'repo/b2.md', 'repo/C3.MD'],
        {},
        { include: '[!b]?.md' },
      ),
    ).toEqual(['repo/a1.md'])
  })

  it('counts filtered files as skipped and never matches the picked folder', async () => {
    const group: FolderGroup = {
      name: 'build',
      entries: [entry('build/a.md'), entry('build/b.tmp')],
      ignoreFiles: [entry('build/.gitignore', 'build/\n')],
      skippedCount: 1,
    }

    const result = filterFolder(await loadFolderSource(group), {
      ...NO_FILTERS,
      exclude: '*.tmp',
    })

    expect(result.entries.map((item) => item.path)).toEqual(['build/a.md'])
    expect(result.skippedCount).toBe(2)
  })
})
