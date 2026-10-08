import {
  Fragment,
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
} from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ClipboardIcon,
  FilePlusIcon,
  FolderOpenIcon,
  FolderPlusIcon,
  PencilIcon,
  RefreshCcwIcon,
  Trash2Icon,
} from 'lucide-react'
import { toast } from 'sonner'

import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '#/components/ui/context-menu'
import { copyTextToClipboard } from '#/lib/clipboard'
import { useInvalidateVikingFs } from '#/routes/resources/-hooks/viking-fm'
import {
  createDirectory,
  createTextFile,
  fetchFsStat,
  moveResource,
} from '#/routes/resources/-lib/api'
import {
  fileNameFromUri,
  normalizeDirUri,
  normalizeFileUri,
  parentUri,
} from '#/routes/resources/-lib/normalize'
import type { VikingFsEntry } from '#/routes/resources/-types/viking-fm'

import {
  canCreateInUri,
  childEntryUri,
  renamedEntryUri,
} from '../-lib/tree-actions'
import { canDeleteResourceUri, createEntryFromUri } from '../-lib/utils'
import { DeleteResourceDialog } from './delete-resource'
import { EntryNameDialog } from './entry-name-dialog'

type SetMenuTarget = (entry: VikingFsEntry) => void

const ContextTreeMenuTargetContext = createContext<SetMenuTarget | null>(null)

/**
 * Rows call this from their own contextmenu/touchstart handlers. Those run
 * before the surrounding trigger opens the menu, so the menu renders with
 * the row that was actually pressed.
 */
export function useContextTreeMenuTarget(): SetMenuTarget | null {
  return useContext(ContextTreeMenuTargetContext)
}

type TreeDialog =
  | { kind: 'newFile' | 'newFolder'; dirUri: string }
  | { kind: 'rename' | 'delete'; entry: VikingFsEntry }

export type ContextTreeMenuProps = {
  children: ReactNode
  className?: string
  /** Directory used when the menu opens on empty space in the tree. */
  currentUri: string
  onEntryDeleted?: (entry: Pick<VikingFsEntry, 'isDir' | 'uri'>) => void
  onEntryRenamed?: (fromUri: string, toUri: string) => void
  onSelectDirectory: (entry: VikingFsEntry) => void
  onSelectFile: (entry: VikingFsEntry) => void
}

export function ContextTreeMenu({
  children,
  className,
  currentUri,
  onEntryDeleted,
  onEntryRenamed,
  onSelectDirectory,
  onSelectFile,
}: ContextTreeMenuProps) {
  const { t } = useTranslation('playground')
  const { invalidateList } = useInvalidateVikingFs()
  const [target, setTarget] = useState<VikingFsEntry | null>(null)
  const [dialog, setDialog] = useState<TreeDialog | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const openingDialogRef = useRef(false)

  const clearTarget = useCallback(() => setTarget(null), [])
  const openDialog = useCallback((next: TreeDialog) => {
    openingDialogRef.current = true
    setDialog(next)
    setDialogOpen(true)
  }, [])

  // Empty space acts on the directory currently shown, like a file explorer.
  const menuDirUri = target
    ? target.isDir
      ? normalizeDirUri(target.uri)
      : null
    : normalizeDirUri(currentUri)
  const canCreate = menuDirUri !== null && canCreateInUri(menuDirUri)
  const canModify = target !== null && canDeleteResourceUri(target.uri)

  const copyUri = (uri: string) => {
    void copyTextToClipboard(uri)
      .then(() => toast.success(t('copied')))
      .catch(() => toast.error(t('copyFailed')))
  }

  const ensureNameFree = async (uri: string, name: string) => {
    if (await isUriTaken(uri)) {
      throw new Error(t('explorer.nameDialog.errors.exists', { name }))
    }
  }

  const createEntry = async (
    dirUri: string,
    name: string,
    isDir: boolean,
  ): Promise<void> => {
    const uri = childEntryUri(dirUri, name)
    await ensureNameFree(uri, name)
    if (isDir) await createDirectory(uri)
    else await createTextFile(uri)
    toast.success(t('explorer.nameDialog.created', { name }))
    await invalidateList(dirUri)
    const created = createEntryFromUri(uri, isDir)
    if (isDir) onSelectDirectory(created)
    else onSelectFile(created)
  }

  const renameEntry = async (
    entry: VikingFsEntry,
    name: string,
  ): Promise<void> => {
    const fromUri = normalizeFileUri(entry.uri)
    const toUri = renamedEntryUri(fromUri, name)
    if (toUri === fromUri) return
    await ensureNameFree(toUri, name)
    await moveResource(fromUri, toUri)
    toast.success(t('explorer.nameDialog.renamed', { name }))
    await invalidateList(parentUri(fromUri))
    onEntryRenamed?.(fromUri, toUri)
  }

  const menuGroups = [
    target
      ? [
          <ContextMenuItem
            key="open"
            onClick={() =>
              target.isDir ? onSelectDirectory(target) : onSelectFile(target)
            }
          >
            <FolderOpenIcon />
            {t('explorer.menu.open')}
          </ContextMenuItem>,
        ]
      : [],
    canCreate && menuDirUri
      ? [
          <ContextMenuItem
            key="new-file"
            onClick={() => openDialog({ kind: 'newFile', dirUri: menuDirUri })}
          >
            <FilePlusIcon />
            {t('explorer.menu.newFile')}
          </ContextMenuItem>,
          <ContextMenuItem
            key="new-folder"
            onClick={() =>
              openDialog({ kind: 'newFolder', dirUri: menuDirUri })
            }
          >
            <FolderPlusIcon />
            {t('explorer.menu.newFolder')}
          </ContextMenuItem>,
        ]
      : [],
    [
      target && canModify ? (
        <ContextMenuItem
          key="rename"
          onClick={() => openDialog({ kind: 'rename', entry: target })}
        >
          <PencilIcon />
          {t('explorer.menu.rename')}
        </ContextMenuItem>
      ) : null,
      target ? (
        <ContextMenuItem key="copy" onClick={() => copyUri(target.uri)}>
          <ClipboardIcon />
          {t('explorer.menu.copyUri')}
        </ContextMenuItem>
      ) : null,
      menuDirUri !== null ? (
        <ContextMenuItem
          key="refresh"
          // Empty space refreshes the whole tree; a folder only itself.
          onClick={() => void invalidateList(target ? menuDirUri : undefined)}
        >
          <RefreshCcwIcon />
          {t('explorer.menu.refresh')}
        </ContextMenuItem>
      ) : null,
    ].filter(Boolean),
    target && canModify
      ? [
          <ContextMenuItem
            key="delete"
            variant="destructive"
            onClick={() => openDialog({ kind: 'delete', entry: target })}
          >
            <Trash2Icon />
            {t('explorer.menu.delete')}
          </ContextMenuItem>,
        ]
      : [],
  ].filter((group) => group.length > 0)

  return (
    <ContextTreeMenuTargetContext.Provider value={setTarget}>
      <ContextMenu>
        <ContextMenuTrigger
          className={className}
          onContextMenuCapture={clearTarget}
          onTouchStartCapture={clearTarget}
        >
          {children}
        </ContextMenuTrigger>
        <ContextMenuContent
          aria-label={
            target ? t('explorer.menu.label', { name: target.name }) : undefined
          }
          finalFocus={() => {
            // A dialog opened from the menu takes focus itself.
            const opening = openingDialogRef.current
            openingDialogRef.current = false
            return !opening
          }}
        >
          {menuGroups.map((group, index) => (
            <Fragment key={index}>
              {index > 0 ? <ContextMenuSeparator /> : null}
              {group}
            </Fragment>
          ))}
        </ContextMenuContent>
      </ContextMenu>

      {dialog?.kind === 'newFile' || dialog?.kind === 'newFolder' ? (
        <EntryNameDialog
          key={`${dialog.kind}:${dialog.dirUri}`}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          mode={dialog.kind === 'newFile' ? 'file' : 'folder'}
          description={t('explorer.nameDialog.createIn', {
            uri: dialog.dirUri,
          })}
          onSubmit={(name) =>
            createEntry(dialog.dirUri, name, dialog.kind === 'newFolder')
          }
        />
      ) : null}
      {dialog?.kind === 'rename' ? (
        <EntryNameDialog
          key={`rename:${dialog.entry.uri}`}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          mode="rename"
          initialName={fileNameFromUri(dialog.entry.uri)}
          selectStem={!dialog.entry.isDir}
          description={t('explorer.nameDialog.renameFrom', {
            uri: dialog.entry.uri,
          })}
          onSubmit={(name) => renameEntry(dialog.entry, name)}
        />
      ) : null}
      {dialog?.kind === 'delete' ? (
        <DeleteResourceDialog
          key={`delete:${dialog.entry.uri}`}
          entry={dialog.entry}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          onDeleted={(entry) => {
            void invalidateList(parentUri(entry.uri))
            onEntryDeleted?.(entry)
          }}
        />
      ) : null}
    </ContextTreeMenuTargetContext.Provider>
  )
}

/** mkdir and mv can silently merge or overwrite, so refuse taken names first. */
async function isUriTaken(uri: string): Promise<boolean> {
  try {
    await fetchFsStat(uri, { throwOnError: true })
    return true
  } catch {
    // Missing (404) is the expected case; other stat failures are left for
    // the write itself to report.
    return false
  }
}
