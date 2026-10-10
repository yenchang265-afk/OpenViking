import { getOvResult, ovClient } from '#/lib/ov-client'
import { fetchCompileSkills } from './api'

/** Shared skills root: built-ins land where every user of the account sees them. */
export const BUILTIN_SKILLS_ROOT = 'viking://agent/skills'

export type BuiltinCompileSkill = {
  name: string
  description: string
  uri: string
  content: string
}

// Bundled from the repo at build time, so Studio ships the same SKILL.md files
// that `ov add-skill examples/compile/ov-compile-skills/<name>` installs.
const sources = import.meta.glob<string>(
  '../../../../../examples/compile/ov-compile-skills/*/SKILL.md',
  { eager: true, import: 'default', query: '?raw' },
)

export function parseSkillFrontmatter(content: string) {
  const block = /^---\r?\n([\s\S]*?)\r?\n---/.exec(content)?.[1] ?? ''
  const field = (key: string) =>
    (new RegExp(`^${key}:[ \\t]*(.*)$`, 'm').exec(block)?.[1] ?? '')
      .trim()
      .replace(/^(['"])(.*)\1$/, '$2')
  return { name: field('name'), description: field('description') }
}

export const BUILTIN_COMPILE_SKILLS: readonly BuiltinCompileSkill[] =
  Object.values(sources)
    .flatMap((content) => {
      const { name, description } = parseSkillFrontmatter(content)
      return name
        ? [
            {
              name,
              description,
              uri: `${BUILTIN_SKILLS_ROOT}/${name}`,
              content,
            },
          ]
        : []
    })
    .sort((a, b) => a.name.localeCompare(b.name))

const trimSlash = (uri: string) => uri.replace(/\/+$/, '')

export function missingBuiltinSkills(
  installed: readonly { uri: string }[],
): BuiltinCompileSkill[] {
  const uris = new Set(installed.map((skill) => trimSlash(skill.uri)))
  return BUILTIN_COMPILE_SKILLS.filter((skill) => !uris.has(skill.uri))
}

function postBuiltinSkill(skill: BuiltinCompileSkill) {
  return getOvResult<unknown>(
    ovClient.client.post({
      url: '/api/v1/skills',
      body: {
        data: skill.content,
        target_uri: BUILTIN_SKILLS_ROOT,
        source_metadata: {
          type: 'studio',
          source: 'ov-compile-skills',
          operation: 'add',
        },
      },
    }),
  )
}

// Concurrent requests for the same skill (menu clicks, the Install button)
// share one check-and-install instead of posting twice.
const inFlight = new Map<string, Promise<boolean>>()

/** Installs the skill unless it is already there; never overwrites edits. */
export function ensureBuiltinSkill(
  skill: BuiltinCompileSkill,
): Promise<boolean> {
  const pending = inFlight.get(skill.uri)
  if (pending) return pending
  const run = (async () => {
    const missing = missingBuiltinSkills(await fetchCompileSkills())
    if (!missing.some((item) => item.uri === skill.uri)) return false
    await postBuiltinSkill(skill)
    return true
  })().finally(() => inFlight.delete(skill.uri))
  inFlight.set(skill.uri, run)
  return run
}

/** Installs, one at a time, every built-in still missing right now. */
export async function installMissingBuiltinSkills(): Promise<{
  installed: string[]
  failed: { name: string; error: unknown }[]
}> {
  const installed: string[] = []
  const failed: { name: string; error: unknown }[] = []
  for (const skill of missingBuiltinSkills(await fetchCompileSkills())) {
    try {
      if (await ensureBuiltinSkill(skill)) installed.push(skill.name)
    } catch (error) {
      failed.push({ name: skill.name, error })
    }
  }
  return { installed, failed }
}

/** `viking://agent/skills/<name>` or `viking://user/<id>/skills/<name>`. */
export function isSkillRootUri(uri: string): boolean {
  return /^viking:\/\/(?:agent|user\/[^/]+)\/skills\/[^/]+$/.test(
    trimSlash(uri),
  )
}

/** Any directory below the `viking://` root can be a compile source. */
export function isCompileSourceUri(uri: string): boolean {
  return /^viking:\/\/[^/]+/.test(uri)
}

/**
 * Default output for compiling `sourceUri`: a sibling inside a resources
 * tree, otherwise a new directory under `viking://resources`.
 */
export function suggestCompileTarget(sourceUri: string, skillName: string) {
  const base = trimSlash(sourceUri)
  if (/^viking:\/\/(?:user\/[^/]+\/)?resources\/.+/.test(base))
    return `${base}-${skillName}`
  const name = base.split('/').pop() || 'compiled'
  return `viking://resources/${name}-${skillName}`
}
