import { describe, expect, it } from 'vitest'

import { compileErrorKey } from './errors'

describe('compileErrorKey', () => {
  it('names an agent that produced no usable output', () => {
    expect(
      compileErrorKey({ code: 'AGENT_OUTPUT_INVALID', message: 'no files' }),
    ).toBe('errors.agentOutput')
  })

  it('falls back to a generic message for unknown codes', () => {
    expect(compileErrorKey({ code: 'SOMETHING_NEW' })).toBe('errors.generic')
    expect(compileErrorKey('boom')).toBe('errors.generic')
  })
})
