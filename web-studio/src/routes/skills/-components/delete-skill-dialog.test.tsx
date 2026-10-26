// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type * as DeleteSkillModule from '../-lib/delete-skill'
import { DeleteSkillDialog } from './delete-skill-dialog'

const deleteSkill = vi.hoisted(() => vi.fn())
const exportOvpack = vi.hoisted(() => vi.fn())
const downloadBlob = vi.hoisted(() => vi.fn())

vi.mock('../-lib/delete-skill', async (importOriginal) => ({
  ...(await importOriginal<typeof DeleteSkillModule>()),
  deleteSkill,
}))

vi.mock('#/routes/filesystem/-lib/data-management', () => ({
  createDataManagementClient: () => ({ client: {} }),
  downloadBlob,
  exportOvpack,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const userSkill = {
  name: 'pr-review',
  scope: 'user' as const,
  uri: 'viking://user/alice/skills/pr-review',
}
const sharedSkill = {
  name: 'pr-review',
  scope: 'agent' as const,
  uri: 'viking://agent/skills/pr-review',
}

function renderDialog(skill: typeof userSkill | typeof sharedSkill) {
  const onDeleted = vi.fn()
  const onOpenChange = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DeleteSkillDialog
        open
        skill={skill}
        getErrorMessage={(error) => String(error)}
        onDeleted={onDeleted}
        onOpenChange={onOpenChange}
      />
    </QueryClientProvider>,
  )
  return { onDeleted, onOpenChange }
}

function confirmButton() {
  return screen.getByRole('button', { name: 'delete.confirm' })
}

describe('DeleteSkillDialog', () => {
  it('does not delete on cancel', () => {
    const { onDeleted, onOpenChange } = renderDialog(userSkill)
    expect(screen.getByText('delete.description')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'delete.cancel' }))

    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(deleteSkill).not.toHaveBeenCalled()
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('deletes a user skill, closes, and reports it', async () => {
    deleteSkill.mockResolvedValue({ name: 'pr-review' })
    const { onDeleted, onOpenChange } = renderDialog(userSkill)
    expect(screen.queryByLabelText('delete.typeName')).toBeNull()

    fireEvent.click(confirmButton())

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith(userSkill))
    expect(deleteSkill.mock.calls[0][0]).toEqual(userSkill)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('makes the user type a shared skill name before deleting', async () => {
    deleteSkill.mockResolvedValue({ name: 'pr-review' })
    const { onDeleted } = renderDialog(sharedSkill)
    const input = screen.getByLabelText('delete.typeName')

    expect(confirmButton().hasAttribute('disabled')).toBe(true)
    fireEvent.click(confirmButton())
    fireEvent.change(input, { target: { value: 'pr-revie' } })
    expect(confirmButton().hasAttribute('disabled')).toBe(true)
    expect(deleteSkill).not.toHaveBeenCalled()

    fireEvent.change(input, { target: { value: 'pr-review' } })
    expect(confirmButton().hasAttribute('disabled')).toBe(false)
    fireEvent.click(confirmButton())

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith(sharedSkill))
  })

  it('downloads an OVPack backup of the skill directory', async () => {
    const blob = new Blob(['pack'])
    exportOvpack.mockResolvedValue(blob)
    renderDialog(userSkill)
    expect(screen.getByText('delete.backupHint')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'delete.backup' }))

    expect(await screen.findByRole('status')).toBeTruthy()
    expect(exportOvpack.mock.calls[0][1]).toBe(userSkill.uri)
    expect(downloadBlob).toHaveBeenCalledWith(blob, userSkill.uri)
    expect(deleteSkill).not.toHaveBeenCalled()
  })

  it('shows a backup failure without deleting', async () => {
    exportOvpack.mockRejectedValue('export failed')
    renderDialog(userSkill)

    fireEvent.click(screen.getByRole('button', { name: 'delete.backup' }))

    expect(await screen.findByText('delete.backupFailed')).toBeTruthy()
    expect(downloadBlob).not.toHaveBeenCalled()
    expect(deleteSkill).not.toHaveBeenCalled()
  })

  it('keeps the dialog open with the server error', async () => {
    deleteSkill.mockRejectedValue('Permission denied')
    const { onDeleted, onOpenChange } = renderDialog(userSkill)

    fireEvent.click(confirmButton())

    expect(await screen.findByText('delete.failed')).toBeTruthy()
    expect(onDeleted).not.toHaveBeenCalled()
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })
})
