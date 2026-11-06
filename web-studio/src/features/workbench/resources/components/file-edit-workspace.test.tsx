// @vitest-environment jsdom
import { createRef } from 'react'
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FileEditWorkspace } from './file-edit-workspace'
import type { FileEditHandle } from './file-edit-workspace'
import {
  saveEditorImages,
  stageEditorImage,
  discardEditorImages,
} from '../lib/editor-images'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))
vi.mock('../lib/api', () => ({
  fetchFsList: vi.fn(async () => ({ entries: [] })),
}))
vi.mock('../lib/editor-images', () => ({
  MAX_EDITOR_IMAGE_BYTES: 10 * 1024 * 1024,
  discardEditorImages: vi.fn(),
  supportsEditorImages: (uri: string) => uri.startsWith('viking://resources/'),
  stageEditorImage: vi.fn(),
  saveEditorImages: vi.fn(),
}))
vi.mock('#/shared/components/code-editor', async () => {
  const React = await import('react')
  return {
    CodeEditor: React.forwardRef(
      (
        {
          initialContent,
          onChange,
          readOnly,
        }: {
          initialContent: string
          onChange: (content: string) => void
          readOnly: boolean
        },
        ref,
      ) => {
        React.useImperativeHandle(ref, () => ({
          getContent: () => initialContent,
          insertText: (text: string) => onChange(initialContent + text),
        }))
        return (
          <textarea
            aria-label="source"
            value={initialContent}
            readOnly={readOnly}
            onChange={(event) => onChange(event.target.value)}
          />
        )
      },
    ),
  }
})

Object.defineProperty(URL, 'revokeObjectURL', {
  configurable: true,
  value: vi.fn(),
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})
const uri = 'viking://resources/demo/note.md'
function setup(content = '# Hello', documentUri = uri) {
  const ref = createRef<FileEditHandle>()
  const onChange = vi.fn()
  render(
    <FileEditWorkspace
      ref={ref}
      uri={documentUri}
      filename="note.md"
      initialContent={content}
      markdown
      isDark={false}
      saving={false}
      onChange={onChange}
      renderPreview={(text) => <div data-testid="preview">{text}</div>}
    />,
  )
  return { ref, onChange }
}

describe('file editing workspace', () => {
  it('keeps source edits when switching to split preview and back', () => {
    const { ref } = setup()
    fireEvent.change(screen.getByLabelText('source'), {
      target: { value: '# My draft' },
    })
    fireEvent.click(
      screen.getByRole('button', { name: 'filePreview.editor.split' }),
    )
    expect(screen.getByTestId('preview').textContent).toBe('# My draft')
    fireEvent.click(
      screen.getByRole('button', { name: 'filePreview.editor.source' }),
    )
    expect(ref.current?.getContent()).toBe('# My draft')
  })
  it('leaves metadata comments intact and disables lossy rich conversion', () => {
    const content = '# Note\n<!-- MEMORY_FIELDS {"content":"private"} -->'
    const { ref } = setup(content)
    expect(
      screen.getByRole<HTMLButtonElement>('button', {
        name: 'filePreview.editor.rich',
      }).disabled,
    ).toBe(true)
    expect(ref.current?.getContent()).toBe(content)
  })
  it('stages images, inserts a durable reference, and uploads only on save', async () => {
    const image = {
      uri: 'viking://resources/demo/assets/id.png',
      path: 'assets/id.png',
      alt: 'Screenshot',
      base64: 'png',
      previewUrl: 'blob:staged',
    }
    vi.mocked(stageEditorImage).mockResolvedValue(image)
    vi.mocked(saveEditorImages).mockResolvedValue(undefined)
    const { ref } = setup()
    fireEvent.change(screen.getByLabelText('filePreview.editor.insertImage'), {
      target: {
        files: [new File(['png'], 'Screenshot.png', { type: 'image/png' })],
      },
    })
    await waitFor(() =>
      expect(ref.current?.getContent()).toContain(
        '![Screenshot](assets/id.png)',
      ),
    )
    expect(saveEditorImages).not.toHaveBeenCalled()
    await act(async () => {
      await ref.current?.saveAssets()
    })
    expect(saveEditorImages).toHaveBeenCalledWith(uri, [image])
  })
  it('retains the source draft when an image upload fails', async () => {
    const { ref } = setup('draft')
    vi.mocked(saveEditorImages).mockRejectedValue(new Error('offline'))
    await expect(ref.current?.saveAssets()).rejects.toThrow('offline')
    expect(ref.current?.getContent()).toBe('draft')
  })
  it('does not offer binary image uploads in memory namespaces', () => {
    setup('# Memory', 'viking://user/alice/memories/events/note.md')
    expect(
      screen.queryByRole('button', { name: 'filePreview.editor.insertImage' }),
    ).toBeNull()
  })
})

it('retains uploaded images after an attempted document write that might have committed', async () => {
  vi.mocked(stageEditorImage).mockResolvedValue({
    uri: 'viking://resources/demo/assets/id.png',
    path: 'assets/id.png',
    alt: 'Shot',
    base64: 'png',
    previewUrl: 'blob:staged',
  })
  vi.mocked(saveEditorImages).mockResolvedValue(undefined)
  const { ref } = setup()
  fireEvent.change(screen.getByLabelText('filePreview.editor.insertImage'), {
    target: { files: [new File(['png'], 'Shot.png', { type: 'image/png' })] },
  })
  await waitFor(() =>
    expect(ref.current?.getContent()).toContain('assets/id.png'),
  )
  await ref.current?.saveAssets()
  ref.current?.retainAssets()
  cleanup()
  expect(discardEditorImages).not.toHaveBeenCalled()
})
