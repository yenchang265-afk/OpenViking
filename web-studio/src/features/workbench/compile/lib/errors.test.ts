import { compileErrorKey } from '#/features/workbench/compile/lib/errors'
import { OvClientError } from '#/shared/api/ov-client/index'
import { describe, expect, it } from 'vitest'

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

  it.each([
    ['COMPILE_SCHEDULER_DISABLED', 'schedule.schedulerDisabled'],
    ['COMPILE_CREDENTIAL_INVALID', 'schedule.credentialInvalid'],
    ['COMPILE_CREDENTIAL_KEY_UNAVAILABLE', 'schedule.credentialKeyUnavailable'],
  ])('explains why a schedule save failed: %s', (reason, expected) => {
    expect(
      compileErrorKey(
        new OvClientError({
          code: 'FAILED_PRECONDITION',
          message: 'Schedule save rejected',
          details: { reason },
        }),
      ),
    ).toBe(expected)
  })
})
