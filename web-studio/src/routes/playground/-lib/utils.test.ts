// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from 'vitest'

import {
  canDeleteResourceUri,
  createIdentityStorageKey,
  readPlaygroundExpandedUris,
  writePlaygroundExpandedUris,
} from './utils'

beforeEach(() => {
  localStorage.clear()
})

describe('createIdentityStorageKey', () => {
  it('isolates persisted Playground state by identity scope', () => {
    const baseKey = 'openviking.playground.terminalEntryHistory'

    expect(createIdentityStorageKey(baseKey, 'account-a\u0000alice')).not.toBe(
      createIdentityStorageKey(baseKey, 'account-b\u0000bob'),
    )
  })

  it('keeps the storage key browser-safe', () => {
    const key = createIdentityStorageKey(
      'openviking.playground.agentSessions',
      'http://localhost:1933\u0000api_key\u0000account-a\u0000alice',
    )

    expect(key).not.toContain('\u0000')
  })
})

describe('Playground expanded directory persistence', () => {
  it('restores normalized expanded URIs for the same identity', () => {
    writePlaygroundExpandedUris('account-a\u0000alice', [
      'viking://user/default',
      'viking://resources/',
    ])

    expect(readPlaygroundExpandedUris('account-a\u0000alice')).toEqual([
      'viking://user/default/',
      'viking://resources/',
    ])
    expect(readPlaygroundExpandedUris('account-a\u0000bob')).toEqual([])
  })
})

describe('canDeleteResourceUri', () => {
  it.each(['viking://', 'viking://resources/', 'viking://user'])(
    'protects the root and top-level namespace %s',
    (uri) => {
      expect(canDeleteResourceUri(uri)).toBe(false)
    },
  )

  it.each([
    'viking://resources/demo/',
    'viking://resources/demo.md',
    'viking://user/default/memories/first.md',
  ])('allows deleting nested resource %s', (uri) => {
    expect(canDeleteResourceUri(uri)).toBe(true)
  })
})
