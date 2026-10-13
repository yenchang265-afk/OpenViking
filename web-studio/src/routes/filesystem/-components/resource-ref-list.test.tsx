// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '#/i18n'

import { ResourceRefList } from './resource-ref-list'

describe('ResourceRefList', () => {
  let previousLanguage: string

  beforeEach(async () => {
    previousLanguage = i18n.language
    await i18n.changeLanguage('zh-TW')
  })

  afterEach(async () => {
    cleanup()
    await i18n.changeLanguage(previousLanguage)
  })

  it('translates fixed terminal ref tags and keeps other meta verbatim', () => {
    render(
      <ResourceRefList
        refs={[
          { label: 'a', meta: 'tool result', uri: 'viking://session/s/a' },
          { label: 'b', meta: 'session', uri: 'viking://session/b' },
          { label: 'c', meta: 'L0 · 0.82', uri: 'viking://resources/c' },
          { label: 'd', meta: 'constructor', uri: 'viking://resources/d' },
        ]}
        onOpenResource={vi.fn()}
      />,
    )

    expect(screen.getByText('工具結果')).not.toBeNull()
    expect(screen.getByText('會話')).not.toBeNull()
    expect(screen.getByText('L0 · 0.82')).not.toBeNull()
    expect(screen.getByText('constructor')).not.toBeNull()
  })
})
