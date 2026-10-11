import { beforeEach, describe, expect, it, vi } from 'vitest'

import { loadCompiledGraph } from './load'

const api = vi.hoisted(() => ({
  fetchFsList: vi.fn(),
  fetchFileContent: vi.fn(),
}))
vi.mock('#/routes/resources/-lib/api', () => api)

const ROOT = 'viking://resources/wiki'
const file = (path: string) => ({
  uri: `${ROOT}/${path}`,
  name: path.split('/').pop(),
  isDir: false,
})

beforeEach(() => {
  vi.clearAllMocks()
})

describe('loadCompiledGraph', () => {
  it('reads visible Markdown pages and skips unreadable ones with a warning', async () => {
    api.fetchFsList.mockResolvedValue({
      entries: [
        file('index.md'),
        file('concept/cat.md'),
        file('broken.md'),
        file('.overview.md'),
        file('concept/.abstract.md'),
        file('data.json'),
        { uri: `${ROOT}/concept/`, name: 'concept', isDir: true },
      ],
    })
    api.fetchFileContent.mockImplementation(async (uri: string) => {
      if (uri.endsWith('broken.md')) throw new Error('denied')
      return {
        content: uri.endsWith('index.md') ? '[Cat](concept/cat.md)' : '',
      }
    })

    const graph = await loadCompiledGraph(`${ROOT}/`, 'llm-wiki')

    expect(api.fetchFsList).toHaveBeenCalledWith(ROOT, {
      recursive: true,
      nodeLimit: 801,
    })
    expect(graph.nodes.map((node) => node.uri).sort()).toEqual([
      `${ROOT}/concept/cat.md`,
      `${ROOT}/index.md`,
    ])
    expect(graph.links).toHaveLength(1)
    expect(graph.warnings).toEqual([
      `${ROOT}/broken.md: could not be read (denied)`,
    ])
  })

  it('reads entities and relations for a knowledge graph', async () => {
    api.fetchFsList.mockResolvedValue({
      entries: [file('entities/a.md'), file('entities/b.md')],
    })
    api.fetchFileContent.mockImplementation(async (uri: string) => ({
      content: uri.endsWith('relations.jsonl')
        ? '{"from":"a","to":"b","relation":"knows"}'
        : `---\nid: ${uri.endsWith('a.md') ? 'a' : 'b'}\ntitle: T\n---\n`,
    }))

    const graph = await loadCompiledGraph(ROOT, 'knowledge-graph')

    expect(api.fetchFsList).toHaveBeenCalledWith(`${ROOT}/entities`, {
      recursive: false,
      nodeLimit: 801,
    })
    expect(graph.links).toEqual([
      {
        source: 'a',
        target: 'b',
        relation: 'knows',
        label: 'knows',
        evidence: [],
      },
    ])
  })
})
