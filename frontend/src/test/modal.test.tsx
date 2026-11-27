import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Input, Modal } from '../components/ui'

// Mirrors how pages use Modal: an inline onClose arrow (new function every render) and
// controlled inputs that re-render the parent on every keystroke.
function StaffLikeForm({ onClose = () => {} }: { onClose?: () => void }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  return (
    <Modal open title="Add staff member" onClose={() => onClose()}>
      <label>Full name<Input autoFocus value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label>Email<Input value={email} onChange={(e) => setEmail(e.target.value)} /></label>
    </Modal>
  )
}

describe('Modal', () => {
  it('keeps focus in the field while typing a full name in one go', async () => {
    const user = userEvent.setup()
    render(<StaffLikeForm />)
    const name = screen.getByLabelText('Full name')
    expect(name).toHaveFocus()
    await user.keyboard('Arun Kumar')
    expect(name).toHaveValue('Arun Kumar')
    expect(name).toHaveFocus()
  })

  it('keeps focus when typing into a field clicked by the user', async () => {
    const user = userEvent.setup()
    render(<StaffLikeForm />)
    const email = screen.getByLabelText('Email')
    await user.click(email)
    await user.keyboard('waiter@example.com')
    expect(email).toHaveValue('waiter@example.com')
  })

  it('still closes on Escape using the latest onClose', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<StaffLikeForm onClose={onClose} />)
    await user.keyboard('abc{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
