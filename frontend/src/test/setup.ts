import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Guard: tests must never use the real Supabase project or API from .env.local.
if (import.meta.env.VITE_SUPABASE_URL || import.meta.env.VITE_SUPABASE_ANON_KEY) {
  throw new Error('Tests must not load real Supabase credentials (check test.env in vite.config.ts)')
}

afterEach(() => cleanup())
