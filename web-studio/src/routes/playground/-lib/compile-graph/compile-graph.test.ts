import { describe, expect, it } from 'vitest'

import { detectGraphKind, isWikiIndex } from './detect'
import {
  buildKnowledgeGraph,
  normalizeEntityType,
  resolveEntityLink,
} from './knowledge-graph'
import { cleanLinkTarget, markdownLinks, parseFrontmatter } from './markdown'
import { matchesQuery, neighborhood } from './neighborhood'
import { buildWikiGraph, createWikiLinkResolver } from './wiki'

const ROOT = 'viking://resources/wiki'
const page = (path: string, content: string) => ({
  uri: `${ROOT}/${path}`,
  content,
})

describe('frontmatter', () => {
  it('reads scalars, quoted values, inline and block lists', () => {
    const { data, body, found } = parseFrontmatter(
      '---\nTitle: "Quoted"\ntags: [a, "b"]\naliases:\n  - X\n  - "Y"\n---\n# Body',
    )
    expect(found).toBe(true)
    expect(data).toEqual({
      title: 'Quoted',
      tags: ['a', 'b'],
      aliases: ['X', 'Y'],
    })
    expect(body).toBe('# Body')
  })

  it('leaves documents without frontmatter alone', () => {
    expect(parseFrontmatter('# Only').found).toBe(false)
  })
})

describe('markdown links', () => {
  it('skips images and fenced code', () => {
    const links = markdownLinks(
      '[A](a.md) ![img](i.png)\n```\n[B](b.md)\n```\n[C](<c d.md> "t")',
    )
    expect(links.map((link) => link.target)).toEqual(['a.md', '<c d.md>'])
  })

  it('closes a fence only on an equal or longer marker', () => {
    const links = markdownLinks('````\n```\n[In](in.md)\n````\n[Out](out.md)')
    expect(links.map((link) => link.target)).toEqual(['out.md'])
  })

  it('cleans targets', () => {
    expect(cleanLinkTarget('a&#x2F;b&#46;md')).toBe('a/b.md')
    expect(cleanLinkTarget('<a%20b.md#part>')).toBe('a b.md')
    expect(cleanLinkTarget('x.md?y=1')).toBe('x.md')
  })
})

describe('llm-wiki graph', () => {
  const graph = buildWikiGraph(ROOT, [
    page(
      'index.md',
      '---\ntype: index\ntitle: Home\n---\n[Cat](concept/cat.md) [Dog](entity/dog.md) [web](https://x.dev/a.md)',
    ),
    page(
      'concept/cat.md',
      '---\ntype: concept\n---\n# Cat\nSee [dog](../entity/dog.md), [again](/entity/dog.md) and [self](cat.md).',
    ),
    page('entity/dog.md', 'No frontmatter. Links to [cat by name](cat.md).'),
    page('notes/misc.md', '---\ntitle: Misc\n---\n[missing](nope.md)'),
  ])
  const id = (path: string) => `${ROOT}/${path}`

  it('derives titles and categories', () => {
    const byId = new Map(graph.nodes.map((node) => [node.id, node]))
    expect(byId.get(id('index.md'))).toMatchObject({
      title: 'Home',
      group: 'index',
    })
    expect(byId.get(id('concept/cat.md'))).toMatchObject({
      title: 'Cat',
      group: 'concept',
    })
    expect(byId.get(id('entity/dog.md'))).toMatchObject({
      title: 'dog',
      group: 'entity',
    })
    expect(byId.get(id('notes/misc.md'))?.group).toBe('other')
    expect(graph.nodes[0].group).toBe('index')
  })

  it('resolves relative, root-absolute and basename links, once per pair', () => {
    expect(
      graph.links.map((link) => [link.source, link.target, link.label]),
    ).toEqual([
      [id('concept/cat.md'), id('entity/dog.md'), 'dog'],
      [id('entity/dog.md'), id('concept/cat.md'), 'cat by name'],
      [id('index.md'), id('concept/cat.md'), 'Cat'],
      [id('index.md'), id('entity/dog.md'), 'Dog'],
    ])
    expect(
      graph.nodes.find((node) => node.id === id('concept/cat.md'))?.degree,
    ).toBe(3)
  })

  it('resolves panel links the same way', () => {
    const resolve = createWikiLinkResolver(graph, ROOT)
    expect(resolve(id('concept/cat.md'), '../entity/dog.md')).toBe(
      id('entity/dog.md'),
    )
    expect(resolve(id('index.md'), 'https://x.dev/a.md')).toBeNull()
  })
})

describe('knowledge graph', () => {
  const entity = (id: string, extra = '') => ({
    uri: `viking://resources/kg/entities/${id}.md`,
    content: `---\ntype: entity\nid: ${id}\ntitle: ${id.toUpperCase()}\n${extra}---\nBody of ${id}`,
  })
  const graph = buildKnowledgeGraph(
    [
      entity(
        'wukong',
        'entity_type: Character\naliases: [Monkey King]\nsources: viking://resources/book.md\n',
      ),
      entity('team', 'entity_type: team\n'),
      entity('staff', 'entity_type: spaceship\n'),
    ],
    [
      '{"from":"wukong","to":"team","relation":"member_of","label":"belongs to","evidence":["a"]}',
      '{"from":"wukong","to":"team","relation":"member_of","evidence":["a","b"]}',
      '{"from":"wukong","to":"ghost","relation":"knows","evidence":["c"]}',
      'not json',
      'null',
      '{"from":"team","to":"staff","relation":"Bad Relation"}',
      '',
    ].join('\n'),
  )

  it('normalizes entity types through aliases', () => {
    expect(normalizeEntityType('Character')).toBe('person')
    expect(normalizeEntityType('Org')).toBe('organization')
    expect(normalizeEntityType('spaceship')).toBe('other')
  })

  it('reads entities and merges duplicate relations', () => {
    const wukong = graph.nodes.find((node) => node.id === 'wukong')
    expect(wukong).toMatchObject({
      title: 'WUKONG',
      group: 'person',
      aliases: ['Monkey King'],
      sources: ['viking://resources/book.md'],
      degree: 1,
    })
    expect(graph.links).toEqual([
      {
        source: 'wukong',
        target: 'team',
        relation: 'member_of',
        label: 'belongs to',
        evidence: ['a', 'b'],
      },
    ])
  })

  it('skips bad lines with warnings instead of failing', () => {
    expect(graph.warnings).toEqual([
      'relations.jsonl:3: unknown entity ghost',
      'relations.jsonl:4: not JSON',
      'relations.jsonl:5: not a JSON object',
      'relations.jsonl:6: needs from, to and a snake_case relation',
    ])
  })

  it('resolves entity links by file stem', () => {
    expect(resolveEntityLink(graph, '../entities/team.md')).toBe('team')
    expect(resolveEntityLink(graph, 'other.md')).toBeNull()
    expect(resolveEntityLink(graph, 'https://host/x/team.md')).toBeNull()
    expect(resolveEntityLink(graph, 'viking://resources/team.md')).toBeNull()
  })
})

describe('detection', () => {
  it('prefers a knowledge graph, then asks to confirm a wiki index', () => {
    expect(
      detectGraphKind([
        { name: 'entities', isDir: true },
        { name: 'relations.jsonl', isDir: false },
        { name: 'index.md', isDir: false },
      ]),
    ).toBe('knowledge-graph')
    expect(detectGraphKind([{ name: 'index.md', isDir: false }])).toBe(
      'wiki-candidate',
    )
    expect(detectGraphKind([{ name: 'notes.md', isDir: false }])).toBeNull()
    expect(
      detectGraphKind([
        { name: 'Entities', isDir: true },
        { name: 'relations.jsonl', isDir: false },
      ]),
    ).toBeNull()
    expect(isWikiIndex('---\ntype: index\n---\n')).toBe(true)
    expect(isWikiIndex('# Plain index')).toBe(false)
  })
})

describe('neighborhood', () => {
  const graph = buildWikiGraph(ROOT, [
    page('index.md', '---\ntype: index\n---\n[a](a.md) [b](b.md)'),
    page('a.md', '[c](c.md)'),
    page('b.md', ''),
    page('c.md', ''),
  ])
  const id = (path: string) => `${ROOT}/${path}`

  it('never walks through the wiki index', () => {
    expect([...neighborhood(graph, id('a.md'), 2)].sort()).toEqual(
      [id('a.md'), id('c.md'), id('index.md')].sort(),
    )
    expect(neighborhood(graph, id('index.md'), 1).size).toBe(3)
  })

  it('matches search on title and uri', () => {
    const node = graph.nodes.find((item) => item.id === id('a.md'))!
    expect(matchesQuery(node, 'A.MD')).toBe(true)
    expect(matchesQuery(node, 'zzz')).toBe(false)
  })
})
