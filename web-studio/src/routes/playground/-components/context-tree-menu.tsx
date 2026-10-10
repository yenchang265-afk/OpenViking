import {
  Fragment,
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import {
  CheckIcon,
  ClipboardIcon,
  DatabaseZapIcon,
  FilePlusIcon,
  FolderOpenIcon,
  FolderPlusIcon,
  PencilIcon,
  RefreshCcwIcon,
  Trash2Icon,
  XIcon,
} from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '#/components/ui/button'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '#/components/ui/context-menu'
import { copyTextToClipboard } from '#/lib/clipboard'
import { isCompileSourceUri } from '#/routes/compile/-lib/builtin-skills'
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
  canReindexUri,
  childEntryUri,
  isUriWithin,
  remapUri,
  renamedEntryUri,
} from '../-lib/tree-actions'
import { canDeleteResourceUri, createEntryFromUri } from '../-lib/utils'
import { CompileMenuItems } from './compile-menu-items'
import {
  BatchDeleteResourceDialog,
  DeleteResourceDialog,
} from './delete-resource'
import { EntryNameDialog } from './entry-name-dialog'
import { ReindexDialog } from './reindex-dialog'

type DeletedEntry = Pick<VikingFsEntry, 'isDir' | 'uri'>

type ContextTreeMenuContextValue = {
  /** Rows marked for batch actions, keyed by URI, in the order picked. */
  selection: ReadonlyMap<string, VikingFsEntry>
  selectMode: boolean
  clearSelection: () => void
  setMenuTarget: (entry: VikingFsEntry) => void
  toggleSelected: (entry: VikingFsEntry) => void
}

const ContextTreeMenuContext =
  createContext<ContextTreeMenuContextValue | null>(null)

/**
 * Rows call `setMenuTarget` from their own contextmenu/touchstart handlers.
 * Those run before the surrounding trigger opens the menu, so the menu
 * renders with the row that was actually pressed.
 */
export function useContextTreeMenu(): ContextTreeMenuContextValue | null {
  return useContext(ContextTreeMenuContext)
}

/** Namespaces cannot be deleted, so they never join a batch selection. */
export function canSelectForBatch(entry: Pick<VikingFsEntry, 'uri'>): boolean {
  return canDeleteResourceUri(entry.uri)
}

const EMPTY_SELECTION: ReadonlyMap<string, VikingFsEntry> = new Map()

type TreeDialog =
  | { kind: 'newFile' | 'newFolder'; dirUri: string }
  | { kind: 'rename' | 'delete' | 'reindex'; entry: VikingFsEntry }
  | { kind: 'batchDelete'; entries: VikingFsEntry[] }

export type ContextTreeMenuProps = {
  children: ReactNode
  className?: string
  /** Directory used when the menu opens on empty space in the tree. */
  currentUri: string
  onEntriesDeleted?: (entries: DeletedEntry[]) => void
  onEntryDeleted?: (entry: DeletedEntry) => void
  onEntryRenamed?: (fromUri: string, toUri: string) => void
  onSelectDirectory: (entry: VikingFsEntry) => void
  onSelectFile: (entry: VikingFsEntry) => void
  onSelectModeChange?: (selectMode: boolean) => void
  /** Checkbox mode: rows show checkboxes and a click checks them. */
  selectMode?: boolean
}

export function ContextTreeMenu({
  children,
  className,
  currentUri,
  onEntriesDeleted,
  onEntryDeleted,
  onEntryRenamed,
  onSelectDirectory,
  onSelectFile,
  onSelectModeChange,
  selectMode = false,
}: ContextTreeMenuProps) {
  const { t } = useTranslation('playground')
  const { invalidateList } = useInvalidateVikingFs()
  const [target, setTarget] = useState<VikingFsEntry | null>(null)
  const [selection, setSelection] =
    useState<ReadonlyMap<string, VikingFsEntry>>(EMPTY_SELECTION)
  // Leaving checkbox mode, from here or the header, drops the checks.
  const [prevSelectMode, setPrevSelectMode] = useState(selectMode)
  if (prevSelectMode !== selectMode) {
    setPrevSelectMode(selectMode)
    if (!selectMode) setSelection(EMPTY_SELECTION)
  }
  const [dialog, setDialog] = useState<TreeDialog | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const openingDialogRef = useRef(false)

  const clearTarget = useCallback(() => setTarget(null), [])
  const clearSelection = useCallback(() => setSelection(EMPTY_SELECTION), [])
  const toggleSelected = useCallback((entry: VikingFsEntry) => {
    if (!canSelectForBatch(entry)) return
    setSelection((current) => {
      const next = new Map(current)
      if (next.has(entry.uri)) next.delete(entry.uri)
      else next.set(entry.uri, entry)
      return next
    })
  }, [])
  /** Deleted entries take anything selected below them along. */
  const dropFromSelection = useCallback((removed: readonly DeletedEntry[]) => {
    setSelection(
      (current) =>
        new Map(
          [...current].filter(
            ([uri]) => !removed.some((entry) => isUriWithin(uri, entry.uri)),
          ),
        ),
    )
  }, [])
  const contextValue = useMemo<ContextTreeMenuContextValue>(
    () => ({
      clearSelection,
      selectMode,
      selection,
      setMenuTarget: setTarget,
      toggleSelected,
    }),
    [clearSelection, selectMode, selection, toggleSelected],
  )
  const openDialog = useCallback((next: TreeDialog) => {
    openingDialogRef.current = true
    setDialog(next)
    setDialogOpen(true)
  }, [])
  const openBatchDelete = () =>
    openDialog({ kind: 'batchDelete', entries: [...selection.values()] })

  const exitSelectMode = () => {
    clearSelection()
    onSelectModeChange?.(false)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (dialogOpen) return
    if (event.key === 'Escape' && (selection.size > 0 || selectMode)) {
      event.preventDefault()
      // First Escape clears the checks; the next one leaves checkbox mode.
      if (selection.size > 0) clearSelection()
      else exitSelectMode()
    } else if (event.key === 'Delete' && selection.size > 0) {
      event.preventDefault()
      openBatchDelete()
    }
  }

  const handleBatchDeleted = (deleted: DeletedEntry[]) => {
    dropFromSelection(deleted)
    // On partial failure the dialog stays open; narrow it to what is left
    // so confirming again retries only the failures.
    setDialog((current) => {
      if (current?.kind !== 'batchDelete') return current
      const remaining = current.entries.filter(
        (entry) => !deleted.some((gone) => isUriWithin(entry.uri, gone.uri)),
      )
      return remaining.length > 0 ? { ...current, entries: remaining } : current
    })
    for (const dirUri of new Set(
      deleted.map((entry) => parentUri(entry.uri)),
    )) {
      void invalidateList(dirUri)
    }
    onEntriesDeleted?.(deleted)
  }

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
    // Marks follow the renamed entry and anything below it.
    setSelection(
      (current) =>
        new Map(
          [...current].map(([uri, marked]) => {
            const next = remapUri(uri, fromUri, toUri)
            return [next, next === uri ? marked : { ...marked, uri: next }]
          }),
        ),
    )
    await invalidateList(parentUri(fromUri))
    onEntryRenamed?.(fromUri, toUri)
  }

  // Right-clicking a row that is part of a multi-selection acts on all of it.
  const batchMenuGroups =
    target !== null && selection.size > 1 && selection.has(target.uri)
      ? [
          [
            <ContextMenuItem key="clear-selection" onClick={clearSelection}>
              <XIcon />
              {t('explorer.menu.clearSelection')}
            </ContextMenuItem>,
          ],
          [
            <ContextMenuItem
              key="delete-selected"
              variant="destructive"
              onClick={openBatchDelete}
            >
              <Trash2Icon />
              {t('explorer.menu.deleteSelected', { count: selection.size })}
            </ContextMenuItem>,
          ],
        ]
      : null

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
    menuDirUri !== null && isCompileSourceUri(menuDirUri)
      ? [<CompileMenuItems key="compile" dirUri={menuDirUri} />]
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
      target && canReindexUri(target.uri) ? (
        <ContextMenuItem
          key="reindex"
          onClick={() => openDialog({ kind: 'reindex', entry: target })}
        >
          <DatabaseZapIcon />
          {t('explorer.menu.reindex')}
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
    <ContextTreeMenuContext.Provider value={contextValue}>
      <ContextMenu>
        <ContextMenuTrigger
          className={className}
          onContextMenuCapture={clearTarget}
          onTouchStartCapture={clearTarget}
          onKeyDown={handleKeyDown}
        >
          {selection.size > 0 || selectMode ? (
            <div
              role="toolbar"
              aria-label={t('explorer.selection.count', {
                count: selection.size,
              })}
              title={t('explorer.selection.hint')}
              className="sticky top-0 z-30 mb-1 flex items-center gap-1 rounded-md border bg-background/95 py-1 pl-2 pr-1 font-sans text-xs backdrop-blur"
            >
              <span className="min-w-0 flex-1 truncate text-muted-foreground">
                {t('explorer.selection.count', { count: selection.size })}
              </span>
              <Button
                type="button"
                size="xs"
                variant="ghost"
                className="text-destructive hover:text-destructive"
                disabled={selection.size === 0}
                onClick={openBatchDelete}
              >
                <Trash2Icon />
                {t('explorer.selection.delete')}
              </Button>
              {selectMode ? (
                <Button
                  type="button"
                  size="xs"
                  variant="ghost"
                  onClick={exitSelectMode}
                >
                  <CheckIcon />
                  {t('explorer.selection.done')}
                </Button>
              ) : (
                <Button
                  type="button"
                  size="xs"
                  variant="ghost"
                  onClick={clearSelection}
                >
                  <XIcon />
                  {t('explorer.selection.clear')}
                </Button>
              )}
            </div>
          ) : null}
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
          {(batchMenuGroups ?? menuGroups).map((group, index) => (
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
            dropFromSelection([entry])
            void invalidateList(parentUri(entry.uri))
            onEntryDeleted?.(entry)
          }}
        />
      ) : null}
      {dialog?.kind === 'batchDelete' ? (
        <BatchDeleteResourceDialog
          entries={dialog.entries}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          onDeleted={handleBatchDeleted}
        />
      ) : null}
      {dialog?.kind === 'reindex' ? (
        <ReindexDialog
          key={`reindex:${dialog.entry.uri}`}
          entry={dialog.entry}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
        />
      ) : null}
    </ContextTreeMenuContext.Provider>
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
