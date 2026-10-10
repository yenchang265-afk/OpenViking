import { describe, expect, it } from 'vitest'

import {
  canCreateInUri,
  canReindexUri,
  childEntryUri,
  isUriWithin,
  remapExpandedUris,
  remapUri,
  renamedEntryUri,
  validateEntryName,
} from './tree-actions'

describe('validateEntryName', () => {
  it('accepts ordinary names', () => {
    expect(validateEntryName('notes', 'folder')).toBeNull()
    expect(validateEntryName('notes.md', 'file')).toBeNull()
    expect(validateEntryName('config.YAML', 'file')).toBeNull()
  })

  it('rejects blank names', () => {
    expect(validateEntryName('   ', 'folder')).toBe('required')
  })

  it.each(['a/b', 'a\\b', 'tab\tname'])('rejects %j', (name) => {
    expect(validateEntryName(name, 'folder')).toBe('invalidChars')
  })

  it.each(['.', '..'])('rejects reserved name %j', (name) => {
    expect(validateEntryName(name, 'folder')).toBe('reserved')
  })

  it('rejects names longer than 255 characters', () => {
    expect(validateEntryName('a'.repeat(256), 'folder')).toBe('tooLong')
  })

  it('requires a writable text extension for new files', () => {
    expect(validateEntryName('notes', 'file')).toBe('extension')
    expect(validateEntryName('image.png', 'file')).toBe('extension')
  })

  it('lets renamed entries keep any extension', () => {
    expect(validateEntryName('image.png', 'rename')).toBeNull()
  })
})

describe('childEntryUri', () => {
  it('joins a trimmed name under a directory', () => {
    expect(childEntryUri('viking://resources', ' docs ')).toBe(
      'viking://resources/docs',
    )
    expect(childEntryUri('viking://resources/', 'a.md')).toBe(
      'viking://resources/a.md',
    )
  })
})

describe('renamedEntryUri', () => {
  it('keeps the parent and replaces the last segment', () => {
    expect(renamedEntryUri('viking://resources/a/old.md', 'new.md')).toBe(
      'viking://resources/a/new.md',
    )
    expect(renamedEntryUri('viking://resources/a/', 'b')).toBe(
      'viking://resources/b',
    )
  })
})

describe('isUriWithin', () => {
  it('matches the uri itself and its descendants only', () => {
    expect(isUriWithin('viking://resources/a/', 'viking://resources/a')).toBe(
      true,
    )
    expect(
      isUriWithin('viking://resources/a/x.md', 'viking://resources/a'),
    ).toBe(true)
    expect(isUriWithin('viking://resources/ab', 'viking://resources/a')).toBe(
      false,
    )
  })
})

describe('remapUri', () => {
  it('rewrites the moved prefix and preserves trailing slashes', () => {
    expect(
      remapUri(
        'viking://resources/a/x/',
        'viking://resources/a',
        'viking://resources/b',
      ),
    ).toBe('viking://resources/b/x/')
    expect(
      remapUri(
        'viking://resources/a',
        'viking://resources/a/',
        'viking://resources/b',
      ),
    ).toBe('viking://resources/b')
  })

  it('leaves unrelated uris alone', () => {
    expect(
      remapUri(
        'viking://resources/ab/',
        'viking://resources/a',
        'viking://resources/b',
      ),
    ).toBe('viking://resources/ab/')
  })
})

describe('remapExpandedUris', () => {
  it('returns a new set with moved directories renamed', () => {
    const current = new Set([
      'viking://',
      'viking://resources/',
      'viking://resources/a/',
      'viking://resources/a/x/',
    ])
    const next = remapExpandedUris(
      current,
      'viking://resources/a',
      'viking://resources/b',
    )

    expect(next).not.toBe(current)
    expect([...next]).toEqual([
      'viking://',
      'viking://resources/',
      'viking://resources/b/',
      'viking://resources/b/x/',
    ])
    expect(current.has('viking://resources/a/')).toBe(true)
  })
})

describe('canCreateInUri', () => {
  it('blocks the virtual root but allows namespaces and below', () => {
    expect(canCreateInUri('viking://')).toBe(false)
    expect(canCreateInUri('viking://resources')).toBe(true)
    expect(canCreateInUri('viking://resources/a/')).toBe(true)
  })
})

describe('canReindexUri', () => {
  it('allows resource, user and agent entries', () => {
    expect(canReindexUri('viking://resources/')).toBe(true)
    expect(canReindexUri('viking://resources/docs/guide.md')).toBe(true)
    expect(canReindexUri('viking://user/')).toBe(true)
    expect(canReindexUri('viking://user/alice/memories/')).toBe(true)
    expect(canReindexUri('viking://agent/skills/')).toBe(true)
  })

  it('blocks the root, the bare agent namespace and sessions', () => {
    expect(canReindexUri('viking://')).toBe(false)
    expect(canReindexUri('viking://agent/')).toBe(false)
    expect(canReindexUri('viking://session/s1/')).toBe(false)
    expect(canReindexUri('viking://user/alice/sessions/')).toBe(false)
    expect(canReindexUri('viking://user/alice/sessions/s1/a.json')).toBe(false)
  })
})
