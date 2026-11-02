import { afterEach, describe, expect, it, vi } from 'vitest'

import { loadFolderSource } from './folder-filter'
import { groupFolderFiles } from './folder-upload'
import {
  canPickFolder,
  folderFromEntry,
  folderFromHandle,
  pickFolder,
  readDrop,
  walkFolder,
} from './folder-walk'
import type { FolderChild, FolderNode } from './folder-walk'

/** Contents by path below the root; a folder is any path prefix ending in '/'. */
type Tree = Record<string, string>

/** A FolderNode over `tree`, recording which folders were listed. */
function fakeFolder(
  name: string,
  tree: Tree,
  listed: string[] = [],
  prefix = '',
): FolderNode {
  return {
    name,
    list: async () => {
      listed.push(prefix)
      const children = new Map<string, FolderChild>()
      for (const [path, content] of Object.entries(tree)) {
        if (!path.startsWith(prefix)) continue
        const rest = path.slice(prefix.length)
        const slash = rest.indexOf('/')
        const childName = slash < 0 ? rest : rest.slice(0, slash)
        if (children.has(childName)) continue
        children.set(
          childName,
          slash < 0
            ? {
                kind: 'file',
                name: childName,
                getFile: async () => new File([content], childName),
              }
            : {
                kind: 'directory',
                name: childName,
                folder: fakeFolder(
                  childName,
                  tree,
                  listed,
                  `${prefix}${childName}/`,
                ),
              },
        )
      }
      return [...children.values()]
    },
  }
}

/** The same tree as the flat file list `<input webkitdirectory>` gives. */
function flatFiles(name: string, tree: Tree): File[] {
  return Object.entries(tree).map(([path, content]) =>
    Object.defineProperty(
      new File([content], path.slice(path.lastIndexOf('/') + 1)),
      'webkitRelativePath',
      { value: `${name}/${path}` },
    ),
  )
}

const REPO: Tree = {
  '.gitignore': 'node_modules/\n*.log\n',
  '.git/HEAD': 'ref',
  'README.md': '# repo',
  'debug.log': 'x',
  'app.exe': 'bin',
  'node_modules/x/index.js': 'js',
  'docs/.gitignore': 'drafts/\n!keep.log\n',
  'docs/guide.md': 'guide',
  'docs/keep.log': 'kept',
  'docs/drafts/wip.md': 'wip',
  'src/main.ts': 'main',
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('walkFolder', () => {
  it('keeps the same files as reading the full listing', async () => {
    const walked = await walkFolder(fakeFolder('repo', REPO))
    const [listed] = groupFolderFiles(flatFiles('repo', REPO)).folders
    const loaded = await loadFolderSource(listed)

    const paths = (entries: Array<{ path: string }>) =>
      entries.map((entry) => entry.path).sort()
    expect(paths(walked.entries)).toEqual(paths(loaded.entries))
    expect(paths(walked.entries)).toEqual([
      'repo/README.md',
      'repo/docs/guide.md',
      'repo/docs/keep.log',
      'repo/src/main.ts',
    ])
    expect(walked.name).toBe('repo')
    expect(await walked.entries[0].file.text()).toBeTruthy()
  })

  it('never opens hidden or gitignored folders', async () => {
    const listed: string[] = []
    const walked = await walkFolder(fakeFolder('repo', REPO, listed))

    expect(listed.sort()).toEqual(['', 'docs/', 'src/'])
    // .gitignore x2, debug.log, app.exe; the pruned folders' files are not counted.
    expect(walked.skippedCount).toBe(4)
  })

  it('reports progress per folder and stops when aborted', async () => {
    const onProgress = vi.fn()
    await walkFolder(fakeFolder('repo', REPO), { onProgress })
    expect(onProgress).toHaveBeenLastCalledWith(4)

    const controller = new AbortController()
    const aborting = walkFolder(fakeFolder('repo', REPO), {
      signal: controller.signal,
      onProgress: () => controller.abort(),
    })
    await expect(aborting).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('treats an unreadable .gitignore as no rules', async () => {
    const root: FolderNode = {
      name: 'repo',
      list: async () => [
        {
          kind: 'file',
          name: '.gitignore',
          getFile: () => Promise.reject(new Error('denied')),
        },
        {
          kind: 'file',
          name: 'a.md',
          getFile: async () => new File(['a'], 'a.md'),
        },
      ],
    }
    const walked = await walkFolder(root)
    expect(walked.entries.map((entry) => entry.path)).toEqual(['repo/a.md'])
  })
})

/** A FileSystemDirectoryEntry whose reader returns `children` in batches. */
function fakeDirectoryEntry(
  name: string,
  children: FileSystemEntry[],
  batchSize = 2,
): FileSystemDirectoryEntry {
  return {
    name,
    isDirectory: true,
    isFile: false,
    createReader: () => {
      let offset = 0
      return {
        readEntries: (resolve: (entries: FileSystemEntry[]) => void) => {
          const batch = children.slice(offset, offset + batchSize)
          offset += batchSize
          resolve(batch)
        },
      }
    },
  } as unknown as FileSystemDirectoryEntry
}

function fakeFileEntry(name: string, content: string): FileSystemFileEntry {
  return {
    name,
    isDirectory: false,
    isFile: true,
    file: (resolve: (file: File) => void) => resolve(new File([content], name)),
  } as unknown as FileSystemFileEntry
}

describe('folderFromEntry', () => {
  it('reads every batch and walks sub-folders', async () => {
    const entry = fakeDirectoryEntry('docs', [
      fakeFileEntry('a.md', 'a'),
      fakeFileEntry('b.md', 'b'),
      fakeFileEntry('c.md', 'c'),
      fakeDirectoryEntry('sub', [fakeFileEntry('d.md', 'd')]),
    ])
    const walked = await walkFolder(folderFromEntry(entry))
    expect(walked.entries.map((item) => item.path)).toEqual([
      'docs/a.md',
      'docs/b.md',
      'docs/c.md',
      'docs/sub/d.md',
    ])
    expect(await walked.entries[3].file.text()).toBe('d')
  })
})

type FakeHandle =
  | { kind: 'file'; name: string; getFile: () => Promise<File> }
  | { kind: 'directory'; name: string; values: () => AsyncIterable<FakeHandle> }

function fakeDirectoryHandle(name: string, children: FakeHandle[]): FakeHandle {
  return {
    kind: 'directory',
    name,
    values: async function* () {
      yield* children
    },
  }
}

function fakeFileHandle(name: string, content: string): FakeHandle {
  return { kind: 'file', name, getFile: async () => new File([content], name) }
}

describe('folderFromHandle', () => {
  it('walks a showDirectoryPicker handle', async () => {
    const handle = fakeDirectoryHandle('notes', [
      fakeFileHandle('a.md', 'a'),
      fakeDirectoryHandle('sub', [fakeFileHandle('b.md', 'b')]),
    ])
    const walked = await walkFolder(
      folderFromHandle(handle as Parameters<typeof folderFromHandle>[0]),
    )
    expect(walked.entries.map((item) => item.path)).toEqual([
      'notes/a.md',
      'notes/sub/b.md',
    ])
  })
})

describe('pickFolder', () => {
  it('is unavailable without showDirectoryPicker', async () => {
    expect(canPickFolder()).toBe(false)
    await expect(pickFolder()).rejects.toThrow('not supported')
  })

  it('opens the picked folder and resolves null on cancel', async () => {
    const picker = vi
      .fn()
      .mockResolvedValueOnce(fakeDirectoryHandle('picked', []))
      .mockRejectedValueOnce(new DOMException('cancelled', 'AbortError'))
      .mockRejectedValueOnce(new DOMException('frame', 'SecurityError'))
    vi.stubGlobal('showDirectoryPicker', picker)

    expect(canPickFolder()).toBe(true)
    expect((await pickFolder())?.name).toBe('picked')
    expect(picker).toHaveBeenCalledWith({ mode: 'read' })
    expect(await pickFolder()).toBeNull()
    await expect(pickFolder()).rejects.toMatchObject({ name: 'SecurityError' })
  })
})

function fakeItem(
  entry: FileSystemEntry | null,
  file: File | null,
  kind = 'file',
): DataTransferItem {
  return {
    kind,
    webkitGetAsEntry: () => entry,
    getAsFile: () => file,
  } as unknown as DataTransferItem
}

describe('readDrop', () => {
  it('splits dropped folders from files and ignores text items', () => {
    const loose = new File(['a'], 'a.md')
    const dropped = readDrop({
      items: [
        fakeItem(fakeDirectoryEntry('docs', []), null),
        fakeItem(fakeFileEntry('a.md', 'a'), loose),
        fakeItem(null, null, 'string'),
      ],
      files: [],
    } as unknown as DataTransfer)

    expect(dropped.files).toEqual([loose])
    expect(dropped.folders.map((folder) => folder.name)).toEqual(['docs'])
  })

  it('falls back to the plain file list without the entries API', () => {
    const file = new File(['a'], 'a.md')
    const dropped = readDrop({
      items: [{ kind: 'file', getAsFile: () => file }],
      files: [file],
    } as unknown as DataTransfer)
    expect(dropped).toEqual({ files: [file], folders: [] })
  })
})
