import { parse as parseYaml } from 'yaml'
import { describe, expect, it } from 'vitest'

import { splitMarkdownFrontmatter } from '#/lib/markdown-frontmatter'

import {
  buildSkillMarkdown,
  validateSkillDescription,
  validateSkillName,
} from './create-skill'

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
