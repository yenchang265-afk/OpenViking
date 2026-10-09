// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import i18n from '#/i18n'

import { AdditionalResourceOptions } from './additional-resource-options'

afterEach(() => {
  cleanup()
})

describe('AdditionalResourceOptions', () => {
  it('labels the default preserve-structure mode with its translation', () => {
    render(
      <AdditionalResourceOptions
        disabled={false}
        isRemote={false}
        onChange={vi.fn()}
        t={i18n.getFixedT('en', 'addResource')}
        value={{
          parseMode: 'default',
          processingMode: 'semantic_and_vectors',
          sourceName: '',
          tagMode: 'replace',
          tags: '',
          timeout: '',
          wait: false,
        }}
      />,
    )

    expect(
      screen.getAllByText(
        i18n.getFixedT('en', 'addResource')('preserveStructure.serverDefault'),
      ).length,
    ).toBeGreaterThan(0)
    expect(screen.queryByText(/preserveStructure\./)).toBeNull()
  })
})
