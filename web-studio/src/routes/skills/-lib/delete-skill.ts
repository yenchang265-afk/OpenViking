import { getOvResult, ovClient } from '#/lib/ov-client'

export type DeletableSkill = {
  name: string
  uri: string
}

/** The scope root a skill directory sits in, e.g. `viking://agent/skills`. */
export function skillTargetUri(skillUri: string): string {
  return skillUri.slice(0, skillUri.lastIndexOf('/'))
}

/**
 * Removes the whole skill directory. Passing the skill's own scope root keeps
 * the server from falling back to a same-named skill in another scope.
 */
export async function deleteSkill(skill: DeletableSkill): Promise<unknown> {
  return getOvResult<unknown>(
    ovClient.client.delete({
      query: { target_uri: skillTargetUri(skill.uri) },
      url: `/api/v1/skills/${encodeURIComponent(skill.name)}`,
    }),
  )
}
