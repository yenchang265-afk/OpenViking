import { fileTypeFromBlob } from 'file-type'
import { FileIcon, FolderUp, Upload } from 'lucide-react'
import type { TFunction } from 'i18next'
import { useCallback, useRef } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { useDropzone } from 'react-dropzone'
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

export type SelectedUploadFile = {
  id: string
  /** The file to upload; for a folder, only a label carrying its name. */
  file: File
  fileType: string | null
  /** Set for a folder, which is uploaded file by file (not zipped). */
  folder?: FolderGroup
  /** The folder before filtering, so changed options can re-filter it. */
  source?: FolderSource
}

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

export function UploadResourceFields({
  files,
  onFilesChange,
  t,
  limits,
  filters,
}: UploadResourceFieldsProps) {
  const filesRef = useRef(files)
  filesRef.current = files

  const updateFiles = useCallback(
    (update: (currentFiles: SelectedUploadFile[]) => SelectedUploadFile[]) => {
      const nextFiles = update(filesRef.current)
      filesRef.current = nextFiles
      onFilesChange(nextFiles)
    },
    [onFilesChange],
  )

  const addFiles = useCallback(
    (nextFiles: File[]) => {
      void (async () => {
        const accepted: SelectedUploadFile[] = []
        const { looseFiles, folders } = groupFolderFiles(nextFiles)

        for (const folder of folders) {
          const packaged = packageFolder(
            await loadFolderSource(folder),
            filters,
            t,
            limits,
          )
          if (packaged) accepted.push(packaged)
        }

        for (const file of looseFiles) {
          if (isBlockedFile(file.name)) {
            toast.error(t('fileBlocked', { name: file.name }), {
              duration: 2500,
            })
            continue
          }
          if (file.size > limits.maxFileBytes) {
            toast.error(
              t('fileTooLarge', {
                name: file.name,
                size: formatFileSize(limits.maxFileBytes),
              }),
              { duration: 2500 },
            )
            continue
          }
          if (await isEmptyFile(file)) {
            toast.error(t('fileEmpty', { name: file.name }), {
              duration: 2500,
            })
            continue
          }
          accepted.push({
            id: createLocalFileId(),
            file,
            fileType: await detectFileType(file),
          })
        }

        updateFiles((currentFiles) => {
          const remainingSlots = Math.max(
            MAX_UPLOAD_FILES - currentFiles.length,
            0,
          )
          if (accepted.length > remainingSlots) {
            toast(t('tooManyFiles', { count: MAX_UPLOAD_FILES }), {
              duration: 2500,
            })
          }
          return [...currentFiles, ...accepted.slice(0, remainingSlots)]
        })
      })()
    },
    [filters, limits, t, updateFiles],
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: addFiles,
    multiple: true,
  })

  const folderInputRef = useRef<HTMLInputElement>(null)

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
              folderInputRef.current?.click()
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
                <FileIcon className="size-5 text-muted-foreground" />
              </div>
              <p className="min-w-0 flex-1 truncate text-sm font-medium">
                {item.folder ? `${item.folder.name}/` : item.file.name}
              </p>
              <span className="shrink-0 text-xs text-muted-foreground">
                {item.folder
                  ? `${t('fileInfo.folderFiles', { count: item.folder.entries.length })} · `
                  : null}
                {formatFileSize(selectedUploadSize(item))}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="shrink-0 text-muted-foreground hover:text-foreground"
                onClick={() =>
                  updateFiles((currentFiles) =>
                    currentFiles.filter(({ id }) => id !== item.id),
                  )
                }
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
