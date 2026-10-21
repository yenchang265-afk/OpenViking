import { parse as parseYaml } from 'yaml'
import { describe, expect, it, vi } from 'vitest'

import { splitMarkdownFrontmatter } from '#/lib/markdown-frontmatter'
import { ovClient } from '#/lib/ov-client'

import {
  buildSkillMarkdown,
  createSkill,
  validateSkillDescription,
  validateSkillName,
} from './create-skill'

vi.mock('#/lib/ov-client', () => ({
  ovClient: { client: { post: vi.fn() } },
  getOvResult: async (request: Promise<{ data: { result: unknown } }>) =>
    (await request).data.result,
}))

describe('validateSkillName', () => {
  it('accepts names the server accepts', () => {
    expect(validateSkillName('pr_triage-2')).toBeNull()
    expect(validateSkillName('  padded  ')).toBeNull()
  })

  it('rejects empty, long, and non-ASCII names', () => {
    expect(validateSkillName('   ')).toBe('required')
    expect(validateSkillName('a'.repeat(65))).toBe('tooLong')
    expect(validateSkillName('has space')).toBe('invalid')
    expect(validateSkillName('技能')).toBe('invalid')
  })
})

describe('validateSkillDescription', () => {
  it('requires a description within the length limit', () => {
    expect(validateSkillDescription(' ')).toBe('required')
    expect(validateSkillDescription('x'.repeat(1025))).toBe('tooLong')
    expect(validateSkillDescription('Reviews pull requests')).toBeNull()
  })
})

describe('buildSkillMarkdown', () => {
  it('writes frontmatter the server can parse, then the instructions', () => {
    const markdown = buildSkillMarkdown({
      body: '\n# Steps\n\n1. Read the diff.\n',
      description: 'Use when: reviewing "risky" changes',
      name: ' pr-review ',
    })
    const split = splitMarkdownFrontmatter(markdown)

    expect(split).not.toBeNull()
    const meta = parseYaml(
      split!.rawFrontmatter.replace(/^---\n/, '').replace(/\n---$/, ''),
    )
    expect(meta).toEqual({
      description: 'Use when: reviewing "risky" changes',
      name: 'pr-review',
    })
    expect(split!.body).toBe('\n# Steps\n\n1. Read the diff.\n')
  })

  it('allows an empty body', () => {
    expect(
      buildSkillMarkdown({ body: '  ', description: 'd', name: 'n' }),
    ).toBe('---\nname: n\ndescription: d\n---\n')
  })
})

describe('createSkill', () => {
  it('installs the built SKILL.md through the server add-skill route', async () => {
    vi.mocked(ovClient.client.post).mockResolvedValue({
      data: { result: { status: 'success' } },
    } as never)

    await createSkill({ body: '', description: 'd', name: 'n', scope: 'agent' })

    expect(ovClient.client.post).toHaveBeenCalledWith({
      body: {
        data: '---\nname: n\ndescription: d\n---\n',
        target_uri: 'viking://agent/skills',
      },
      url: '/api/v1/skills',
    })
  })
})
