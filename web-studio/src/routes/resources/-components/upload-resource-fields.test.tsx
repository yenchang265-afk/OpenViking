// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { UploadResourceFields } from './upload-resource-fields'
import type { SelectedUploadFile } from './upload-resource-fields'
import { MAX_UPLOAD_FILES } from '../-lib/upload'
import type { UploadLimits } from '../-lib/upload-limits'
import type { TFunction } from 'i18next'

const MIB = 1024 * 1024
// Echo the key and interpolation options so assertions can check the size shown.
const echoT = ((key: string, options?: unknown) =>
  `${key}:${JSON.stringify(options)}`) as unknown as TFunction<'addResource'>
const LIMITS: UploadLimits = {
  maxFileBytes: 4 * MIB,
  maxSessionBytes: 8 * MIB,
  maxFiles: 100,
  partSizeBytes: MIB,
}

const mocks = vi.hoisted(() => ({
  onDrop: null as ((files: File[]) => void) | null,
  pending: new Map<string, (value: null) => void>(),
  toast: vi.fn(),
  toastError: vi.fn(),
}))

vi.mock('file-type', () => ({
  fileTypeFromBlob: (file: File) =>
    new Promise((resolve) => {
      mocks.pending.set(file.name, () => resolve(undefined))
    }),
}))

vi.mock('react-dropzone', () => ({
  useDropzone: ({ onDrop }: { onDrop: (files: File[]) => void }) => {
    mocks.onDrop = onDrop
    return {
      getInputProps: () => ({}),
      getRootProps: () => ({}),
      isDragActive: false,
    }
  },
}))

vi.mock('sonner', () => ({
  toast: Object.assign(mocks.toast, { error: mocks.toastError }),
}))

afterEach(() => {
  cleanup()
  mocks.onDrop = null
  mocks.pending.clear()
  vi.clearAllMocks()
})

describe('UploadResourceFields', () => {
  it('appends concurrent drops against the latest selected files', async () => {
    let current: SelectedUploadFile[] = []
    render(
      <UploadResourceFields
        files={[]}
        onFilesChange={(update) => {
          current = typeof update === 'function' ? update(current) : update
        }}
        t={(key) => key}
        limits={LIMITS}
      />,
    )

    mocks.onDrop?.([new File(['first'], 'first.pdf')])
    mocks.onDrop?.([new File(['second'], 'second.pdf')])
    mocks.pending.get('second.pdf')?.(null)
    await Promise.resolve()
    await Promise.resolve()
    mocks.pending.get('first.pdf')?.(null)
    await Promise.resolve()
    await Promise.resolve()

    expect(current.map(({ file }) => file.name).sort()).toEqual([
      'first.pdf',
      'second.pdf',
    ])
  })

  it('reports truncation when concurrent drops exceed the latest limit', async () => {
    let current: SelectedUploadFile[] = Array.from(
      { length: MAX_UPLOAD_FILES - 1 },
      (_, index) => ({
        id: `existing-${index}`,
        file: new File(['existing'], `existing-${index}.pdf`),
        fileType: null,
      }),
    )
    render(
      <UploadResourceFields
        files={current}
        onFilesChange={(update) => {
          current = typeof update === 'function' ? update(current) : update
        }}
        t={(key) => key}
        limits={LIMITS}
      />,
    )

    mocks.onDrop?.([new File(['first'], 'first.pdf')])
    mocks.onDrop?.([new File(['second'], 'second.pdf')])
    mocks.pending.get('first.pdf')?.(null)
    mocks.pending.get('second.pdf')?.(null)

    await waitFor(() => expect(current).toHaveLength(MAX_UPLOAD_FILES))
    expect(mocks.toast).toHaveBeenCalledWith('tooManyFiles', {
      duration: 2500,
    })
  })

  it('keeps a dropped folder as one entry without zipping it', async () => {
    let current: SelectedUploadFile[] = []
    render(
      <UploadResourceFields
        files={[]}
        onFilesChange={(update) => {
          current = typeof update === 'function' ? update(current) : update
        }}
        t={(key) => key}
        limits={LIMITS}
      />,
    )

    const withPath = (file: File, path: string) =>
      Object.defineProperty(file, 'path', { value: path })
    mocks.onDrop?.([
      withPath(new File(['a'], 'a.md'), '/docs/a.md'),
      withPath(new File(['b'], 'b.md'), '/docs/sub/b.md'),
    ])

    await waitFor(() => expect(current).toHaveLength(1))
    expect(current[0].file.name).toBe('docs')
    expect(current[0].folder?.name).toBe('docs')
    expect(current[0].folder?.entries.map((entry) => entry.path)).toEqual([
      'docs/a.md',
      'docs/sub/b.md',
    ])
  })

  it('rejects a folder larger than the upload session limit', async () => {
    let current: SelectedUploadFile[] = []
    render(
      <UploadResourceFields
        files={[]}
        onFilesChange={(update) => {
          current = typeof update === 'function' ? update(current) : update
        }}
        t={echoT}
        limits={{ ...LIMITS, maxSessionBytes: 5 }}
      />,
    )

    const withPath = (file: File, path: string) =>
      Object.defineProperty(file, 'path', { value: path })
    mocks.onDrop?.([
      withPath(new File(['abc'], 'a.md'), '/docs/a.md'),
      withPath(new File(['def'], 'b.md'), '/docs/b.md'),
    ])

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalled())
    expect(current).toHaveLength(0)
    expect(mocks.toastError).toHaveBeenCalledWith(
      'fileTooLarge:{"name":"docs/","size":"5 B"}',
      { duration: 2500 },
    )
  })

  it('removes from the latest files after an asynchronous append', async () => {
    const existing: SelectedUploadFile = {
      id: 'existing',
      file: new File(['existing'], 'existing.pdf'),
      fileType: null,
    }
    let current = [existing]
    render(
      <UploadResourceFields
        files={current}
        onFilesChange={(update) => {
          current = typeof update === 'function' ? update(current) : update
        }}
        t={(key) => key}
        limits={LIMITS}
      />,
    )

    mocks.onDrop?.([new File(['new'], 'new.pdf')])
    mocks.pending.get('new.pdf')?.(null)
    await Promise.resolve()
    await Promise.resolve()
    fireEvent.click(screen.getByRole('button', { name: 'fileInfo.remove' }))

    expect(current.map(({ file }) => file.name)).toEqual(['new.pdf'])
  })

  it('rejects files over the server upload limit and accepts files at it', async () => {
    let current: SelectedUploadFile[] = []
    render(
      <UploadResourceFields
        files={[]}
        onFilesChange={(update) => {
          current = typeof update === 'function' ? update(current) : update
        }}
        t={echoT}
        limits={LIMITS}
      />,
    )

    const atLimit = new File([new Uint8Array(LIMITS.maxFileBytes)], 'ok.pdf')
    const overLimit = new File(
      [new Uint8Array(LIMITS.maxFileBytes + 1)],
      'big.pdf',
    )
    mocks.onDrop?.([overLimit, atLimit])
    await waitFor(() => expect(mocks.pending.has('ok.pdf')).toBe(true))
    mocks.pending.get('ok.pdf')?.(null)

    await waitFor(() => expect(current).toHaveLength(1))
    expect(current[0].file.name).toBe('ok.pdf')
    expect(mocks.toastError).toHaveBeenCalledWith(
      'fileTooLarge:{"name":"big.pdf","size":"4.0 MB"}',
      { duration: 2500 },
    )
  })
})
