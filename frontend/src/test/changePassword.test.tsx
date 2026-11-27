import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthValue } from '../auth/AuthContext'
import { ChangePasswordForm } from '../components/ChangePasswordForm'
import { ToastProvider } from '../components/Toast'

const sb = vi.hoisted(() => ({ signInWithPassword: vi.fn(), updateUser: vi.fn() }))
vi.mock('../lib/supabase', () => ({ supabaseConfigured: true, supabase: { auth: sb } }))

const auth: AuthValue = {
  status: 'signed-in',
  me: { id: 'u1', email: 'owner@example.com', full_name: 'Owner', memberships: [] },
  membership: null,
  error: null,
  signIn: vi.fn(),
  signOut: vi.fn(),
  selectRestaurant: vi.fn(),
}

function setup(onDone = vi.fn()) {
  render(
    <AuthContext.Provider value={auth}>
      <ToastProvider><ChangePasswordForm onDone={onDone} /></ToastProvider>
    </AuthContext.Provider>,
  )
  return onDone
}

async function fill(current: string, next: string, confirm: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Current password'), current)
  await user.type(screen.getByLabelText(/^New password/), next)
  await user.type(screen.getByLabelText('Confirm new password'), confirm)
  await user.click(screen.getByRole('button', { name: 'Change password' }))
}

beforeEach(() => {
  sb.signInWithPassword.mockReset().mockResolvedValue({ error: null })
  sb.updateUser.mockReset().mockResolvedValue({ error: null })
})

describe('ChangePasswordForm', () => {
  it('rejects a short new password without calling Supabase', async () => {
    setup()
    await fill('oldpass12', 'short', 'short')
    expect(await screen.findByRole('alert')).toHaveTextContent('at least 8 characters')
    expect(sb.updateUser).not.toHaveBeenCalled()
  })

  it('rejects mismatched confirmation', async () => {
    setup()
    await fill('oldpass12', 'newpass123', 'newpass124')
    expect(await screen.findByRole('alert')).toHaveTextContent('do not match')
    expect(sb.updateUser).not.toHaveBeenCalled()
  })

  it('refuses to change the password when the current password is wrong', async () => {
    sb.signInWithPassword.mockResolvedValue({ error: { message: 'Invalid login credentials' } })
    setup()
    await fill('wrongpass', 'newpass123', 'newpass123')
    expect(await screen.findByRole('alert')).toHaveTextContent('current password is incorrect')
    expect(sb.signInWithPassword).toHaveBeenCalledWith({ email: 'owner@example.com', password: 'wrongpass' })
    expect(sb.updateUser).not.toHaveBeenCalled()
  })

  it('changes the password after verifying the current one', async () => {
    const onDone = setup()
    await fill('oldpass12', 'newpass123', 'newpass123')
    expect(await screen.findByText('Password changed')).toBeInTheDocument()
    expect(sb.updateUser).toHaveBeenCalledWith({ password: 'newpass123' })
    expect(onDone).toHaveBeenCalled()
  })
})
