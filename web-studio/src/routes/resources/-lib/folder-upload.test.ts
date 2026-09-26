import { describe, expect, it } from 'vitest'

import { groupFolderFiles, getRelativePath } from './folder-upload'

function withPath(file: File, path: string): File {
  Object.defineProperty(file, 'path', { value: path })
  return file
}

describe('getRelativePath', () => {
  it('normalizes dropzone and directory-input paths', () => {
    expect(getRelativePath(withPath(new File([''], 'a.md'), './a.md'))).toBe(
      'a.md',
    )
    expect(
      getRelativePath(withPath(new File([''], 'a.md'), '/docs/a.md')),
    ).toBe('docs/a.md')
    expect(getRelativePath(withPath(new File([''], 'a.md'), 'docs/a.md'))).toBe(
      'docs/a.md',
    )
    expect(getRelativePath(new File([''], 'plain.md'))).toBe('plain.md')
  })
})

describe('groupFolderFiles', () => {
  it('separates loose files from files grouped by top-level folder', () => {
    const loose = withPath(new File([''], 'loose.md'), './loose.md')
    const docA = withPath(new File([''], 'a.md'), '/docs/a.md')
    const docB = withPath(new File([''], 'b.md'), '/docs/sub/b.md')
    const other = withPath(new File([''], 'c.md'), '/other/c.md')

    const result = groupFolderFiles([loose, docA, docB, other])

    expect(result.looseFiles).toEqual([loose])
    expect(result.folders.map((folder) => folder.name)).toEqual([
      'docs',
      'other',
    ])
    expect(result.folders[0].entries.map((entry) => entry.path)).toEqual([
      'docs/a.md',
      'docs/sub/b.md',
    ])
  })

  it('skips hidden paths and blocked extensions inside folders', () => {
    const kept = withPath(new File([''], 'a.md'), '/docs/a.md')
    const git = withPath(new File([''], 'HEAD'), '/docs/.git/HEAD')
    const dsStore = withPath(new File([''], '.DS_Store'), '/docs/.DS_Store')
    const binary = withPath(new File([''], 'x.exe'), '/docs/x.exe')

    const result = groupFolderFiles([kept, git, dsStore, binary])

    expect(result.folders[0].entries.map((entry) => entry.path)).toEqual([
      'docs/a.md',
    ])
    expect(result.folders[0].skippedCount).toBe(3)
  })
})
