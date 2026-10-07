import { fileTypeFromBlob } from 'file-type'
import { FileIcon, FolderUp, Upload } from 'lucide-react'
import type { TFunction } from 'i18next'
import { useCallback, useRef } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { useDropzone } from 'react-dropzone'
import { toast } from 'sonner'

import { Button } from '#/components/ui/button'
import { cn } from '#/lib/utils'
import { MAX_UPLOAD_FILES, formatFileSize, isBlockedFile } from '../-lib/upload'
import { folderUploadLimitBytes } from '../-lib/upload-limits'
import type { UploadLimits } from '../-lib/upload-limits'
import {
  getFolderSize,
  groupFolderFiles,
  zipFolder,
} from '../-lib/folder-upload'
import type { FolderGroup } from '../-lib/folder-upload'

export type SelectedUploadFile = {
  id: string
  file: File
  fileType: string | null
}

type UploadResourceFieldsProps = {
  files: SelectedUploadFile[]
  onFilesChange: Dispatch<SetStateAction<SelectedUploadFile[]>>
  t: TFunction<'addResource'>
  /** Server upload limits, from GET /api/v1/uploads/limits. */
  limits: UploadLimits
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

async function packageFolder(
  folder: FolderGroup,
  t: TFunction<'addResource'>,
  maxBytes: number,
): Promise<SelectedUploadFile | null> {
  if (folder.skippedCount > 0) {
    toast(
      t('folderSkipped', { name: folder.name, count: folder.skippedCount }),
      {
        duration: 2500,
      },
    )
  }
  if (folder.entries.length === 0) {
    toast.error(t('folderEmpty', { name: folder.name }), { duration: 2500 })
    return null
  }
  if (getFolderSize(folder) > maxBytes) {
    toast.error(
      t('fileTooLarge', {
        name: `${folder.name}/`,
        size: formatFileSize(maxBytes),
      }),
      { duration: 2500 },
    )
    return null
  }
  try {
    return {
      id: createLocalFileId(),
      file: await zipFolder(folder),
      fileType: 'application/zip',
    }
  } catch {
    toast.error(t('folderZipFailed', { name: folder.name }), {
      duration: 2500,
    })
    return null
  }
}

export function UploadResourceFields({
  files,
  onFilesChange,
  t,
  limits,
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
          const packaged = await packageFolder(
            folder,
            t,
            folderUploadLimitBytes(limits),
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
    [limits, t, updateFiles],
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
          {files.map(({ id, file }) => (
            <div
              key={id}
              className="flex items-center gap-3 border-b border-border/50 px-4 py-3 last:border-b-0"
            >
              <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted">
                <FileIcon className="size-5 text-muted-foreground" />
              </div>
              <p className="min-w-0 flex-1 truncate text-sm font-medium">
                {file.name}
              </p>
              <span className="shrink-0 text-xs text-muted-foreground">
                {formatFileSize(file.size)}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="shrink-0 text-muted-foreground hover:text-foreground"
                onClick={() =>
                  updateFiles((currentFiles) =>
                    currentFiles.filter((item) => item.id !== id),
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
