// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { buildKnowledgeGraph } from '../../-lib/compile-graph/knowledge-graph'
import { buildWikiGraph } from '../../-lib/compile-graph/wiki'
import { CompileGraphView } from './graph-view'

const { loadMock } = vi.hoisted(() => ({ loadMock: vi.fn() }))
vi.mock('../../-lib/compile-graph/load', () => ({
  loadCompiledGraph: loadMock,
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && 'count' in options ? `${key}:${String(options.count)}` : key,
  }),
}))

const ROOT = 'viking://resources/wiki'
const wiki = buildWikiGraph(ROOT, [
  {
    uri: `${ROOT}/index.md`,
    content: '---\ntype: index\ntitle: Home\n---\n[Cat](concept/cat.md)',
  },
  {
    uri: `${ROOT}/concept/cat.md`,
    content:
      '---\ntype: concept\ntitle: Cat\n---\nSee [home](../index.md), [site](https://example.com), [raw](viking://resources/raw.md) and [bad](javascript:alert(1)).',
  },
])

function renderView(kind: 'llm-wiki' | 'knowledge-graph' = 'llm-wiki') {
  const onOpenFile = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CompileGraphView
        dirUri={`${ROOT}/`}
        kind={kind}
        scopeKey="test"
        onOpenFile={onOpenFile}
      />
    </QueryClientProvider>,
  )
  return { onOpenFile }
}

const panel = () => screen.getByRole('complementary')
const canvas = () =>
  within(screen.getByRole('group', { name: 'compileGraph.canvas' }))
const findNode = async (name: string) => {
  await screen.findByRole('group', { name: 'compileGraph.canvas' })
  return canvas().findByRole('button', { name })
}

beforeEach(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
    },
  )
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('CompileGraphView', () => {
  it('draws every page and starts on the wiki index', async () => {
    loadMock.mockResolvedValue(wiki)
    renderView()

    expect(await findNode('Cat')).toBeTruthy()
    expect(canvas().getByRole('button', { name: 'Home' })).toBeTruthy()
    expect(within(panel()).getByRole('heading', { name: 'Home' })).toBeTruthy()
    expect(loadMock).toHaveBeenCalledWith(ROOT, 'llm-wiki')
  })

  it('selects a node from the canvas and follows panel links safely', async () => {
    loadMock.mockResolvedValue(wiki)
    const { onOpenFile } = renderView()
    fireEvent.click(await findNode('Cat'))

    const details = within(panel())
    expect(details.getByRole('heading', { name: 'Cat' })).toBeTruthy()
    const external = details.getByRole('link', { name: 'site' })
    expect(external.getAttribute('target')).toBe('_blank')
    expect(external.getAttribute('rel')).toBe('noopener noreferrer')
    expect(details.queryByRole('link', { name: 'bad' })).toBeNull()

    fireEvent.click(details.getByRole('button', { name: 'raw' }))
    expect(onOpenFile).toHaveBeenCalledWith('viking://resources/raw.md')

    fireEvent.click(details.getByRole('button', { name: 'home' }))
    expect(within(panel()).getByRole('heading', { name: 'Home' })).toBeTruthy()

    fireEvent.click(within(panel()).getByTitle('compileGraph.openFile'))
    expect(onOpenFile).toHaveBeenCalledWith(`${ROOT}/index.md`)
  })

  it('ignores Enter on an empty search', async () => {
    loadMock.mockResolvedValue(wiki)
    renderView()
    const search = await screen.findByRole('textbox', {
      name: 'compileGraph.search',
    })
    fireEvent.click(await findNode('Cat'))
    fireEvent.keyDown(search, { key: 'Enter' })

    expect(within(panel()).getByRole('heading', { name: 'Cat' })).toBeTruthy()
  })

  it('selects the first search match on Enter', async () => {
    loadMock.mockResolvedValue(wiki)
    renderView()
    const search = await screen.findByRole('textbox', {
      name: 'compileGraph.search',
    })
    fireEvent.change(search, { target: { value: 'cat' } })
    fireEvent.keyDown(search, { key: 'Enter' })

    expect(within(panel()).getByRole('heading', { name: 'Cat' })).toBeTruthy()
  })

  it('shows relations with evidence for a knowledge graph', async () => {
    loadMock.mockResolvedValue(
      buildKnowledgeGraph(
        [
          {
            uri: `${ROOT}/entities/a.md`,
            content: '---\nid: a\ntitle: Alpha\nentity_type: person\n---\n',
          },
          {
            uri: `${ROOT}/entities/b.md`,
            content: '---\nid: b\ntitle: Beta\nentity_type: place\n---\n',
          },
        ],
        '{"from":"a","to":"b","relation":"lives_in","label":"lives in","evidence":["viking://resources/doc.md"]}',
      ),
    )
    renderView('knowledge-graph')

    await findNode('Alpha')
    const details = within(panel())
    expect(details.getByText('compileGraph.relations:1')).toBeTruthy()
    expect(details.getByText('lives in')).toBeTruthy()
    expect(details.getByText('compileGraph.evidence:1')).toBeTruthy()
    expect(details.getByText('viking://resources/doc.md')).toBeTruthy()
  })

  it('reports an output with nothing to draw', async () => {
    loadMock.mockResolvedValue({ ...wiki, nodes: [], links: [] })
    renderView()
    expect(await screen.findByText('compileGraph.empty')).toBeTruthy()
  })
})
