import { supabase } from './supabase'

const API_URL = ((import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  code: string
  details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

let restaurantId: string | null = null

/** The restaurant all staff API calls are scoped to (sent as X-Restaurant-Id). */
export function setActiveRestaurant(id: string | null) {
  restaurantId = id
}

async function authHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {}
  const { data } = (await supabase?.auth.getSession()) ?? { data: { session: null } }
  if (data.session) headers.Authorization = `Bearer ${data.session.access_token}`
  if (restaurantId) headers['X-Restaurant-Id'] = restaurantId
  return headers
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; form?: FormData; auth?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = options.auth === false ? {} : await authHeaders()
  let body: BodyInit | undefined
  if (options.form) body = options.form
  else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  let response: Response
  try {
    response = await fetch(`${API_URL}/api${path}`, { method: options.method ?? 'GET', headers, body })
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the Smart Queue server. Check your connection.')
  }

  if (response.status === 204) return undefined as T
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const err = data?.error
    throw new ApiError(
      response.status,
      err?.code ?? 'error',
      err?.message ?? data?.detail ?? `Request failed (${response.status})`,
      err?.details ?? {},
    )
  }
  return data as T
}

export const errorMessage = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong')
