// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import i18n from '#/i18n'
import type { ResourceUploadTask } from '../-hooks/use-resource-upload'
import { UploadTaskDialog } from './upload-task-dialog'

function task(
  overrides: Partial<ResourceUploadTask> & Pick<ResourceUploadTask, 'id'>,
): ResourceUploadTask {
  return {
    source: 'local',
    serverTaskId: null,
    fileName: `${overrides.id}.md`,
    fileSize: 1,
    fileType: null,
    status: 'uploading',
    progress: 10,
    createdAt: 1,
    finishedAt: null,
    errorCode: null,
    errorMessage: null,
    rootUri: null,
    ...overrides,
  }
}

beforeAll(async () => {
  await i18n.changeLanguage('en')
})

afterEach(() => {
  cleanup()
})

describe('UploadTaskDialog', () => {
  it('offers cancel only for local uploads still sending data', () => {
    const onCancelTask = vi.fn()
    render(
      <UploadTaskDialog
        open
        onOpenChange={vi.fn()}
        onCancelTask={onCancelTask}
        tasks={[
          task({ id: 'sending', status: 'uploading' }),
          task({ id: 'queued', status: 'pending', createdAt: 2 }),
          task({ id: 'importing', status: 'processing', createdAt: 3 }),
          task({ id: 'remote', source: 'remote', createdAt: 4 }),
          task({ id: 'done', status: 'success', createdAt: 5 }),
        ]}
      />,
    )

    const buttons = screen.getAllByRole('button', {
      name: /sending|queued|importing|remote|done/,
    })
    expect(buttons.map((button) => button.getAttribute('aria-label'))).toEqual([
      'Cancel uploading queued.md',
      'Cancel uploading sending.md',
    ])

    fireEvent.click(
      screen.getByRole('button', { name: 'Cancel uploading sending.md' }),
    )
    expect(onCancelTask).toHaveBeenCalledExactlyOnceWith('sending')
  })

  it('tells queued, uploading and processing tasks apart', () => {
    render(
      <UploadTaskDialog
        open
        onOpenChange={vi.fn()}
        tasks={[
          task({ id: 'queued', status: 'pending', progress: 0 }),
          task({
            id: 'sending',
            status: 'uploading',
            progress: 42,
            createdAt: 2,
          }),
          task({
            id: 'starting',
            status: 'uploading',
            progress: null,
            createdAt: 3,
          }),
          task({
            id: 'importing',
            status: 'processing',
            progress: null,
            createdAt: 4,
          }),
        ]}
      />,
    )

    const statusOf = (name: string) =>
      screen
        .getByText(`${name}.md`)
        .closest('[data-task-row]')
        ?.querySelector('[data-task-status]')?.textContent
    expect(statusOf('queued')).toBe('Queued')
    expect(statusOf('sending')).toBe('Uploading 42%')
    expect(statusOf('starting')).toBe('Uploading')
    expect(statusOf('importing')).toBe('Processing')
  })

  it('shows no cancel buttons without a cancel handler', () => {
    render(
      <UploadTaskDialog
        open
        onOpenChange={vi.fn()}
        tasks={[task({ id: 'sending' })]}
      />,
    )

    expect(
      screen.queryByRole('button', { name: /Cancel uploading/ }),
    ).toBeNull()
  })
})
