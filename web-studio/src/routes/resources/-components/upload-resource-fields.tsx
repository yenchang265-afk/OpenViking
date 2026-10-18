import { fileTypeFromBlob } from 'file-type'
import { FileIcon, FolderUp, Loader2Icon, Upload } from 'lucide-react'
import type { TFunction } from 'i18next'
import { useCallback, useEffect, useRef } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { useDropzone } from 'react-dropzone'
import type { DropEvent } from 'react-dropzone'
import { toast } from 'sonner'

import { Button } from '#/components/ui/button'
import { cn } from '#/lib/utils'
import {
  MAX_UPLOAD_FILES,
  formatFileSize,
  isBlockedFile,
  isEmptyFile,
} from '../-lib/upload'
import type { UploadLimits } from '../-lib/upload-limits'
import { filterFolder, loadFolderSource } from '../-lib/folder-filter'
import type { FolderFilters, FolderSource } from '../-lib/folder-filter'
import { getFolderSize, groupFolderFiles } from '../-lib/folder-upload'
import type { FolderGroup } from '../-lib/folder-upload'
import {
  canPickFolder,
  pickFolder,
  readDrop,
  walkFolder,
} from '../-lib/folder-walk'
import type { FolderNode, WalkFolderOptions } from '../-lib/folder-walk'

export type SelectedUploadFile = {
  id: string
  /** The file to upload; for a folder, only a label carrying its name. */
  file: File
  fileType: string | null
  /** Set for a folder, which is uploaded file by file (not zipped). */
  folder?: FolderGroup
  /** The folder before filtering, so changed options can re-filter it. */
  source?: FolderSource
  /** Set while a picked folder is still being read; it cannot be uploaded yet. */
  scanning?: { filesFound: number }
}

/** Whether any selected folder is still being read. */
export function isScanningSelection(files: SelectedUploadFile[]): boolean {
  return files.some((item) => item.scanning)
}

/** Reads one picked folder; the row shows as scanning until it settles. */
type FolderScan = {
  name: string
  read: (options: WalkFolderOptions) => Promise<FolderSource>
}

// Progress re-renders the whole list, so a big folder updates it at most this often.
const SCAN_PROGRESS_INTERVAL_MS = 200

export function selectedUploadSize(item: SelectedUploadFile): number {
  return item.folder ? getFolderSize(item.folder) : item.file.size
}

type UploadResourceFieldsProps = {
  files: SelectedUploadFile[]
  onFilesChange: Dispatch<SetStateAction<SelectedUploadFile[]>>
  t: TFunction<'addResource'>
  /** Server upload limits, from GET /api/v1/uploads/limits. */
  limits: UploadLimits
  /** Ignore dirs / include / exclude, applied with the folder's .gitignore. */
  filters: FolderFilters
}

function createLocalFileId(): string {
  if (
    typeof crypto !== 'undefined' &&
    typeof crypto.randomUUID === 'function'
  ) {
    return crypto.randomUUID()
  }
  return `local-file-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

async function detectFileType(file: File): Promise<string | null> {
  try {
    const result = await fileTypeFromBlob(file)
    return result?.mime ?? null
  } catch {
    return null
  }
}

/** The first upload limit a folder breaks, as a message; null when it fits. */
export function folderLimitError(
  folder: FolderGroup,
  t: TFunction<'addResource'>,
  limits: UploadLimits,
): string | null {
  if (folder.entries.length === 0) {
    return t('folderEmpty', { name: folder.name })
  }
  const oversized = folder.entries.find(
    ({ file }) => file.size > limits.maxFileBytes,
  )
  if (oversized) {
    return t('fileTooLarge', {
      name: oversized.path,
      size: formatFileSize(limits.maxFileBytes),
    })
  }
  if (folder.entries.length > limits.maxFiles) {
    return t('folderTooManyFiles', {
      name: `${folder.name}/`,
      files: folder.entries.length.toLocaleString(),
      max: limits.maxFiles.toLocaleString(),
    })
  }
  const folderSize = getFolderSize(folder)
  if (folderSize > limits.maxSessionBytes) {
    return t('folderTooLarge', {
      name: `${folder.name}/`,
      size: formatFileSize(folderSize),
      max: formatFileSize(limits.maxSessionBytes),
    })
  }
  return null
}

/** Re-apply the folder filters to every selected folder (options changed). */
export function refilterSelectedFiles(
  files: SelectedUploadFile[],
  filters: FolderFilters,
): SelectedUploadFile[] {
  return files.map((item) =>
    item.source
      ? { ...item, folder: filterFolder(item.source, filters) }
      : item,
  )
}

function packageFolder(
  source: FolderSource,
  filters: FolderFilters,
  t: TFunction<'addResource'>,
  limits: UploadLimits,
): SelectedUploadFile | null {
  const folder = filterFolder(source, filters)
  if (folder.skippedCount > 0) {
    toast(
      t('folderSkipped', { name: folder.name, count: folder.skippedCount }),
      {
        duration: 2500,
      },
    )
  }
  const error = folderLimitError(folder, t, limits)
  if (error) {
    toast.error(error, { duration: 2500 })
    return null
  }
  return {
    id: createLocalFileId(),
    file: new File([], folder.name),
    fileType: null,
    folder,
    source,
  }
}

/** A loose file that passes the upload checks, or null after a toast. */
async function checkLooseFile(
  file: File,
  t: TFunction<'addResource'>,
  limits: UploadLimits,
): Promise<SelectedUploadFile | null> {
  if (isBlockedFile(file.name)) {
    toast.error(t('fileBlocked', { name: file.name }), { duration: 2500 })
    return null
  }
  if (file.size > limits.maxFileBytes) {
    toast.error(
      t('fileTooLarge', {
        name: file.name,
        size: formatFileSize(limits.maxFileBytes),
      }),
      { duration: 2500 },
    )
    return null
  }
  if (await isEmptyFile(file)) {
    toast.error(t('fileEmpty', { name: file.name }), { duration: 2500 })
    return null
  }
  return {
    id: createLocalFileId(),
    file,
    fileType: await detectFileType(file),
  }
}

function walkScan(folder: FolderNode): FolderScan {
  return { name: folder.name, read: (options) => walkFolder(folder, options) }
}

export function UploadResourceFields({
  files,
  onFilesChange,
  t,
  limits,
  filters,
}: UploadResourceFieldsProps) {
  const filesRef = useRef(files)
  filesRef.current = files
  // A scan settles after the options may have changed; package it with the latest.
  const latestRef = useRef({ filters, limits, t })
  latestRef.current = { filters, limits, t }
  // `listed` once the row reached `files`, so a scan whose row left it is stopped.
  const scansRef = useRef(
    new Map<string, { controller: AbortController; listed: boolean }>(),
  )

  // Functional, so a parent update queued before the next render (a reset,
  // a re-filter) is not overwritten by a list built from stale props.
  const updateFiles = useCallback(
    (update: (currentFiles: SelectedUploadFile[]) => SelectedUploadFile[]) => {
      onFilesChange((currentFiles) => {
        const nextFiles = update(currentFiles)
        filesRef.current = nextFiles
        return nextFiles
      })
    },
    [onFilesChange],
  )
  const updateFilesRef = useRef(updateFiles)
  updateFilesRef.current = updateFiles

  // Stop reading folders whose rows were removed, reset or submitted.
  useEffect(() => {
    const ids = new Set(files.map((item) => item.id))
    for (const [id, scan] of scansRef.current) {
      if (ids.has(id)) scan.listed = true
      else if (scan.listed) scan.controller.abort()
    }
  }, [files])

  // The selection outlives this component (e.g. switching to a remote
  // source), so drop the rows whose scans unmounting stops.
  useEffect(() => {
    const scans = scansRef.current
    const latestUpdateFiles = updateFilesRef
    return () => {
      if (!scans.size) return
      const stopped = new Set(scans.keys())
      for (const scan of scans.values()) scan.controller.abort()
      scans.clear()
      latestUpdateFiles.current((currentFiles) =>
        currentFiles.filter((item) => !stopped.has(item.id)),
      )
    }
  }, [])

  /** Append within MAX_UPLOAD_FILES; returns the items that fit. */
  const appendFiles = useCallback(
    (items: SelectedUploadFile[]): SelectedUploadFile[] => {
      if (!items.length) return []
      const remainingSlots = Math.max(
        MAX_UPLOAD_FILES - filesRef.current.length,
        0,
      )
      if (items.length > remainingSlots) {
        toast(
          latestRef.current.t('tooManyFiles', { count: MAX_UPLOAD_FILES }),
          { duration: 2500 },
        )
      }
      const admitted = items.slice(0, remainingSlots)
      if (admitted.length) {
        updateFiles((currentFiles) => [
          ...currentFiles,
          ...admitted.slice(
            0,
            Math.max(MAX_UPLOAD_FILES - currentFiles.length, 0),
          ),
        ])
      }
      return admitted
    },
    [updateFiles],
  )

  /** Replace a row in place, or drop it; a no-op once the user removed it. */
  const settleRow = useCallback(
    (id: string, next: SelectedUploadFile | null) => {
      updateFiles((currentFiles) =>
        currentFiles.flatMap((item) =>
          item.id !== id ? [item] : next ? [next] : [],
        ),
      )
    },
    [updateFiles],
  )

  const runScan = useCallback(
    async (row: SelectedUploadFile, scan: FolderScan) => {
      const controller = new AbortController()
      scansRef.current.set(row.id, { controller, listed: false })
      let shownAt = 0
      const onProgress = (filesFound: number) => {
        const now = Date.now()
        if (now - shownAt < SCAN_PROGRESS_INTERVAL_MS) return
        shownAt = now
        updateFiles((currentFiles) =>
          currentFiles.map((item) =>
            item.id === row.id ? { ...item, scanning: { filesFound } } : item,
          ),
        )
      }
      try {
        const source = await scan.read({
          signal: controller.signal,
          onProgress,
        })
        if (controller.signal.aborted) return
        const latest = latestRef.current
        const packaged = packageFolder(
          source,
          latest.filters,
          latest.t,
          latest.limits,
        )
        settleRow(row.id, packaged && { ...packaged, id: row.id })
      } catch {
        if (controller.signal.aborted) return
        toast.error(
          latestRef.current.t('folderReadFailed', { name: scan.name }),
          {
            duration: 2500,
          },
        )
        settleRow(row.id, null)
      } finally {
        scansRef.current.delete(row.id)
      }
    },
    [settleRow, updateFiles],
  )

  /** Show a row per folder now, then read each without holding up the rest. */
  const startFolderScans = useCallback(
    (scans: FolderScan[]) => {
      const rows = appendFiles(
        scans.map(({ name }) => ({
          id: createLocalFileId(),
          file: new File([], name),
          fileType: null,
          scanning: { filesFound: 0 },
        })),
      )
      rows.forEach((row, index) => void runScan(row, scans[index]))
    },
    [appendFiles, runScan],
  )

  const addFiles = useCallback(
    (nextFiles: File[]) => {
      const { looseFiles, folders } = groupFolderFiles(nextFiles)
      startFolderScans(
        folders.map((folder) => ({
          name: folder.name,
          read: () => loadFolderSource(folder),
        })),
      )
      if (!looseFiles.length) return
      void (async () => {
        const { t: latestT, limits: latestLimits } = latestRef.current
        const checked = await Promise.all(
          looseFiles.map((file) => checkLooseFile(file, latestT, latestLimits)),
        )
        appendFiles(checked.filter((item) => item !== null))
      })()
    },
    [appendFiles, startFolderScans],
  )

  // Dropped folders are walked here rather than by react-dropzone, which
  // lists every file (node_modules, .git) before it calls onDrop.
  const getFilesFromEvent = useCallback(
    async (event: DropEvent): Promise<Array<File | DataTransferItem>> => {
      if (Array.isArray(event)) {
        return Promise.all(event.map((handle) => handle.getFile()))
      }
      if ('dataTransfer' in event && event.dataTransfer) {
        if (event.type !== 'drop') {
          return Array.from(event.dataTransfer.items).filter(
            (item) => item.kind === 'file',
          )
        }
        const dropped = readDrop(event.dataTransfer)
        startFolderScans(dropped.folders.map(walkScan))
        return dropped.files
      }
      const input = event.target as HTMLInputElement | null
      return Array.from(input?.files ?? [])
    },
    [startFolderScans],
  )

  const removeRow = useCallback(
    (id: string) => {
      updateFiles((currentFiles) =>
        currentFiles.filter((item) => item.id !== id),
      )
    },
    [updateFiles],
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: addFiles,
    getFilesFromEvent,
    multiple: true,
  })

  const folderInputRef = useRef<HTMLInputElement>(null)
  // Set once showDirectoryPicker refuses (e.g. in a cross-origin frame).
  const pickerRefusedRef = useRef(false)

  // showDirectoryPicker hands over the folder at once; other browsers list it
  // all through <input webkitdirectory> first.
  const selectFolder = useCallback(async () => {
    if (pickerRefusedRef.current || !canPickFolder()) {
      folderInputRef.current?.click()
      return
    }
    try {
      const folder = await pickFolder()
      if (folder) startFolderScans([walkScan(folder)])
    } catch {
      // The refused picker may have used up the click, so this one can be
      // blocked; the next click then goes straight to the input.
      pickerRefusedRef.current = true
      folderInputRef.current?.click()
    }
  }, [startFolderScans])

  return (
    <div className="space-y-3">
      <div
        {...getRootProps()}
        className={cn(
          'relative rounded-lg border-2 border-dashed p-8 text-center transition-colors',
          isDragActive
            ? 'cursor-pointer border-primary bg-primary/5'
            : 'cursor-pointer border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/30',
        )}
      >
        <input {...getInputProps()} />
        <div className="space-y-2">
          <Upload className="mx-auto size-10 text-muted-foreground/60" />
          <p className="text-sm font-medium">{t('dropzone.title')}</p>
          <p className="text-xs text-muted-foreground">{t('dropzone.hint')}</p>
          <p className="text-xs text-muted-foreground/70">
            {t('dropzone.supportedFormats')}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-1"
            onClick={(event) => {
              event.stopPropagation()
              void selectFolder()
            }}
          >
            <FolderUp className="size-4" />
            {t('dropzone.selectFolder')}
          </Button>
        </div>
      </div>
      <input
        ref={folderInputRef}
        type="file"
        className="hidden"
        data-testid="folder-input"
        {...{ webkitdirectory: '' }}
        onChange={(event) => {
          const picked = Array.from(event.target.files ?? [])
          event.target.value = ''
          if (picked.length) addFiles(picked)
        }}
      />

      {files.length ? (
        <div className="overflow-hidden rounded-lg border border-border/60 bg-muted/10">
          {files.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-3 border-b border-border/50 px-4 py-3 last:border-b-0"
            >
              <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted">
                {item.scanning ? (
                  <Loader2Icon className="size-5 animate-spin text-muted-foreground" />
                ) : (
                  <FileIcon className="size-5 text-muted-foreground" />
                )}
              </div>
              <p className="min-w-0 flex-1 truncate text-sm font-medium">
                {item.folder || item.scanning
                  ? `${item.file.name}/`
                  : item.file.name}
              </p>
              <span
                className="shrink-0 text-xs text-muted-foreground"
                aria-live={item.scanning ? 'polite' : undefined}
              >
                {item.scanning ? (
                  t('fileInfo.scanning', { count: item.scanning.filesFound })
                ) : (
                  <>
                    {item.folder
                      ? `${t('fileInfo.folderFiles', { count: item.folder.entries.length })} · `
                      : null}
                    {formatFileSize(selectedUploadSize(item))}
                  </>
                )}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="shrink-0 text-muted-foreground hover:text-foreground"
                onClick={() => removeRow(item.id)}
              >
                {t('fileInfo.remove')}
              </Button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
