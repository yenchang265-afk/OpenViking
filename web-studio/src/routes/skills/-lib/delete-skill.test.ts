import { describe, expect, it, vi } from 'vitest'

import { ovClient } from '#/lib/ov-client'

import { deleteSkill, skillTargetUri } from './delete-skill'

vi.mock('#/lib/ov-client', () => ({
  ovClient: { client: { delete: vi.fn() } },
  getOvResult: async (request: Promise<{ data: { result: unknown } }>) =>
    (await request).data.result,
}))

describe('skillTargetUri', () => {
  it('returns the scope root the skill directory sits in', () => {
    expect(skillTargetUri('viking://agent/skills/pr-review')).toBe(
      'viking://agent/skills',
    )
    expect(skillTargetUri('viking://user/alice/skills/pr-review')).toBe(
      'viking://user/alice/skills',
    )
  })
})

describe('deleteSkill', () => {
  it('deletes the skill in its own scope only', async () => {
    vi.mocked(ovClient.client.delete).mockResolvedValue({
      data: { result: { name: 'pr review' } },
    } as never)

    await expect(
      deleteSkill({
        name: 'pr review',
        uri: 'viking://agent/skills/pr review',
      }),
    ).resolves.toEqual({ name: 'pr review' })

    expect(ovClient.client.delete).toHaveBeenCalledWith({
      query: { target_uri: 'viking://agent/skills' },
      url: '/api/v1/skills/pr%20review',
    })
  })
})
