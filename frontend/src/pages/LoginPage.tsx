import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router'
import { useAuth } from '../auth/AuthContext'
import { Button, Card, ErrorBanner, Field, Input, PasswordInput } from '../components/ui'
import { homePathFor } from '../lib/roles'

/** One shared staff login. After sign-in, staff are routed to the dashboard for their role. */
export function LoginPage() {
  const { status, membership, signIn, error: authError } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (status === 'signed-in' && membership) return <Navigate to={homePathFor(membership.role)} replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await signIn(email.trim(), password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 grid size-12 place-items-center rounded-xl bg-brand-700 font-bold text-white">SQ</div>
          <h1 className="text-2xl font-semibold tracking-tight">Smart Queue</h1>
          <p className="mt-1 text-sm text-ink-muted">Staff sign in</p>
        </div>
        <Card className="p-6">
          <form onSubmit={submit} className="space-y-4">
            {(error || (status === 'error' && authError)) && <ErrorBanner>{error ?? authError}</ErrorBanner>}
            <Field label="Email"><Input type="email" required autoComplete="username" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
            <Field label="Password"><PasswordInput required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
            <Button type="submit" size="lg" className="w-full" loading={busy || (status === 'loading' && !!email)}>Sign in</Button>
          </form>
        </Card>
        <p className="mt-6 text-center text-xs text-ink-muted">Accounts are created by the restaurant owner.</p>
      </div>
    </div>
  )
}
