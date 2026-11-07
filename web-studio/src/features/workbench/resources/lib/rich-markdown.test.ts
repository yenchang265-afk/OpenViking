import { describe, expect, it } from 'vitest'
import { richMarkdownBody } from './rich-markdown'

describe('rich Markdown eligibility', () => {
  it('preserves frontmatter bytes, BOM, and line endings separately from the editable body', () => {
    const prefix = '\uFEFF---\r\ntitle: Example\r\n---\r\n'
    expect(richMarkdownBody(prefix + '# Heading')).toEqual({
      prefix,
      body: '# Heading',
    })
  })
  it.each([
    '<!-- MEMORY_FIELDS {} -->',
    '<div>HTML</div>',
    '[ref]: ./note.md',
    '[link][ref]',
    '[^footnote]',
    '::: custom',
    '~~strike~~',
    '| Table |',
    '- [ ] task',
    '```mermaid\ngraph TD\n```',
  ])('requires source mode for unsupported syntax: %s', (text) => {
    expect(richMarkdownBody(text)).toBeNull()
  })
  it('allows basic Markdown and local images', () => {
    const body = '# Title\n\n**Bold** and *italic*\n\n![image](assets/id.png)'
    expect(richMarkdownBody(body)).toEqual({ prefix: '', body })
  })
})
