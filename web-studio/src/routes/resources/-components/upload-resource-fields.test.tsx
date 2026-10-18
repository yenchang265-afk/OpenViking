// @vitest-environment jsdom

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  UploadResourceFields,
  isScanningSelection,
  refilterSelectedFiles,
} from './upload-resource-fields'
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

const NO_FILTERS = { ignoreDirs: '', include: '', exclude: '' }

const mocks = vi.hoisted(() => ({
  onDrop: null as ((files: File[]) => void) | null,
  getFilesFromEvent: null as
    | ((event: unknown) => Promise<Array<File | DataTransferItem>>)
    | null,
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
  useDropzone: (options: {
    onDrop: (files: File[]) => void
    getFilesFromEvent: (
      event: unknown,
    ) => Promise<Array<File | DataTransferItem>>
  }) => {
    mocks.onDrop = options.onDrop
    mocks.getFilesFromEvent = options.getFilesFromEvent
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

/** Dropped files are read (empty check) before type detection starts. */
async function waitForDetection(...names: string[]) {
  await waitFor(() =>
    expect(names.every((name) => mocks.pending.has(name))).toBe(true),
  )
}

afterEach(() => {
  cleanup()
  mocks.onDrop = null
  mocks.getFilesFromEvent = null
  mocks.pending.clear()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
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
        filters={NO_FILTERS}
        limits={LIMITS}
      />,
    )

    mocks.onDrop?.([new File(['first'], 'first.pdf')])
    mocks.onDrop?.([new File(['second'], 'second.pdf')])
    await waitForDetection('first.pdf', 'second.pdf')
    mocks.pending.get('second.pdf')?.(null)
    await waitFor(() => expect(current).toHaveLength(1))
    mocks.pending.get('first.pdf')?.(null)

    await waitFor(() =>
      expect(current.map(({ file }) => file.name).sort()).toEqual([
        'first.pdf',
        'second.pdf',
      ]),
    )
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
        filters={NO_FILTERS}
        limits={LIMITS}
      />,
    )

    mocks.onDrop?.([new File(['first'], 'first.pdf')])
    mocks.onDrop?.([new File(['second'], 'second.pdf')])
    await waitForDetection('first.pdf', 'second.pdf')
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
        filters={NO_FILTERS}
        limits={LIMITS}
      />,
    )

    const withPath = (file: File, path: string) =>
      Object.defineProperty(file, 'path', { value: path })
    mocks.onDrop?.([
      withPath(new File(['a'], 'a.md'), '/docs/a.md'),
      withPath(new File(['b'], 'b.md'), '/docs/sub/b.md'),
    ])

    await waitFor(() => expect(current[0]?.folder).toBeDefined())
    expect(current).toHaveLength(1)
    expect(current[0].file.name).toBe('docs')
    expect(current[0].folder?.name).toBe('docs')
    expect(current[0].folder?.entries.map((entry) => entry.path)).toEqual([
      'docs/a.md',
      'docs/sub/b.md',
    ])
  })

  it('filters a dropped folder by its .gitignore and the folder options', async () => {
    let current: SelectedUploadFile[] = []
    render(
      <UploadResourceFields
        files={[]}
        onFilesChange={(update) => {
          current = typeof update === 'function' ? update(current) : update
        }}
        t={echoT}
        filters={{ ignoreDirs: '', include: '', exclude: '*.tmp' }}
        limits={LIMITS}
      />,
    )

    const withPath = (file: File, path: string) =>
      Object.defineProperty(file, 'path', { value: path })
    mocks.onDrop?.([
      withPath(new File(['target/\n'], '.gitignore'), '/repo/.gitignore'),
      withPath(new File(['a'], 'a.md'), '/repo/a.md'),
      withPath(new File(['b'], 'app.d'), '/repo/target/debug/app.d'),
      withPath(new File(['c'], 'index.js'), '/repo/node_modules/x/index.js'),
      withPath(new File(['d'], 'x.tmp'), '/repo/x.tmp'),
    ])

    await waitFor(() => expect(current[0]?.folder).toBeDefined())
    expect(current).toHaveLength(1)
    expect(current[0].folder?.entries.map((entry) => entry.path)).toEqual([
      'repo/a.md',
      'repo/node_modules/x/index.js',
    ])
    expect(mocks.toast).toHaveBeenCalledWith(
      'folderSkipped:{"name":"repo","count":3}',
      { duration: 2500 },
    )
    expect(
      refilterSelectedFiles(current, {
        ignoreDirs: 'node_modules',
        include: '',
        exclude: '',
      })[0].folder?.entries.map((entry) => entry.path),
    ).toEqual(['repo/a.md', 'repo/x.tmp'])
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
        filters={NO_FILTERS}
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
      'folderTooLarge:{"name":"docs/","size":"6 B","max":"5 B"}',
      { duration: 2500 },
    )
  })

  it('says how many files a folder has when it exceeds the file limit', async () => {
    let current: SelectedUploadFile[] = []
    render(
      <UploadResourceFields
        files={[]}
        onFilesChange={(update) => {
          current = typeof update === 'function' ? update(current) : update
        }}
        t={echoT}
        filters={NO_FILTERS}
        limits={{ ...LIMITS, maxFiles: 2 }}
      />,
    )

    const withPath = (file: File, path: string) =>
      Object.defineProperty(file, 'path', { value: path })
    mocks.onDrop?.(
      ['a', 'b', 'c'].map((name) =>
        withPath(new File([name], `${name}.md`), `/docs/${name}.md`),
      ),
    )

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalled())
    expect(current).toHaveLength(0)
    expect(mocks.toastError).toHaveBeenCalledWith(
      'folderTooManyFiles:{"name":"docs/","files":"3","max":"2"}',
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
        filters={NO_FILTERS}
        limits={LIMITS}
      />,
    )

    mocks.onDrop?.([new File(['new'], 'new.pdf')])
    await waitForDetection('new.pdf')
    mocks.pending.get('new.pdf')?.(null)
    await waitFor(() => expect(current).toHaveLength(2))
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
        filters={NO_FILTERS}
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

  it('rejects empty and whitespace-only files before upload', async () => {
    let current: SelectedUploadFile[] = []
    render(
      <UploadResourceFields
        files={[]}
        onFilesChange={(update) => {
          current = typeof update === 'function' ? update(current) : update
        }}
        t={echoT}
        filters={NO_FILTERS}
        limits={LIMITS}
      />,
    )

    mocks.onDrop?.([
      new File([], 'empty.md'),
      new File([' \n\t\n'], 'blank.md'),
      new File(['# Notes'], 'notes.md'),
    ])
    await waitFor(() => expect(mocks.pending.has('notes.md')).toBe(true))
    mocks.pending.get('notes.md')?.(null)

    await waitFor(() => expect(current).toHaveLength(1))
    expect(current[0].file.name).toBe('notes.md')
    expect(mocks.toastError).toHaveBeenCalledWith(
      'fileEmpty:{"name":"empty.md"}',
      { duration: 2500 },
    )
    expect(mocks.toastError).toHaveBeenCalledWith(
      'fileEmpty:{"name":"blank.md"}',
      { duration: 2500 },
    )
  })
})

/** Renders with real state, reporting every change to `onChange`. */
function Harness({
  onChange,
}: {
  onChange: (files: SelectedUploadFile[]) => void
}) {
  const [files, setFiles] = useState<SelectedUploadFile[]>([])
  return (
    <UploadResourceFields
      files={files}
      onFilesChange={(update) =>
        setFiles((previous) => {
          const next = typeof update === 'function' ? update(previous) : update
          onChange(next)
          return next
        })
      }
      t={echoT}
      filters={NO_FILTERS}
      limits={LIMITS}
    />
  )
}

function fileEntry(name: string, content: string): FileSystemFileEntry {
  return {
    name,
    isDirectory: false,
    isFile: true,
    file: (resolve: (file: File) => void) => resolve(new File([content], name)),
  } as unknown as FileSystemFileEntry
}

/** A dropped folder whose listing waits until `release` is called. */
function gatedFolderEntry(name: string, children: FileSystemEntry[]) {
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  const entry = {
    name,
    isDirectory: true,
    isFile: false,
    createReader: () => {
      let read = false
      return {
        readEntries: (resolve: (entries: FileSystemEntry[]) => void) => {
          if (read) return resolve([])
          read = true
          void gate.then(() => resolve(children))
        },
      }
    },
  } as unknown as FileSystemDirectoryEntry
  return { entry, release }
}

function dropEvent(...entries: FileSystemEntry[]) {
  return {
    type: 'drop',
    dataTransfer: {
      items: entries.map((entry) => ({
        kind: 'file',
        webkitGetAsEntry: () => entry,
        getAsFile: () => null,
      })),
      files: [],
    },
  }
}

describe('UploadResourceFields folder scanning', () => {
  it('shows a dropped folder at once and fills it in once read', async () => {
    let current: SelectedUploadFile[] = []
    render(<Harness onChange={(files) => (current = files)} />)

    const { entry, release } = gatedFolderEntry('docs', [
      fileEntry('a.md', 'a'),
    ])
    let dropped: Array<File | DataTransferItem> = []
    await act(async () => {
      dropped = (await mocks.getFilesFromEvent?.(dropEvent(entry))) ?? []
    })

    expect(dropped).toEqual([])
    expect(current).toHaveLength(1)
    expect(current[0].scanning).toEqual({ filesFound: 0 })
    expect(isScanningSelection(current)).toBe(true)
    expect(screen.getByText('docs/')).toBeTruthy()
    expect(screen.getByText('fileInfo.scanning:{"count":0}')).toBeTruthy()
    const rowId = current[0].id

    release()
    await waitFor(() => expect(current[0]?.folder).toBeDefined())
    expect(current[0].id).toBe(rowId)
    expect(current[0].scanning).toBeUndefined()
    expect(current[0].folder?.entries.map((item) => item.path)).toEqual([
      'docs/a.md',
    ])
    expect(isScanningSelection(current)).toBe(false)
  })

  it('stops reading a folder the user removed', async () => {
    let current: SelectedUploadFile[] = []
    render(<Harness onChange={(files) => (current = files)} />)

    const { entry, release } = gatedFolderEntry('docs', [
      fileEntry('a.md', 'a'),
    ])
    await act(async () => {
      await mocks.getFilesFromEvent?.(dropEvent(entry))
    })
    fireEvent.click(screen.getByRole('button', { name: /^fileInfo\.remove/ }))
    expect(current).toEqual([])

    await act(async () => {
      release()
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    expect(current).toEqual([])
    expect(mocks.toastError).not.toHaveBeenCalled()
  })

  it('drops scanning rows when the fields unmount, e.g. on a source switch', async () => {
    let current: SelectedUploadFile[] = []
    function Page({ shown }: { shown: boolean }) {
      const [files, setFiles] = useState<SelectedUploadFile[]>([])
      current = files
      return shown ? (
        <UploadResourceFields
          files={files}
          onFilesChange={setFiles}
          t={echoT}
          filters={NO_FILTERS}
          limits={LIMITS}
        />
      ) : null
    }
    const { rerender } = render(<Page shown />)
    const { entry, release } = gatedFolderEntry('docs', [
      fileEntry('a.md', 'a'),
    ])
    await act(async () => {
      await mocks.getFilesFromEvent?.(dropEvent(entry))
    })
    expect(isScanningSelection(current)).toBe(true)

    rerender(<Page shown={false} />)
    expect(current).toEqual([])
    await act(async () => {
      release()
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    expect(current).toEqual([])
  })

  it('passes drag-over items and input picks straight through', async () => {
    render(<Harness onChange={() => {}} />)
    const file = new File(['a'], 'a.md')

    const dragged = await mocks.getFilesFromEvent?.({
      type: 'dragenter',
      dataTransfer: { items: [{ kind: 'file' }, { kind: 'string' }] },
    })
    expect(dragged).toHaveLength(1)
    expect(
      await mocks.getFilesFromEvent?.({
        type: 'change',
        target: { files: [file] },
      }),
    ).toEqual([file])
  })

  it('opens the folder button with showDirectoryPicker when available', async () => {
    let current: SelectedUploadFile[] = []
    render(<Harness onChange={(files) => (current = files)} />)
    const inputClick = vi.spyOn(screen.getByTestId('folder-input'), 'click')
    vi.stubGlobal(
      'showDirectoryPicker',
      vi.fn().mockResolvedValue({
        kind: 'directory',
        name: 'notes',
        values: async function* () {
          yield {
            kind: 'file',
            name: 'n.md',
            getFile: async () => new File(['n'], 'n.md'),
          }
        },
      }),
    )

    fireEvent.click(
      screen.getByRole('button', { name: /^dropzone\.selectFolder/ }),
    )

    await waitFor(() => expect(current[0]?.folder).toBeDefined())
    expect(current[0].folder?.entries.map((item) => item.path)).toEqual([
      'notes/n.md',
    ])
    expect(inputClick).not.toHaveBeenCalled()
  })

  it('falls back to the folder input when the picker is missing or refused', async () => {
    render(<Harness onChange={() => {}} />)
    const inputClick = vi
      .spyOn(screen.getByTestId('folder-input'), 'click')
      .mockImplementation(() => {})
    const button = screen.getByRole('button', {
      name: /^dropzone\.selectFolder/,
    })

    fireEvent.click(button)
    await waitFor(() => expect(inputClick).toHaveBeenCalledTimes(1))

    vi.stubGlobal(
      'showDirectoryPicker',
      vi.fn().mockRejectedValue(new DOMException('frame', 'SecurityError')),
    )
    fireEvent.click(button)
    await waitFor(() => expect(inputClick).toHaveBeenCalledTimes(2))
  })

  it('removes a folder that cannot be read and says so', async () => {
    let current: SelectedUploadFile[] = []
    render(<Harness onChange={(files) => (current = files)} />)
    const broken = {
      name: 'locked',
      isDirectory: true,
      isFile: false,
      createReader: () => ({
        readEntries: (_resolve: unknown, reject: (error: Error) => void) =>
          reject(new Error('denied')),
      }),
    } as unknown as FileSystemDirectoryEntry

    await act(async () => {
      await mocks.getFilesFromEvent?.(dropEvent(broken))
    })

    await waitFor(() =>
      expect(mocks.toastError).toHaveBeenCalledWith(
        'folderReadFailed:{"name":"locked"}',
        { duration: 2500 },
      ),
    )
    expect(current).toEqual([])
  })
})
