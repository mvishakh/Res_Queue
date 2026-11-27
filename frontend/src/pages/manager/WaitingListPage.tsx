import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { useToast } from '../../components/Toast'
import { Button, Card, ConfirmDialog, cx, EmptyState, ErrorBanner, Field, Input, MessageStatusBadge, PageHeader, QueueStatusBadge, Spinner } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import { formatDuration, formatTime, minutesBetween, useNow } from '../../lib/format'
import { useQueue } from '../../lib/queries'
import type { QueueEntry, QueueStatus } from '../../lib/types'

const FILTERS: { key: string; label: string; statuses: QueueStatus[] }[] = [
  { key: 'waiting', label: 'Waiting', statuses: ['WAITING'] },
  { key: 'seated', label: 'Seated', statuses: ['ASSIGNED'] },
  { key: 'completed', label: 'Completed', statuses: ['COMPLETED'] },
  { key: 'cancelled', label: 'Cancelled', statuses: ['CANCELLED'] },
  { key: 'all', label: 'All', statuses: [] },
]

export function WaitingListPage() {
  const [filter, setFilter] = useState(FILTERS[0])
  const [search, setSearch] = useState('')
  const [cancelling, setCancelling] = useState<QueueEntry | null>(null)
  const [reason, setReason] = useState('')
  const now = useNow()
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, error } = useQueue(filter.statuses, search)

  const cancel = useMutation({
    mutationFn: (e: QueueEntry) => api<QueueEntry>(`/queue/${e.id}/cancel`, { method: 'PATCH', body: { reason: reason || null } }),
    onSuccess: (e) => {
      toast(`${e.queue_number} cancelled`)
      setCancelling(null)
      setReason('')
      qc.invalidateQueries({ queryKey: ['queue'] })
      qc.invalidateQueries({ queryKey: ['overview'] })
    },
    onError: (e) => toast(errorMessage(e), 'error'),
  })

  const showPosition = filter.key === 'waiting' && !search

  return (
    <>
      <PageHeader
        title="Waiting List"
        description="First come, first served. Customers who don't fit a free table keep their place until a suitable table opens."
        actions={<Link to="/manager/register" className="inline-flex h-10 items-center rounded-lg bg-brand-700 px-4 text-sm font-medium text-white hover:bg-brand-800">Add customer</Link>}
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex rounded-lg border border-line bg-white p-0.5" role="tablist">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              role="tab"
              aria-selected={f.key === filter.key}
              onClick={() => setFilter(f)}
              className={cx('rounded-md px-3 py-1.5 text-sm font-medium', f.key === filter.key ? 'bg-brand-700 text-white' : 'text-ink-muted hover:text-ink')}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
          <Input className="pl-9" placeholder="Search name, phone or queue no." value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search" />
        </div>
      </div>

      {error && <ErrorBanner>{errorMessage(error)}</ErrorBanner>}
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="p-6"><Spinner /></div>
        ) : !data?.items.length ? (
          <EmptyState title={filter.key === 'waiting' ? 'Nobody is waiting' : 'No customers found'} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm">
              <thead className="border-b border-line bg-canvas/60 text-left text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  {showPosition && <th className="px-4 py-3 font-medium">#</th>}
                  <th className="px-4 py-3 font-medium">Queue</th>
                  <th className="px-4 py-3 font-medium">Customer</th>
                  <th className="px-4 py-3 font-medium">Phone</th>
                  <th className="px-4 py-3 text-right font-medium">Guests</th>
                  <th className="px-4 py-3 font-medium">Arrival</th>
                  <th className="px-4 py-3 font-medium">Waiting</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">WhatsApp</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.items.map((e, i) => {
                  const end = e.assigned_at ?? e.cancelled_at
                  const waited = minutesBetween(e.arrived_at, end ? new Date(end).getTime() : now)
                  const lastMsg = e.messages[e.messages.length - 1]
                  return (
                    <tr key={e.id} className="hover:bg-brand-50/30">
                      {showPosition && <td className="px-4 py-3 tabular-nums text-ink-muted">{i + 1}</td>}
                      <td className="px-4 py-3 font-semibold text-brand-700">{e.queue_number}</td>
                      <td className="px-4 py-3">
                        <p className="font-medium">{e.customer.full_name}</p>
                        {e.notes && <p className="max-w-[16rem] truncate text-xs text-ink-muted" title={e.notes}>{e.notes}</p>}
                      </td>
                      <td className="px-4 py-3 tabular-nums">{e.customer.phone_e164}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{e.party_size}</td>
                      <td className="px-4 py-3 tabular-nums">{formatTime(e.arrived_at)}</td>
                      <td className="px-4 py-3">{formatDuration(waited)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          <QueueStatusBadge status={e.status} />
                          {e.allocation && e.status === 'ASSIGNED' && <span className="text-xs font-medium">{e.allocation.table_number}</span>}
                        </div>
                      </td>
                      <td className="px-4 py-3">{lastMsg ? <MessageStatusBadge status={lastMsg.status} title={lastMsg.last_error} /> : '—'}</td>
                      <td className="px-4 py-3 text-right">
                        {e.status === 'WAITING' && <Button size="sm" variant="ghost" onClick={() => setCancelling(e)}>Cancel</Button>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <ConfirmDialog
        open={!!cancelling}
        title={`Cancel ${cancelling?.queue_number}?`}
        danger
        confirmLabel="Cancel registration"
        loading={cancel.isPending}
        message={<>{cancelling?.customer.full_name} will be removed from the waiting list. The record is kept in history.</>}
        onClose={() => setCancelling(null)}
        onConfirm={() => cancelling && cancel.mutate(cancelling)}
      >
        <div className="mt-4">
          <Field label="Reason (optional)">
            <Input value={reason} maxLength={255} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Customer left" />
          </Field>
        </div>
      </ConfirmDialog>
    </>
  )
}
