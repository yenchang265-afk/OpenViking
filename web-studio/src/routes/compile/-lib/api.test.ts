import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchCompileSkills, fetchCompileTask, fetchCompileTasks } from './api'

const clientMocks = vi.hoisted(() => ({
  get: vi.fn(),
}))

const fsMocks = vi.hoisted(() => ({
  fetchFsList: vi.fn(),
}))

vi.mock('#/routes/resources/-lib/api', () => fsMocks)

vi.mock('#/lib/ov-client', () => ({
  getOvResult: async (value: unknown) => value,
  OvClientError: class extends Error {},
  ovClient: { client: clientMocks },
}))

const taskWithoutSources = {
  task_id: 'cmp_memory',
  task_type: 'compile',
  status: 'failed',
  meta: {
    request: {
      to: 'viking://user/default/memories/events',
      skill: 'memory',
    },
  },
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('compile task API normalization', () => {
  it('normalizes an omitted source list in task pages', async () => {
    clientMocks.get.mockResolvedValue({
      items: [taskWithoutSources],
      next_cursor: null,
      has_more: false,
    })

    const page = await fetchCompileTasks()

    expect(page.items[0].meta?.request?.from).toEqual([])
    expect(taskWithoutSources.meta.request).not.toHaveProperty('from')
  })

  it('normalizes a null source list in task details', async () => {
    clientMocks.get.mockResolvedValue({
      ...taskWithoutSources,
      meta: {
        request: { ...taskWithoutSources.meta.request, from: null },
      },
    })

    const task = await fetchCompileTask('cmp_memory')

    expect(task.meta?.request?.from).toEqual([])
  })
})

describe('compile skill listing', () => {
  it('adds bundled system Skills after installed ones', async () => {
    clientMocks.get.mockResolvedValue({
      skills: [
        {
          name: 'mine',
          uri: 'viking://user/alice/skills/mine',
          description: 'd',
        },
      ],
    })
    fsMocks.fetchFsList.mockResolvedValue({
      entries: [
        { name: 'llm-wiki', isDir: true },
        { name: '.abstract.md', isDir: false },
      ],
    })

    expect(await fetchCompileSkills()).toEqual([
      {
        name: 'mine',
        uri: 'viking://user/alice/skills/mine',
        description: 'd',
      },
      {
        name: 'llm-wiki',
        uri: 'viking://system/compile/example-skills/llm-wiki',
        description: '',
      },
    ])
  })

  it('still lists installed Skills when the system namespace is unavailable', async () => {
    clientMocks.get.mockResolvedValue({ skills: [] })
    fsMocks.fetchFsList.mockRejectedValue(new Error('not found'))

    expect(await fetchCompileSkills()).toEqual([])
  })
})
