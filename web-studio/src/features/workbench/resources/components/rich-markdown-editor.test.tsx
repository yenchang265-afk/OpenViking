// @vitest-environment jsdom
import { createRef } from 'react'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import RichMarkdownEditor from './rich-markdown-editor'
import type { CodeEditorHandle } from '#/shared/components/code-editor'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock('#/shared/api/ov-client', () => ({ getContentDownload: vi.fn() }))
beforeEach(() => {
  Object.defineProperty(Range.prototype, 'getClientRects', {
    configurable: true,
    value: () => [],
  })
  Object.defineProperty(Range.prototype, 'getBoundingClientRect', {
    configurable: true,
    value: () => new DOMRect(),
  })
  Object.defineProperty(HTMLElement.prototype, 'getClientRects', {
    configurable: true,
    value: () => [],
  })
})
afterEach(cleanup)
it('preserves exact original Markdown until the user edits, including frontmatter', async () => {
  const ref = createRef<CodeEditorHandle>()
  const content = '\uFEFF---\r\ntitle: test\r\n---\r\n# Original\n\nText  \n'
  const onChange = vi.fn()
  render(
    <RichMarkdownEditor
      ref={ref}
      initialContent={content}
      readOnly={false}
      onChange={onChange}
      getImageUrl={() => undefined}
      uri="viking://resources/demo/note.md"
    />,
  )
  await screen.findByLabelText('filePreview.editor.rich')
  expect(ref.current?.getContent()).toBe(content)
  expect(onChange).not.toHaveBeenCalled()
  act(() => ref.current?.insertText('**New text**'))
  await waitFor(() => expect(onChange).toHaveBeenCalled())
  expect(ref.current?.getContent()).toContain('**New text**')
  expect(
    ref.current?.getContent().startsWith('\uFEFF---\r\ntitle: test\r\n---\r\n'),
  ).toBe(true)
})
it('renders staged images while keeping durable paths in saved Markdown', async () => {
  const ref = createRef<CodeEditorHandle>()
  render(
    <RichMarkdownEditor
      ref={ref}
      initialContent="# Images"
      readOnly={false}
      onChange={vi.fn()}
      getImageUrl={() => 'blob:local-preview'}
      uri="viking://resources/demo/note.md"
    />,
  )
  await screen.findByLabelText('filePreview.editor.rich')
  act(() => ref.current?.insertText('![Shot](assets/id.png)'))
  expect((await screen.findByAltText<HTMLImageElement>('Shot')).src).toBe(
    'blob:local-preview',
  )
  expect(ref.current?.getContent()).toContain('assets/id.png')
  expect(ref.current?.getContent()).not.toContain('blob:')
})
