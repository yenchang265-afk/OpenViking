// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { VikingFsEntry } from '#/routes/resources/-types/viking-fm'

import { ContextExplorerHeader, ContextTree } from './context-explorer'

const api = vi.hoisted(() => ({
  createDirectory: vi.fn(),
  createTextFile: vi.fn(),
  fetchFsStat: vi.fn(),
  moveResource: vi.fn(),
  removeResource: vi.fn(),
}))
const { invalidateListMock, useVikingFsListMock } = vi.hoisted(() => ({
  invalidateListMock: vi.fn(),
  useVikingFsListMock: vi.fn(),
}))

vi.mock('#/routes/resources/-lib/api', () => api)
vi.mock('#/routes/resources/-hooks/viking-fm', () => ({
  useInvalidateVikingFs: () => ({ invalidateList: invalidateListMock }),
  useVikingFsList: useVikingFsListMock,
}))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { name?: string }) =>
      options?.name ? `${key}:${options.name}` : key,
  }),
}))

const namespace: VikingFsEntry = {
  abstract: '',
  isDir: true,
  modTime: '',
  modTimestamp: 1,
  name: 'resources',
  overview: '',
  size: '',
  sizeBytes: null,
  uri: 'viking://resources/',
}

const folder: VikingFsEntry = {
  ...namespace,
  name: 'docs',
  uri: 'viking://resources/docs/',
}

const file: VikingFsEntry = {
  ...namespace,
  isDir: false,
  name: 'guide.md',
  size: '1 KB',
  sizeBytes: 1024,
  uri: 'viking://resources/guide.md',
}

const notFound = { statusCode: 404, code: 'NOT_FOUND', message: 'missing' }

beforeEach(() => {
  useVikingFsListMock.mockImplementation((uri: string) => ({
    data: {
      entries:
        uri === 'viking://'
          ? [namespace]
          : uri === namespace.uri
            ? [folder, file]
            : [],
    },
    isError: false,
    isLoading: false,
  }))
  api.fetchFsStat.mockRejectedValue(notFound)
  api.createDirectory.mockResolvedValue(undefined)
  api.createTextFile.mockResolvedValue(undefined)
  api.moveResource.mockResolvedValue(undefined)
  api.removeResource.mockResolvedValue(undefined)
  invalidateListMock.mockResolvedValue(undefined)
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0)
    return 1
  })
  Element.prototype.scrollIntoView = vi.fn()
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

function renderTree({ currentUri = 'viking://', selectMode = false } = {}) {
  const props = {
    onEntriesDeleted: vi.fn(),
    onEntryDeleted: vi.fn(),
    onEntryRenamed: vi.fn(),
    onExpandedKeysChange: vi.fn(),
    onSelectDirectory: vi.fn(),
    onSelectFile: vi.fn(),
    onSelectModeChange: vi.fn(),
  }
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  })
  const tree = (mode: boolean) => (
    <QueryClientProvider client={queryClient}>
      <ContextTree
        currentUri={currentUri}
        expandedKeys={new Set([namespace.uri, folder.uri])}
        selectMode={mode}
        {...props}
      />
    </QueryClientProvider>
  )

  const { rerender } = render(tree(selectMode))

  return {
    ...props,
    setSelectMode: (mode: boolean) => rerender(tree(mode)),
  }
}

function rightClick(name: string) {
  fireEvent.contextMenu(screen.getByRole('button', { name }))
}

async function menuItemNames(): Promise<string[]> {
  const items = await screen.findAllByRole('menuitem')
  return items.map((item) => item.textContent)
}

describe('ContextTree context menu', () => {
  it('offers file actions on a file row', async () => {
    renderTree()
    rightClick('guide.md')

    expect(await menuItemNames()).toEqual([
      'explorer.menu.open',
      'explorer.menu.rename',
      'explorer.menu.copyUri',
      'explorer.menu.delete',
    ])
  })

  it('offers create actions but no rename or delete on a namespace', async () => {
    renderTree()
    rightClick('resources')

    expect(await menuItemNames()).toEqual([
      'explorer.menu.open',
      'explorer.menu.newFile',
      'explorer.menu.newFolder',
      'explorer.menu.copyUri',
      'explorer.menu.refresh',
    ])
  })

  it('creates a folder inside the clicked directory and selects it', async () => {
    const user = userEvent.setup()
    const { onSelectDirectory } = renderTree()
    rightClick('docs')
    await user.click(
      await screen.findByRole('menuitem', { name: 'explorer.menu.newFolder' }),
    )

    await user.type(
      await screen.findByLabelText('explorer.nameDialog.nameLabel'),
      'specs',
    )
    await user.click(
      screen.getByRole('button', { name: 'explorer.nameDialog.create' }),
    )

    await vi.waitFor(() =>
      expect(api.createDirectory).toHaveBeenCalledWith(
        'viking://resources/docs/specs',
      ),
    )
    expect(api.fetchFsStat).toHaveBeenCalledWith(
      'viking://resources/docs/specs',
      { throwOnError: true },
    )
    expect(invalidateListMock).toHaveBeenCalledWith('viking://resources/docs/')
    await vi.waitFor(() =>
      expect(onSelectDirectory).toHaveBeenCalledWith(
        expect.objectContaining({ uri: 'viking://resources/docs/specs/' }),
      ),
    )
  })

  it('rejects new file names without a writable extension', async () => {
    const user = userEvent.setup()
    renderTree()
    rightClick('docs')
    await user.click(
      await screen.findByRole('menuitem', { name: 'explorer.menu.newFile' }),
    )

    await user.type(
      await screen.findByLabelText('explorer.nameDialog.nameLabel'),
      'notes',
    )
    await user.click(
      screen.getByRole('button', { name: 'explorer.nameDialog.create' }),
    )

    expect(
      await screen.findByText('explorer.nameDialog.errors.extension'),
    ).toBeTruthy()
    expect(api.createTextFile).not.toHaveBeenCalled()
  })

  it('refuses names that already exist', async () => {
    const user = userEvent.setup()
    api.fetchFsStat.mockResolvedValue(file)
    renderTree()
    rightClick('resources')
    await user.click(
      await screen.findByRole('menuitem', { name: 'explorer.menu.newFile' }),
    )

    await user.type(
      await screen.findByLabelText('explorer.nameDialog.nameLabel'),
      'guide.md',
    )
    await user.click(
      screen.getByRole('button', { name: 'explorer.nameDialog.create' }),
    )

    expect(
      await screen.findByText(
        'explorer.nameDialog.failed',
        { exact: false },
        { timeout: 2000 },
      ),
    ).toBeTruthy()
    expect(api.createTextFile).not.toHaveBeenCalled()
  })

  it('renames a folder and remaps expanded paths', async () => {
    const user = userEvent.setup()
    const { onEntryRenamed, onExpandedKeysChange } = renderTree()
    rightClick('docs')
    await user.click(
      await screen.findByRole('menuitem', { name: 'explorer.menu.rename' }),
    )

    const input = await screen.findByLabelText('explorer.nameDialog.nameLabel')
    expect((input as HTMLInputElement).value).toBe('docs')
    await user.clear(input)
    await user.type(input, 'manuals')
    await user.click(
      screen.getByRole('button', { name: 'explorer.nameDialog.rename' }),
    )

    await vi.waitFor(() =>
      expect(api.moveResource).toHaveBeenCalledWith(
        'viking://resources/docs',
        'viking://resources/manuals',
      ),
    )
    await vi.waitFor(() =>
      expect(onEntryRenamed).toHaveBeenCalledWith(
        'viking://resources/docs',
        'viking://resources/manuals',
      ),
    )
    expect(onExpandedKeysChange).toHaveBeenCalledWith(
      new Set([namespace.uri, 'viking://resources/manuals/']),
    )
  })

  it('deletes a file after confirmation', async () => {
    const user = userEvent.setup()
    const { onEntryDeleted } = renderTree()
    rightClick('guide.md')
    await user.click(
      await screen.findByRole('menuitem', { name: 'explorer.menu.delete' }),
    )
    await user.click(
      await screen.findByRole('button', { name: 'deleteResource.confirm' }),
    )

    await vi.waitFor(() =>
      expect(api.removeResource).toHaveBeenCalledWith(file.uri, {
        recursive: false,
      }),
    )
    await vi.waitFor(() =>
      expect(onEntryDeleted).toHaveBeenCalledWith(
        expect.objectContaining({ uri: file.uri }),
      ),
    )
  })

  it('creates in the current directory from empty space', async () => {
    renderTree({ currentUri: 'viking://resources/docs/' })
    fireEvent.contextMenu(screen.getByRole('list', { name: 'explorer.title' }))

    expect(await menuItemNames()).toEqual([
      'explorer.menu.newFile',
      'explorer.menu.newFolder',
      'explorer.menu.refresh',
    ])
  })
})

function ctrlClick(name: string) {
  fireEvent.click(screen.getByRole('button', { name }), { ctrlKey: true })
}

function selectionToolbar() {
  return screen.queryByRole('toolbar', { name: 'explorer.selection.count' })
}

describe('ContextTree batch delete', () => {
  it('marks rows with ctrl-click without opening them', () => {
    const { onSelectDirectory, onSelectFile } = renderTree()
    ctrlClick('docs')
    ctrlClick('guide.md')

    expect(selectionToolbar()).toBeTruthy()
    expect(onSelectDirectory).not.toHaveBeenCalled()
    expect(onSelectFile).not.toHaveBeenCalled()
  })

  it('never marks a namespace', () => {
    renderTree()
    ctrlClick('resources')

    expect(selectionToolbar()).toBeNull()
  })

  it('clears the marks on a plain click', () => {
    const { onSelectFile } = renderTree()
    ctrlClick('docs')
    fireEvent.click(screen.getByRole('button', { name: 'guide.md' }))

    expect(selectionToolbar()).toBeNull()
    expect(onSelectFile).toHaveBeenCalled()
  })

  it('offers batch actions when right-clicking a marked row', async () => {
    renderTree()
    ctrlClick('docs')
    ctrlClick('guide.md')
    rightClick('guide.md')

    expect(await menuItemNames()).toEqual([
      'explorer.menu.clearSelection',
      'explorer.menu.deleteSelected',
    ])
  })

  it('keeps the single-row menu for an unmarked row', async () => {
    renderTree()
    ctrlClick('docs')
    ctrlClick('guide.md')
    rightClick('resources')

    expect(await menuItemNames()).toContain('explorer.menu.newFile')
  })

  it('deletes every marked row after one confirmation', async () => {
    const user = userEvent.setup()
    const { onEntriesDeleted } = renderTree()
    ctrlClick('docs')
    ctrlClick('guide.md')
    rightClick('guide.md')
    await user.click(
      await screen.findByRole('menuitem', {
        name: 'explorer.menu.deleteSelected',
      }),
    )

    const list = await screen.findByRole('list', {
      name: 'deleteResource.batchListLabel',
    })
    expect(list.textContent).toContain(folder.uri)
    expect(list.textContent).toContain(file.uri)
    await user.click(
      screen.getByRole('button', { name: 'deleteResource.confirm' }),
    )

    await vi.waitFor(() =>
      expect(onEntriesDeleted).toHaveBeenCalledWith([
        expect.objectContaining({ uri: folder.uri }),
        expect.objectContaining({ uri: file.uri }),
      ]),
    )
    expect(api.removeResource).toHaveBeenCalledWith(folder.uri, {
      recursive: true,
    })
    expect(api.removeResource).toHaveBeenCalledWith(file.uri, {
      recursive: false,
    })
    expect(invalidateListMock).toHaveBeenCalledWith(namespace.uri)
    expect(selectionToolbar()).toBeNull()
  })

  it('keeps failures selected and retries only them', async () => {
    const user = userEvent.setup()
    api.removeResource.mockImplementation(async (uri: string) => {
      if (uri === file.uri) throw new Error('locked')
    })
    const { onEntriesDeleted } = renderTree()
    ctrlClick('docs')
    ctrlClick('guide.md')
    fireEvent.click(
      screen.getByRole('button', { name: 'explorer.selection.delete' }),
    )
    await user.click(
      await screen.findByRole('button', { name: 'deleteResource.confirm' }),
    )

    expect((await screen.findByRole('alert')).textContent).toBe(
      'deleteResource.batchFailed',
    )
    expect(onEntriesDeleted).toHaveBeenCalledWith([
      expect.objectContaining({ uri: folder.uri }),
    ])
    const list = screen.getByRole('list', {
      name: 'deleteResource.batchListLabel',
    })
    expect(list.textContent).toBe(file.uri)

    api.removeResource.mockClear()
    api.removeResource.mockResolvedValue(undefined)
    await user.click(
      screen.getByRole('button', { name: 'deleteResource.confirm' }),
    )

    await vi.waitFor(() =>
      expect(onEntriesDeleted).toHaveBeenLastCalledWith([
        expect.objectContaining({ uri: file.uri }),
      ]),
    )
    expect(api.removeResource).toHaveBeenCalledTimes(1)
    expect(selectionToolbar()).toBeNull()
  })

  it('marks rows from the keyboard with Ctrl+Space', () => {
    const { onSelectFile } = renderTree()
    const row = screen.getByRole('button', { name: 'guide.md' })
    fireEvent.keyDown(row, { key: ' ', ctrlKey: true })

    expect(selectionToolbar()).toBeTruthy()
    expect(row.getAttribute('aria-describedby')).toBeTruthy()
    expect(onSelectFile).not.toHaveBeenCalled()
  })

  it('moves marks along with a renamed folder', async () => {
    const user = userEvent.setup()
    renderTree()
    // A single mark keeps the regular menu, which offers Rename.
    ctrlClick('docs')
    rightClick('docs')
    await user.click(
      await screen.findByRole('menuitem', { name: 'explorer.menu.rename' }),
    )
    const input = await screen.findByLabelText('explorer.nameDialog.nameLabel')
    await user.clear(input)
    await user.type(input, 'manuals')
    await user.click(
      screen.getByRole('button', { name: 'explorer.nameDialog.rename' }),
    )
    await vi.waitFor(() => expect(api.moveResource).toHaveBeenCalled())

    fireEvent.click(
      screen.getByRole('button', { name: 'explorer.selection.delete' }),
    )
    const list = await screen.findByRole('list', {
      name: 'deleteResource.batchListLabel',
    })
    expect(list.textContent).toBe('viking://resources/manuals/')
  })

  it('handles Escape and Delete keys on the tree', async () => {
    renderTree()
    ctrlClick('guide.md')
    fireEvent.keyDown(screen.getByRole('button', { name: 'guide.md' }), {
      key: 'Escape',
    })
    expect(selectionToolbar()).toBeNull()

    ctrlClick('guide.md')
    fireEvent.keyDown(screen.getByRole('button', { name: 'guide.md' }), {
      key: 'Delete',
    })
    expect(
      await screen.findByRole('list', {
        name: 'deleteResource.batchListLabel',
      }),
    ).toBeTruthy()
  })
})

describe('ContextTree checkbox mode', () => {
  it('checks rows on a plain click instead of opening them', () => {
    const { onSelectDirectory, onSelectFile } = renderTree({
      selectMode: true,
    })
    const row = screen.getByRole('button', { name: 'guide.md' })
    expect(row.getAttribute('aria-pressed')).toBe('false')

    fireEvent.click(row)
    fireEvent.click(screen.getByRole('button', { name: 'docs' }))

    expect(row.getAttribute('aria-pressed')).toBe('true')
    expect(onSelectFile).not.toHaveBeenCalled()
    expect(onSelectDirectory).not.toHaveBeenCalled()
    expect(
      screen.getByRole('button', { name: 'docs' }).getAttribute('aria-pressed'),
    ).toBe('true')
  })

  it('leaves namespaces without a checkbox and still opens them', () => {
    const { onSelectDirectory } = renderTree({ selectMode: true })
    fireEvent.click(screen.getByRole('button', { name: 'guide.md' }))
    const namespaceRow = screen.getByRole('button', { name: 'resources' })
    expect(namespaceRow.getAttribute('aria-pressed')).toBeNull()

    fireEvent.click(namespaceRow)

    expect(onSelectDirectory).toHaveBeenCalled()
    // Opening a namespace keeps the checks.
    expect(
      screen
        .getByRole('button', { name: 'guide.md' })
        .getAttribute('aria-pressed'),
    ).toBe('true')
  })

  it('shows the toolbar with Delete disabled until something is checked', () => {
    renderTree({ selectMode: true })
    const deleteButton = screen.getByRole('button', {
      name: 'explorer.selection.delete',
    })
    expect(deleteButton.hasAttribute('disabled')).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: 'guide.md' }))

    expect(deleteButton.hasAttribute('disabled')).toBe(false)
  })

  it('exits with Done and with Escape once nothing is checked', () => {
    const { onSelectModeChange } = renderTree({ selectMode: true })
    fireEvent.click(
      screen.getByRole('button', { name: 'explorer.selection.done' }),
    )
    expect(onSelectModeChange).toHaveBeenLastCalledWith(false)

    onSelectModeChange.mockClear()
    const row = screen.getByRole('button', { name: 'guide.md' })
    fireEvent.click(row)
    fireEvent.keyDown(row, { key: 'Escape' })
    expect(row.getAttribute('aria-pressed')).toBe('false')
    expect(onSelectModeChange).not.toHaveBeenCalled()
    fireEvent.keyDown(row, { key: 'Escape' })
    expect(onSelectModeChange).toHaveBeenCalledWith(false)
  })

  it('drops the checks when the mode is turned off from outside', () => {
    const { setSelectMode } = renderTree({ selectMode: true })
    fireEvent.click(screen.getByRole('button', { name: 'guide.md' }))
    setSelectMode(false)
    setSelectMode(true)

    expect(
      screen
        .getByRole('button', { name: 'guide.md' })
        .getAttribute('aria-pressed'),
    ).toBe('false')
  })

  it('toggles from the explorer header', () => {
    const onToggleSelecting = vi.fn()
    render(
      <ContextExplorerHeader
        activeTaskCount={0}
        hasActiveTasks={false}
        hasTasks={false}
        isRefreshing={false}
        isRefreshingTasks={false}
        isSelecting
        onAddResource={vi.fn()}
        onOpenProcessingTasks={vi.fn()}
        onOpenSearch={vi.fn()}
        onRefresh={vi.fn()}
        onToggleSelecting={onToggleSelecting}
      />,
    )
    const toggle = screen.getByRole('button', { name: 'explorer.selectMode' })
    expect(toggle.getAttribute('aria-pressed')).toBe('true')

    fireEvent.click(toggle)

    expect(onToggleSelecting).toHaveBeenCalled()
  })
})
