import { isBlockedFile } from './upload'
import { createStoredZip } from './zip'

export type FolderEntry = {
  path: string
  file: File
}

export type FolderGroup = {
  name: string
  entries: FolderEntry[]
  skippedCount: number
}

export type GroupedFiles = {
  looseFiles: File[]
  folders: FolderGroup[]
}

// react-dropzone reports "./a.md" for loose files, "/dir/a.md" for dropped
// folders, and webkitRelativePath ("dir/a.md") for directory-input picks.
export function getRelativePath(file: File): string {
  const withPath = file as File & { path?: unknown }
  const raw =
    typeof withPath.path === 'string' && withPath.path
      ? withPath.path
      : file.webkitRelativePath || file.name
  return raw.replace(/^\.?\/+/, '')
}

// Installed dependencies and build output: regenerated from source, rarely
// worth indexing, and often tens of thousands of files (a repo checkout with
// node_modules or a Rust target/ dir blows past the server's upload limits).
const GENERATED_DIRS = new Set([
  'node_modules',
  '__pycache__',
  'venv',
  'target',
  'build',
  'dist',
])

function isHiddenPath(path: string): boolean {
  return path.split('/').some((segment) => segment.startsWith('.'))
}

/** True below the picked folder only, and only for directories. */
function isGeneratedPath(path: string): boolean {
  return path
    .split('/')
    .slice(1, -1)
    .some((segment) => GENERATED_DIRS.has(segment))
}

export function groupFolderFiles(files: File[]): GroupedFiles {
  const looseFiles: File[] = []
  const folders = new Map<string, FolderGroup>()

  for (const file of files) {
    const path = getRelativePath(file)
    const slash = path.indexOf('/')
    if (slash <= 0) {
      looseFiles.push(file)
      continue
    }

    const name = path.slice(0, slash)
    const group = folders.get(name) ?? { name, entries: [], skippedCount: 0 }
    folders.set(name, group)

    if (
      isHiddenPath(path) ||
      isGeneratedPath(path) ||
      isBlockedFile(file.name)
    ) {
      group.skippedCount += 1
      continue
    }
    group.entries.push({ path, file })
  }

  return { looseFiles, folders: [...folders.values()] }
}

export function getFolderSize(folder: FolderGroup): number {
  return folder.entries.reduce((total, entry) => total + entry.file.size, 0)
}

export async function zipFolder(folder: FolderGroup): Promise<File> {
  const entries = await Promise.all(
    folder.entries.map(async ({ path, file }) => ({
      path,
      data: new Uint8Array(await file.arrayBuffer()),
    })),
  )
  const blob = createStoredZip(entries)
  return new File([blob], `${folder.name}.zip`, { type: 'application/zip' })
}
