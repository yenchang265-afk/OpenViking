import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  BUILTIN_COMPILE_SKILLS,
  ensureBuiltinSkill,
  installMissingBuiltinSkills,
  isCompileSourceUri,
  isSkillRootUri,
  missingBuiltinSkills,
  parseSkillFrontmatter,
  suggestCompileTarget,
} from './builtin-skills'

const mocks = vi.hoisted(() => ({
  fetchCompileSkills: vi.fn(),
  post: vi.fn(),
}))
vi.mock('./api', () => ({ fetchCompileSkills: mocks.fetchCompileSkills }))
vi.mock('#/lib/ov-client', () => ({
  getOvResult: (promise: Promise<unknown>) => promise,
  ovClient: { client: { post: mocks.post } },
}))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.post.mockResolvedValue({})
})

describe('bundled compile skills', () => {
  it('ships every skill under examples/compile/ov-compile-skills', () => {
    expect(BUILTIN_COMPILE_SKILLS.map((skill) => skill.name)).toEqual([
      'daily-report',
      'knowledge-distillation',
      'knowledge-graph',
      'llm-wiki',
      'ov-session-report',
    ])
    for (const skill of BUILTIN_COMPILE_SKILLS) {
      expect(skill.uri).toBe(`viking://agent/skills/${skill.name}`)
      expect(skill.description).not.toBe('')
      expect(skill.content.startsWith('---')).toBe(true)
    }
  })

  it('reads name and description from frontmatter', () => {
    expect(
      parseSkillFrontmatter(
        '---\nname: "wiki"\ndescription: Builds a wiki.\n---\n# Body\nname: no',
      ),
    ).toEqual({ name: 'wiki', description: 'Builds a wiki.' })
    expect(parseSkillFrontmatter('# No frontmatter')).toEqual({
      name: '',
      description: '',
    })
  })

  it('lists only the built-ins that are not installed', () => {
    const missing = missingBuiltinSkills([
      { uri: 'viking://agent/skills/llm-wiki/' },
      { uri: 'viking://user/alice/skills/daily-report' },
    ])
    expect(missing.map((skill) => skill.name)).toEqual([
      'daily-report',
      'knowledge-distillation',
      'knowledge-graph',
      'ov-session-report',
    ])
  })
})

describe('ensureBuiltinSkill', () => {
  const wiki = BUILTIN_COMPILE_SKILLS.find(
    (skill) => skill.name === 'llm-wiki',
  )!

  it('installs a missing skill into the shared skills root', async () => {
    mocks.fetchCompileSkills.mockResolvedValue([])
    await expect(ensureBuiltinSkill(wiki)).resolves.toBe(true)
    expect(mocks.post).toHaveBeenCalledWith({
      url: '/api/v1/skills',
      body: expect.objectContaining({
        data: wiki.content,
        target_uri: 'viking://agent/skills',
      }),
    })
  })

  it('leaves an installed skill untouched', async () => {
    mocks.fetchCompileSkills.mockResolvedValue([{ uri: wiki.uri }])
    await expect(ensureBuiltinSkill(wiki)).resolves.toBe(false)
    expect(mocks.post).not.toHaveBeenCalled()
  })
})

describe('concurrent installs', () => {
  it('shares one check-and-install between simultaneous requests', async () => {
    const wiki = BUILTIN_COMPILE_SKILLS.find((s) => s.name === 'llm-wiki')!
    mocks.fetchCompileSkills.mockResolvedValue([])
    const results = await Promise.all([
      ensureBuiltinSkill(wiki),
      ensureBuiltinSkill(wiki),
    ])
    expect(results).toEqual([true, true])
    expect(mocks.post).toHaveBeenCalledTimes(1)
  })

  it('installs only what is missing at click time and reports failures', async () => {
    const installed = BUILTIN_COMPILE_SKILLS.filter(
      (s) => s.name !== 'llm-wiki' && s.name !== 'daily-report',
    ).map((s) => ({ uri: s.uri }))
    mocks.fetchCompileSkills.mockResolvedValue(installed)
    mocks.post.mockImplementation(async ({ body }) => {
      if (String(body.data).includes('name: daily-report'))
        throw new Error('denied')
      return {}
    })
    const result = await installMissingBuiltinSkills()
    expect(result.installed).toEqual(['llm-wiki'])
    expect(result.failed.map((f) => f.name)).toEqual(['daily-report'])
    expect(mocks.post).toHaveBeenCalledTimes(2)
  })
})

describe('uri helpers', () => {
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
