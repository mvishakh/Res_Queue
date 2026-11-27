import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'
import { supabase } from '../lib/supabase'
import { useToast } from './Toast'
import { Button, ErrorBanner, Field, PasswordInput } from './ui'

export const MIN_PASSWORD_LENGTH = 8

/**
 * Lets signed-in staff change their own Supabase Auth password. The current password is
 * checked first, so an unattended signed-in device can't be used to take over the account.
 */
export function ChangePasswordForm({ onDone }: { onDone?: () => void }) {
  const { me } = useAuth()
  const toast = useToast()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (next.length < MIN_PASSWORD_LENGTH) return setError(`The new password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
    if (next !== confirm) return setError('The new passwords do not match.')
    if (next === current) return setError('Choose a password different from the current one.')
    if (!supabase || !me) return setError('You are not signed in.')

    setBusy(true)
    try {
      const check = await supabase.auth.signInWithPassword({ email: me.email, password: current })
      if (check.error) return setError('Your current password is incorrect.')
      const { error: updateError } = await supabase.auth.updateUser({ password: next })
      if (updateError) return setError(updateError.message)
      setCurrent('')
      setNext('')
      setConfirm('')
      toast('Password changed')
      onDone?.()
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <Field label="Current password">
        <PasswordInput required autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      </Field>
      <Field label="New password" hint={`At least ${MIN_PASSWORD_LENGTH} characters`}>
        <PasswordInput required autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
      </Field>
      <Field label="Confirm new password">
        <PasswordInput required autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </Field>
      <Button type="submit" loading={busy}>Change password</Button>
    </form>
  )
}
