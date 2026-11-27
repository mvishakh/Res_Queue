import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useToast } from '../../components/Toast'
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorBanner, Field, Input, MessageStatusBadge, PageHeader, Select, Spinner } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import { formatDateTime } from '../../lib/format'
import { useAllocations, useTables } from '../../lib/queries'
import type { Allocation } from '../../lib/types'

const END_LABEL: Record<NonNullable<Allocation['end_reason']>, string> = {
  TABLE_FREED: 'Finished',
  NO_SHOW: 'No-show',
  REVERTED: 'Reverted',
  REASSIGNED: 'Moved',
}

export function AllocationsPage() {
  const { data, isLoading, error } = useAllocations(200)
  const { data: tables } = useTables()
  const qc = useQueryClient()
  const toast = useToast()
  const [releasing, setReleasing] = useState<Allocation | null>(null)
  const [moving, setMoving] = useState<Allocation | null>(null)
  const [target, setTarget] = useState('')
  const [reason, setReason] = useState('')

  const done = (msg: string) => {
    toast(msg)
    setReleasing(null)
    setMoving(null)
    setReason('')
    setTarget('')
    qc.invalidateQueries()
  }
  const release = useMutation({
    mutationFn: (a: Allocation) => api<Allocation>(`/allocations/${a.id}/release`, { method: 'POST', body: { reason: reason || null } }),
    onSuccess: (a) => done(`${a.table_number} released. The next matching party is seated automatically.`),
    onError: (e) => toast(errorMessage(e), 'error'),
  })
  const reassign = useMutation({
    mutationFn: (a: Allocation) => api<Allocation>(`/allocations/${a.id}/reassign`, { method: 'POST', body: { table_id: target, reason: reason || null } }),
    onSuccess: (a) => done(`${a.queue_number} moved to ${a.table_number}. Customer notified.`),
    onError: (e) => toast(errorMessage(e), 'error'),
  })

  const fittingTables = (tables ?? []).filter((t) => t.status === 'AVAILABLE' && moving && t.capacity >= moving.party_size)

  return (
    <>
      <PageHeader
        title="Allocation History"
        description="Every table assignment, newest first. Corrections are for exceptions only and are recorded in the activity log."
      />
      {error && <ErrorBanner>{errorMessage(error)}</ErrorBanner>}
      <Card className="overflow-hidden">
        {isLoading ? <div className="p-6"><Spinner /></div> : !data?.length ? <EmptyState title="No allocations yet" /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead className="border-b border-line bg-canvas/60 text-left text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Allocated</th>
                  <th className="px-4 py-3 font-medium">Table</th>
                  <th className="px-4 py-3 font-medium">Customer</th>
                  <th className="px-4 py-3 text-right font-medium">Guests</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">WhatsApp</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.map((a) => (
                  <tr key={a.id}>
                    <td className="px-4 py-3 tabular-nums">{formatDateTime(a.allocated_at)}</td>
                    <td className="px-4 py-3 font-semibold">{a.table_number} <span className="font-normal text-ink-muted">({a.table_capacity})</span></td>
                    <td className="px-4 py-3"><span className="font-medium text-brand-700">{a.queue_number}</span> · {a.customer_name}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{a.party_size}</td>
                    <td className="px-4 py-3">{a.allocation_type === 'AUTOMATIC' ? 'Automatic' : <Badge tone="warn">Manual override</Badge>}</td>
                    <td className="px-4 py-3">
                      {a.status === 'ACTIVE' ? <Badge tone="ok">Seated</Badge> : <Badge tone={a.end_reason === 'TABLE_FREED' ? 'neutral' : 'warn'}>{a.end_reason ? END_LABEL[a.end_reason] : a.status}</Badge>}
                      {a.ended_at && <span className="ml-2 text-xs text-ink-muted">{formatDateTime(a.ended_at)}</span>}
                    </td>
                    <td className="px-4 py-3">{a.notification_status ? <MessageStatusBadge status={a.notification_status} /> : '—'}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      {a.status === 'ACTIVE' && (
                        <>
                          <Button size="sm" variant="ghost" onClick={() => setMoving(a)}>Move</Button>
                          <Button size="sm" variant="ghost" className="text-red-700" onClick={() => setReleasing(a)}>No-show</Button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <ConfirmDialog
        open={!!releasing}
        title={`Release ${releasing?.table_number}?`}
        danger
        confirmLabel="Customer did not arrive"
        loading={release.isPending}
        message={<>{releasing?.queue_number} ({releasing?.customer_name}) will be cancelled as a no-show and {releasing?.table_number} offered to the next matching party.</>}
        onClose={() => setReleasing(null)}
        onConfirm={() => releasing && release.mutate(releasing)}
      >
        <div className="mt-4"><Field label="Note (optional)"><Input value={reason} maxLength={255} onChange={(e) => setReason(e.target.value)} /></Field></div>
      </ConfirmDialog>

      <ConfirmDialog
        open={!!moving}
        title={`Move ${moving?.queue_number} to another table`}
        confirmLabel="Move party"
        loading={reassign.isPending}
        message={<>Manual override. {moving?.table_number} becomes free for the queue and the customer is sent the new table number.</>}
        onClose={() => setMoving(null)}
        onConfirm={() => moving && target && reassign.mutate(moving)}
      >
        <div className="mt-4 space-y-3">
          <Field label="New table" hint={fittingTables.length ? undefined : 'No available table fits this party right now.'}>
            <Select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Choose a table…</option>
              {fittingTables.map((t) => <option key={t.id} value={t.id}>{t.table_number} — seats {t.capacity}</option>)}
            </Select>
          </Field>
          <Field label="Reason"><Input value={reason} maxLength={255} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Guest requested a quieter table" /></Field>
        </div>
      </ConfirmDialog>
    </>
  )
}
