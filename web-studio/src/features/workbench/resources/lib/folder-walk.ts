import { createGitignore } from './folder-filter'
import type { FolderSource } from './folder-filter'
import { isHiddenPath } from './folder-upload'
import type { FolderEntry } from './folder-upload'
import { isBlockedFile } from './upload'

/**
 * A folder read lazily, one level at a time. Both browser folder APIs fit it:
 * drag-drop entries (webkitGetAsEntry) and showDirectoryPicker handles.
 * Unlike `<input webkitdirectory>`, which lists the whole tree before the page
 * sees anything, the walk can skip ignored folders without opening them.
 */
export type FolderNode = {
  name: string
  list: () => Promise<FolderChild[]>
}

export type FolderChild =
  | { kind: 'file'; name: string; getFile: () => Promise<File> }
  | { kind: 'directory'; name: string; folder: FolderNode }

export type WalkFolderOptions = {
  signal?: AbortSignal
  /** Called after each folder level with the number of files kept so far. */
  onProgress?: (filesFound: number) => void
}

/**
 * Read a folder into the same FolderSource that groupFolderFiles +
 * loadFolderSource build from a flat file list: hidden and blocked files
 * dropped, .gitignore applied. Hidden and gitignored folders are skipped
 * without being read, so their files are not in `skippedCount`.
 */
export async function walkFolder(
  root: FolderNode,
  { signal, onProgress }: WalkFolderOptions = {},
): Promise<FolderSource> {
  const gitignore = createGitignore()
  const entries: FolderEntry[] = []
  let skippedCount = 0

  // Depth first, folders one at a time: a folder's .gitignore is added before
  // anything below it is checked, as git reads them.
  const visit = async (folder: FolderNode, rel: string): Promise<void> => {
    signal?.throwIfAborted()
    const children = [...(await folder.list())].sort((a, b) =>
      a.name.localeCompare(b.name),
    )
    const ignoreFile = children.find(
      (child) => child.kind === 'file' && child.name === '.gitignore',
    )
    if (ignoreFile?.kind === 'file') {
      try {
        gitignore.add(await (await ignoreFile.getFile()).text(), rel)
      } catch {
        // An unreadable .gitignore only means fewer files are skipped.
      }
    }

    const files: Array<{
      path: string
      child: FolderChild & { kind: 'file' }
    }> = []
    const folders: Array<{ rel: string; folder: FolderNode }> = []
    for (const child of children) {
      const childRel = rel ? `${rel}/${child.name}` : child.name
      const path = `${root.name}/${childRel}`
      if (child.kind === 'directory') {
        if (!isHiddenPath(path) && !gitignore.ignores(`${childRel}/`)) {
          folders.push({ rel: childRel, folder: child.folder })
        }
      } else if (
        isHiddenPath(path) ||
        isBlockedFile(child.name) ||
        gitignore.ignores(childRel)
      ) {
        skippedCount += 1
      } else {
        files.push({ path, child })
      }
    }

    entries.push(
      ...(await Promise.all(
        files.map(async ({ path, child }) => ({
          path,
          file: await child.getFile(),
        })),
      )),
    )
    signal?.throwIfAborted()
    onProgress?.(entries.length)
    for (const next of folders) await visit(next.folder, next.rel)
  }

  await visit(root, '')
  return { name: root.name, entries, skippedCount }
}

function readEntryBatch(
  reader: FileSystemDirectoryReader,
): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => reader.readEntries(resolve, reject))
}

/** A dropped folder (DataTransferItem.webkitGetAsEntry) as a FolderNode. */
export function folderFromEntry(entry: FileSystemDirectoryEntry): FolderNode {
  return {
    name: entry.name,
    list: async () => {
      const reader = entry.createReader()
      const all: FileSystemEntry[] = []
      // readEntries returns at most ~100 entries per call; empty means done.
      for (let batch = await readEntryBatch(reader); batch.length; ) {
        all.push(...batch)
        batch = await readEntryBatch(reader)
      }
      return all.map((child): FolderChild => {
        if (child.isDirectory) {
          return {
            kind: 'directory',
            name: child.name,
            folder: folderFromEntry(child as FileSystemDirectoryEntry),
          }
        }
        const fileEntry = child as FileSystemFileEntry
        return {
          kind: 'file',
          name: child.name,
          getFile: () =>
            new Promise((resolve, reject) => fileEntry.file(resolve, reject)),
        }
      })
    },
  }
}

/** The part of the File System Access API the walk uses (Chromium only). */
type DirectoryHandle = {
  kind: 'directory'
  name: string
  values: () => AsyncIterable<DirectoryHandle | FileHandle>
}

type FileHandle = {
  kind: 'file'
  name: string
  getFile: () => Promise<File>
}

type DirectoryPickerGlobal = {
  showDirectoryPicker?: (options?: {
    mode?: 'read'
  }) => Promise<DirectoryHandle>
}

function directoryPicker(): DirectoryPickerGlobal['showDirectoryPicker'] {
  return (globalThis as DirectoryPickerGlobal).showDirectoryPicker
}

export function folderFromHandle(handle: DirectoryHandle): FolderNode {
  return {
    name: handle.name,
    list: async () => {
      const children: FolderChild[] = []
      for await (const child of handle.values()) {
        children.push(
          child.kind === 'directory'
            ? {
                kind: 'directory',
                name: child.name,
                folder: folderFromHandle(child),
              }
            : {
                kind: 'file',
                name: child.name,
                getFile: () => child.getFile(),
              },
        )
      }
      return children
    },
  }
}

/** Whether this browser can open a folder without listing it all first. */
export function canPickFolder(): boolean {
  return typeof directoryPicker() === 'function'
}

/**
 * Ask for a folder with showDirectoryPicker. Resolves null when the user
 * cancels; rejects when the browser refuses (e.g. a cross-origin frame).
 */
export async function pickFolder(): Promise<FolderNode | null> {
  const picker = directoryPicker()
  // eslint-disable-next-line studio-i18n/no-literal-message -- callers check canPickFolder() first and fall back to the file input on any rejection
  if (!picker) throw new Error('showDirectoryPicker is not supported')
  try {
    return folderFromHandle(await picker.call(globalThis, { mode: 'read' }))
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return null
    }
    throw error
  }
}

/** What a drop carried: plain files for the usual checks, folders to walk. */
export type DroppedItems = {
  files: File[]
  folders: FolderNode[]
}

/**
 * Split a drop into files and folders. Must run while the drop event is being
 * dispatched: DataTransfer items are unreadable once it returns.
 */
export function readDrop(dataTransfer: DataTransfer): DroppedItems {
  const items = Array.from(dataTransfer.items).filter(
    (item) => item.kind === 'file',
  )
  if (!items.length || typeof items[0].webkitGetAsEntry !== 'function') {
    return { files: Array.from(dataTransfer.files), folders: [] }
  }
  const dropped: DroppedItems = { files: [], folders: [] }
  for (const item of items) {
    const entry = item.webkitGetAsEntry()
    if (entry?.isDirectory) {
      dropped.folders.push(folderFromEntry(entry as FileSystemDirectoryEntry))
      continue
    }
    const file = item.getAsFile()
    if (file) dropped.files.push(file)
  }
  return dropped
}
