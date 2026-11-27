import type { Session } from '@supabase/supabase-js'
import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError, setActiveRestaurant } from '../lib/api'
import { supabase } from '../lib/supabase'
import type { Me, Membership } from '../lib/types'

export type AuthStatus = 'loading' | 'signed-out' | 'signed-in' | 'no-access' | 'error'

export interface AuthValue {
  status: AuthStatus
  me: Me | null
  membership: Membership | null
  error: string | null
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  selectRestaurant: (restaurantId: string) => void
}

export const AuthContext = createContext<AuthValue | null>(null)

const STORAGE_KEY = 'smartqueue.restaurant'

function readStoredRestaurant(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [session, setSession] = useState<Session | null | undefined>(undefined)
  const [me, setMe] = useState<Me | null>(null)
  const [restaurantId, setRestaurantId] = useState<string | null>(readStoredRestaurant)
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!supabase) {
      setStatus('error')
      setError('Supabase is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.')
      return
    }
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => data.subscription.unsubscribe()
  }, [])

  const userId = session?.user.id
  useEffect(() => {
    if (session === undefined) return
    if (!userId) {
      queryClient.clear() // never show one user's cached data to the next
      setMe(null)
      setActiveRestaurant(null)
      setStatus('signed-out')
      return
    }
    let cancelled = false
    setStatus('loading')
    api<Me>('/auth/me')
      .then((data) => {
        if (cancelled) return
        setMe(data)
        setStatus(data.memberships.length ? 'signed-in' : 'no-access')
      })
      .catch((e: unknown) => {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 403) setStatus('no-access')
        else {
          setStatus('error')
          setError(e instanceof Error ? e.message : 'Could not load your account')
        }
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId])

  const membership = useMemo(() => {
    if (!me?.memberships.length) return null
    return me.memberships.find((m) => m.restaurant_id === restaurantId) ?? me.memberships[0]
  }, [me, restaurantId])

  // Keep the API client scoped to the selected restaurant
  setActiveRestaurant(membership?.restaurant_id ?? null)

  const selectRestaurant = useCallback((id: string) => {
    queryClient.clear() // cached data belongs to the previous restaurant
    setRestaurantId(id)
    try {
      localStorage.setItem(STORAGE_KEY, id)
    } catch {
      /* storage unavailable — selection lasts for this tab only */
    }
  }, [queryClient])

  const signIn = useCallback(async (email: string, password: string) => {
    if (!supabase) throw new Error('Supabase is not configured')
    const { error: err } = await supabase.auth.signInWithPassword({ email, password })
    if (err) throw new Error(err.message === 'Invalid login credentials' ? 'Incorrect email or password' : err.message)
  }, [])

  const signOut = useCallback(async () => {
    await supabase?.auth.signOut()
  }, [])

  const value = useMemo<AuthValue>(
    () => ({ status, me, membership, error, signIn, signOut, selectRestaurant }),
    [status, me, membership, error, signIn, signOut, selectRestaurant],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
