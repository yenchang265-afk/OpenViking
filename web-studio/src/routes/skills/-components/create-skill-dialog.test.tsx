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

import type * as CreateSkillModule from '../-lib/create-skill'
import { CreateSkillDialog } from './create-skill-dialog'

const createSkill = vi.hoisted(() => vi.fn())

vi.mock('../-lib/create-skill', async (importOriginal) => ({
  ...(await importOriginal<typeof CreateSkillModule>()),
  createSkill,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

afterEach(() => {
  cleanup()
  createSkill.mockReset()
})

function renderDialog() {
  const onCreated = vi.fn()
  const onOpenChange = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CreateSkillDialog
        open
        existingSkills={[{ name: 'pr-review', scope: 'user' }]}
        getErrorMessage={(error) => String(error)}
        initialScope="user"
        onCreated={onCreated}
        onOpenChange={onOpenChange}
      />
    </QueryClientProvider>,
  )
  return { onCreated, onOpenChange }
}

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

describe('CreateSkillDialog', () => {
  it('refuses a name already used in the chosen scope', async () => {
    renderDialog()
    fill('create.nameLabel', 'pr-review')
    fill('create.descriptionLabel', 'Reviews pull requests')
    fireEvent.click(screen.getByRole('button', { name: 'create.submit' }))

    expect(await screen.findByText('create.errors.name.exists')).toBeTruthy()
    expect(createSkill).not.toHaveBeenCalled()
  })

  it('creates the skill and closes', async () => {
    createSkill.mockResolvedValue({ status: 'success' })
    const { onCreated, onOpenChange } = renderDialog()
    fill('create.nameLabel', ' triage ')
    fill('create.descriptionLabel', 'Triage new issues')
    fill('create.instructionsLabel', '# Steps')
    fireEvent.click(screen.getByRole('button', { name: 'create.submit' }))

    const draft = {
      body: '# Steps',
      description: 'Triage new issues',
      name: 'triage',
      scope: 'user',
    }
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(draft))
    expect(createSkill.mock.calls[0][0]).toEqual(draft)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('keeps the dialog open and shows the server error', async () => {
    createSkill.mockRejectedValue('boom')
    const { onOpenChange } = renderDialog()
    fill('create.nameLabel', 'triage')
    fill('create.descriptionLabel', 'Triage new issues')
    fireEvent.click(screen.getByRole('button', { name: 'create.submit' }))

    expect(await screen.findByText('create.failed')).toBeTruthy()
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })
})
