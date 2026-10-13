import { stringify as stringifyYaml } from 'yaml'

import { getOvResult, ovClient } from '#/lib/ov-client'

import type { SkillScope } from '../-components/skill-scope-tabs'

/** Mirrors the server's skill name rules (openviking/utils/skill_processor.py). */
export const MAX_SKILL_NAME_LENGTH = 64
export const MAX_SKILL_DESCRIPTION_LENGTH = 1024
const SKILL_NAME_PATTERN = /^[A-Za-z0-9_-]+$/

export const SKILL_TARGET_URIS = {
  agent: 'viking://agent/skills',
  user: 'viking://~/skills',
} satisfies Record<SkillScope, string>

export type SkillDraft = {
  body: string
  description: string
  name: string
  scope: SkillScope
}

export type SkillNameError = 'required' | 'tooLong' | 'invalid' | 'exists'
export type SkillDescriptionError = 'required' | 'tooLong'

export function validateSkillName(
  name: string,
  existingNames: ReadonlySet<string>,
): SkillNameError | null {
  const trimmed = name.trim()
  if (!trimmed) return 'required'
  if (trimmed.length > MAX_SKILL_NAME_LENGTH) return 'tooLong'
  if (!SKILL_NAME_PATTERN.test(trimmed)) return 'invalid'
  // Installing over an existing name replaces that skill without asking.
  if (existingNames.has(trimmed)) return 'exists'
  return null
}

export function validateSkillDescription(
  description: string,
): SkillDescriptionError | null {
  const trimmed = description.trim()
  if (!trimmed) return 'required'
  if (trimmed.length > MAX_SKILL_DESCRIPTION_LENGTH) return 'tooLong'
  return null
}

/** Build a SKILL.md document: YAML frontmatter followed by the instructions. */
export function buildSkillMarkdown({
  body,
  description,
  name,
}: Pick<SkillDraft, 'body' | 'description' | 'name'>): string {
  const frontmatter = stringifyYaml(
    { name: name.trim(), description: description.trim() },
    { lineWidth: 0 },
  )
  const instructions = body.trim()
  return `---\n${frontmatter}---\n${instructions ? `\n${instructions}\n` : ''}`
}

export async function createSkill(draft: SkillDraft): Promise<unknown> {
  return getOvResult<unknown>(
    ovClient.client.post({
      body: {
        data: buildSkillMarkdown(draft),
        target_uri: SKILL_TARGET_URIS[draft.scope],
      },
      url: '/api/v1/resources/skills',
    }),
  )
}
