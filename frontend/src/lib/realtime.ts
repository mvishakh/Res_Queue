import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { supabase } from './supabase'
import type { StaffRole } from './types'

/**
 * Live dashboard sync through Supabase Realtime (Postgres Changes).
 *
 * Change events are used only as a signal: on any change the affected queries are
 * re-fetched from FastAPI, which remains the single source of truth. Row Level Security
 * limits which rows each staff member can receive (waiters get table and allocation
 * changes only — never customer or queue rows).
 */
const TABLE_TO_QUERIES: Record<string, string[][]> = {
  dining_tables: [['tables'], ['overview']],
  table_allocations: [['tables'], ['allocations'], ['overview'], ['queue']],
  queue_entries: [['queue'], ['overview'], ['customers']],
  whatsapp_messages: [['notifications'], ['overview'], ['queue']],
}

export function useRealtimeSync(restaurantId: string | undefined, role: StaffRole | undefined) {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!supabase || !restaurantId || !role) return
    const watched = role === 'WAITER' ? ['dining_tables', 'table_allocations'] : Object.keys(TABLE_TO_QUERIES)

    const pending = new Set<string>()
    let timer: ReturnType<typeof setTimeout> | undefined
    const flush = () => {
      const keys = new Set<string>()
      pending.forEach((t) => TABLE_TO_QUERIES[t].forEach((k) => keys.add(JSON.stringify(k))))
      pending.clear()
      keys.forEach((k) => queryClient.invalidateQueries({ queryKey: JSON.parse(k) }))
    }

    const channel = supabase.channel(`restaurant-${restaurantId}`)
    for (const table of watched) {
      channel.on(
        'postgres_changes',
        { event: '*', schema: 'public', table, filter: `restaurant_id=eq.${restaurantId}` },
        () => {
          // One allocation touches several tables at once; batch the refetches.
          pending.add(table)
          clearTimeout(timer)
          timer = setTimeout(flush, 250)
        },
      )
    }
    channel.subscribe()
    return () => {
      clearTimeout(timer)
      supabase?.removeChannel(channel)
    }
  }, [restaurantId, role, queryClient])
}
