import { useMutation, useQueryClient } from '@tanstack/react-query'
import { RotateCcw, Users } from 'lucide-react'
import { api, errorMessage } from '../lib/api'
import { formatTime } from '../lib/format'
import type { DiningTable, MarkAvailableResult } from '../lib/types'
import { useToast } from './Toast'
import { Badge, Button, Card, cx } from './ui'

export function useMarkAvailable() {
  const qc = useQueryClient()
  const toast = useToast()
  return useMutation({
    // Sends the allocation the waiter is looking at, so a double-tap can't free the next party.
    mutationFn: (t: DiningTable) =>
      api<MarkAvailableResult>(`/tables/${t.id}/available`, { method: 'PATCH', body: { allocation_id: t.current?.allocation_id ?? null } }),
    onSuccess: (r) => {
      toast(r.new_allocation ? `${r.table.table_number} → ${r.new_allocation.queue_number} (${r.new_allocation.party_size} guests). Customer notified on WhatsApp.` : r.message, r.new_allocation ? 'success' : 'info')
      qc.invalidateQueries({ queryKey: ['tables'] })
      qc.invalidateQueries({ queryKey: ['allocations'] })
    },
    onError: (e) => toast(errorMessage(e), 'error'),
  })
}

export function useUndoAvailable() {
  const qc = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: (t: DiningTable) => api<DiningTable>(`/tables/${t.id}/undo-available`, { method: 'POST' }),
    onSuccess: (t) => {
      toast(`Undone — ${t.table_number} is back with ${t.current?.queue_number ?? 'its previous party'}`)
      qc.invalidateQueries()
    },
    onError: (e) => toast(errorMessage(e), 'error'),
  })
}

/**
 * A table on the floor. Per the wireframe, occupied tables show who is seated rather
 * than a prominent "Occupied" label; the underlying status is still AVAILABLE/OCCUPIED.
 */
export function TableCard({ table, canFree, canUndo = true }: { table: DiningTable; canFree: boolean; canUndo?: boolean }) {
  const markAvailable = useMarkAvailable()
  const undo = useUndoAvailable()
  const available = table.status === 'AVAILABLE'
  const busy = markAvailable.isPending && markAvailable.variables?.id === table.id

  return (
    <Card className={cx('flex flex-col p-4', available && 'border-green-200 bg-green-50/40')}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-2xl font-semibold tracking-tight">{table.table_number}</p>
          <p className="mt-0.5 flex items-center gap-1 text-sm text-ink-muted">
            <Users className="size-3.5" aria-hidden /> Seats {table.capacity}
          </p>
        </div>
        {available && <Badge tone="ok">Available</Badge>}
      </div>

      <div className="mt-3 min-h-[3.25rem] flex-1 text-sm">
        {table.current ? (
          <>
            <p className="font-medium">
              <span className="text-brand-700">{table.current.queue_number}</span> · {table.current.customer_name}
            </p>
            <p className="text-ink-muted">
              {table.current.party_size} {table.current.party_size === 1 ? 'guest' : 'guests'} · since {formatTime(table.current.allocated_at)}
              {table.current.allocation_type === 'MANUAL_OVERRIDE' && ' · manual'}
            </p>
          </>
        ) : available ? (
          <p className="text-ink-muted">Ready for the next matching party</p>
        ) : (
          <p className="text-ink-muted">In use</p>
        )}
      </div>

      {canFree && !available && (
        <Button variant="success" size="lg" className="mt-3 w-full" loading={busy} onClick={() => markAvailable.mutate(table)}>
          Mark as Available
        </Button>
      )}
      {canUndo && table.can_undo_available && (
        <Button variant="ghost" size="sm" className="mt-2 self-start" loading={undo.isPending} onClick={() => undo.mutate(table)}>
          <RotateCcw className="size-3.5" aria-hidden /> Undo “available”
        </Button>
      )}
    </Card>
  )
}
