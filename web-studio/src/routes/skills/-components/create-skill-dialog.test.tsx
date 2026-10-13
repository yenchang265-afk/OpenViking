// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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

// jsdom does not implement scrollIntoView.
const scrollIntoView = vi.fn()

beforeEach(() => {
  Element.prototype.scrollIntoView = scrollIntoView
})

afterEach(() => {
  cleanup()
  createSkill.mockReset()
  scrollIntoView.mockReset()
  delete (Element.prototype as Partial<Element>).scrollIntoView
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
  it('asks before replacing a skill with the same name', async () => {
    createSkill.mockResolvedValue({ status: 'success' })
    const { onCreated } = renderDialog()
    fill('create.nameLabel', 'pr-review')
    fill('create.descriptionLabel', 'Reviews pull requests')
    expect(screen.getByText('create.nameExists')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'create.submit' }))

    expect(await screen.findByText('create.replace.title')).toBeTruthy()
    expect(createSkill).not.toHaveBeenCalled()

    fireEvent.click(
      screen.getByRole('button', { name: 'create.replace.confirm' }),
    )
    await waitFor(() =>
      expect(onCreated).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'pr-review' }),
        true,
      ),
    )
    expect(createSkill).toHaveBeenCalledTimes(1)
  })

  it('goes back from the replace step without saving', async () => {
    const { onOpenChange } = renderDialog()
    fill('create.nameLabel', 'pr-review')
    fill('create.descriptionLabel', 'Reviews pull requests')
    fireEvent.click(screen.getByRole('button', { name: 'create.submit' }))
    fireEvent.click(
      await screen.findByRole('button', { name: 'create.replace.back' }),
    )

    expect(screen.queryByText('create.replace.title')).toBeNull()
    expect(screen.getByRole('button', { name: 'create.submit' })).toBeTruthy()
    expect(createSkill).not.toHaveBeenCalled()
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })

  it('drops the replace step when the name changes', async () => {
    renderDialog()
    fill('create.nameLabel', 'pr-review')
    fill('create.descriptionLabel', 'Reviews pull requests')
    fireEvent.click(screen.getByRole('button', { name: 'create.submit' }))
    expect(await screen.findByText('create.replace.title')).toBeTruthy()

    fill('create.nameLabel', 'pr-review-2')
    expect(screen.queryByText('create.replace.title')).toBeNull()
  })

  it('scrolls the replace buttons into view', async () => {
    renderDialog()
    fill('create.nameLabel', 'pr-review')
    fill('create.descriptionLabel', 'Reviews pull requests')
    fireEvent.click(screen.getByRole('button', { name: 'create.submit' }))

    const replace = await screen.findByRole('button', {
      name: 'create.replace.confirm',
    })
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' })
    const scrolled = scrollIntoView.mock.contexts[0] as Element
    expect(scrolled.contains(replace)).toBe(true)
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
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(draft, false))
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
