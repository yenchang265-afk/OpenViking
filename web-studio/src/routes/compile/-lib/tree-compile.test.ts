import { describe, expect, it } from 'vitest'
import {
  isCompileSourceUri,
  isSkillRootUri,
  suggestCompileTarget,
} from './tree-compile'

describe('tree compile helpers', () => {
  it('recognises skill folders', () => {
    expect(isSkillRootUri('viking://agent/skills/llm-wiki/')).toBe(true)
    expect(isSkillRootUri('viking://user/alice/skills/mine')).toBe(true)
    expect(isSkillRootUri('viking://agent/skills')).toBe(false)
    expect(isSkillRootUri('viking://agent/skills/llm-wiki/refs')).toBe(false)
    expect(isSkillRootUri('viking://resources/skills/x')).toBe(false)
  })

  it('accepts any directory below the root as a source', () => {
    expect(isCompileSourceUri('viking://resources/')).toBe(true)
    expect(isCompileSourceUri('viking://')).toBe(false)
  })

  it('suggests a sibling output inside resources, else one under resources', () => {
    expect(
      suggestCompileTarget('viking://resources/research/', 'llm-wiki'),
    ).toBe('viking://resources/research-llm-wiki')
    expect(
      suggestCompileTarget(
        'viking://user/alice/resources/notes',
        'daily-report',
      ),
    ).toBe('viking://user/alice/resources/notes-daily-report')
    expect(suggestCompileTarget('viking://resources', 'llm-wiki')).toBe(
      'viking://resources/resources-llm-wiki',
    )
    expect(
      suggestCompileTarget('viking://user/alice/memories/', 'knowledge-graph'),
    ).toBe('viking://resources/memories-knowledge-graph')
  })
})
