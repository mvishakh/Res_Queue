import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthValue } from '../auth/AuthContext'
import { LoginPage } from '../pages/LoginPage'

function renderLogin(signIn = vi.fn().mockResolvedValue(undefined)) {
  const auth: AuthValue = {
    status: 'signed-out', me: null, membership: null, error: null,
    signIn, signOut: vi.fn(), selectRestaurant: vi.fn(),
  }
  render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter><LoginPage /></MemoryRouter>
    </AuthContext.Provider>,
  )
  return signIn
}

describe('Login show-password toggle', () => {
  it('hides the password by default and reveals it on demand', async () => {
    const user = userEvent.setup()
    renderLogin()
    const password = screen.getByLabelText('Password')
    await user.type(password, '12345678')
    expect(password).toHaveAttribute('type', 'password')

    await user.click(screen.getByRole('button', { name: 'Show password' }))
    expect(password).toHaveAttribute('type', 'text')
    expect(password).toHaveValue('12345678')

    await user.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(password).toHaveAttribute('type', 'password')
  })

  it('toggling does not submit the form, and sign-in sends the typed values', async () => {
    const user = userEvent.setup()
    const signIn = renderLogin()
    await user.type(screen.getByLabelText('Email'), ' waiter@example.com ')
    await user.type(screen.getByLabelText('Password'), '12345678')
    await user.click(screen.getByRole('button', { name: 'Show password' }))
    expect(signIn).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(signIn).toHaveBeenCalledWith('waiter@example.com', '12345678')
  })
})
