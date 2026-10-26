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

import { DeleteSkillDialog } from './delete-skill-dialog'

const deleteSkill = vi.hoisted(() => vi.fn())

vi.mock('../-lib/delete-skill', () => ({ deleteSkill }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const skill = { name: 'pr-review', uri: 'viking://agent/skills/pr-review' }

function renderDialog() {
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

describe('DeleteSkillDialog', () => {
  it('does not delete on cancel', () => {
    const { onDeleted, onOpenChange } = renderDialog()
    expect(screen.getByText('delete.description')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'delete.cancel' }))

    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(deleteSkill).not.toHaveBeenCalled()
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('deletes the skill, closes, and reports it', async () => {
    deleteSkill.mockResolvedValue({ name: 'pr-review' })
    const { onDeleted, onOpenChange } = renderDialog()

    fireEvent.click(screen.getByRole('button', { name: 'delete.confirm' }))

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith(skill))
    expect(deleteSkill.mock.calls[0][0]).toEqual(skill)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('keeps the dialog open with the server error', async () => {
    deleteSkill.mockRejectedValue('Permission denied')
    const { onDeleted, onOpenChange } = renderDialog()

    fireEvent.click(screen.getByRole('button', { name: 'delete.confirm' }))

    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByText('delete.failed')).toBeTruthy()
    expect(onDeleted).not.toHaveBeenCalled()
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })
})
