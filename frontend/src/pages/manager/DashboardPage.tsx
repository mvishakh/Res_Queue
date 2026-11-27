import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router'
import { useToast } from '../../components/Toast'
import { Button, Card, EmptyState, ErrorBanner, MessageStatusBadge, PageHeader, QueueStatusBadge, Spinner, StatCard } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import { formatTime } from '../../lib/format'
import { useNotifications, useOverview } from '../../lib/queries'

export function DashboardPage() {
  const { data, isLoading, error } = useOverview()

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Live view of the waiting list, tables and WhatsApp notifications."
        actions={<Link to="/manager/register" className="inline-flex h-10 items-center rounded-lg bg-brand-700 px-4 text-sm font-medium text-white hover:bg-brand-800">Add customer</Link>}
      />
      {error && <ErrorBanner>{errorMessage(error)}</ErrorBanner>}
      {isLoading && <Spinner />}
      {data && (
        <div className="space-y-6">
          {data.failed_notifications > 0 && <FailedMessages />}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Customers waiting" value={data.waiting_customers} />
            <StatCard label="Available tables" value={data.available_tables} hint={`of ${data.total_tables} tables`} tone="ok" />
            <StatCard label="Seated today" value={data.allocated_today} hint="automatic and manual allocations" />
            <StatCard label="Registered today" value={data.registered_today} />
          </div>

          <div className="grid gap-6 xl:grid-cols-3">
            <Card>
              <SectionTitle title="Recent registrations" to="/manager/waiting-list" />
              {data.recent_registrations.length === 0 ? <EmptyState title="No registrations yet" /> : (
                <ul className="divide-y divide-line">
                  {data.recent_registrations.map((r) => (
                    <li key={r.id} className="flex items-center gap-3 px-4 py-3 text-sm">
                      <span className="w-12 font-semibold text-brand-700">{r.queue_number}</span>
                      <span className="min-w-0 flex-1 truncate">{r.customer_name} · {r.party_size}</span>
                      <span className="text-ink-muted tabular-nums">{formatTime(r.arrived_at)}</span>
                      <QueueStatusBadge status={r.status} />
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <SectionTitle title="Recent table allocations" to="/manager/allocations" />
              {data.recent_allocations.length === 0 ? <EmptyState title="No allocations yet" /> : (
                <ul className="divide-y divide-line">
                  {data.recent_allocations.map((a) => (
                    <li key={a.id} className="flex items-center gap-3 px-4 py-3 text-sm">
                      <span className="w-10 font-semibold">{a.table_number}</span>
                      <span className="min-w-0 flex-1 truncate">{a.queue_number} · {a.customer_name} · {a.party_size}</span>
                      <span className="text-ink-muted tabular-nums">{formatTime(a.allocated_at)}</span>
                      {a.notification_status && <MessageStatusBadge status={a.notification_status} />}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <SectionTitle title="WhatsApp activity" />
              {data.recent_messages.length === 0 ? <EmptyState title="No messages yet" /> : (
                <ul className="divide-y divide-line">
                  {data.recent_messages.map((m) => (
                    <li key={m.id} className="flex items-center gap-3 px-4 py-3 text-sm">
                      <span className="min-w-0 flex-1 truncate">
                        {m.message_type === 'MENU' ? 'Menu' : 'Table ready'} → {m.customer_name}
                        {m.queue_number && <span className="text-ink-muted"> ({m.queue_number})</span>}
                      </span>
                      <span className="text-ink-muted tabular-nums">{formatTime(m.created_at)}</span>
                      <MessageStatusBadge status={m.status} title={m.last_error} />
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  )
}

function SectionTitle({ title, to }: { title: string; to?: string }) {
  return (
    <div className="flex items-center justify-between border-b border-line px-4 py-3">
      <h2 className="font-medium">{title}</h2>
      {to && <Link to={to} className="text-sm text-brand-700 hover:underline">View all</Link>}
    </div>
  )
}

/** Staff alert for WhatsApp messages that could not be delivered after all retries. */
function FailedMessages() {
  const { data } = useNotifications('FAILED')
  const qc = useQueryClient()
  const toast = useToast()
  const retry = useMutation({
    mutationFn: (id: string) => api(`/notifications/${id}/retry`, { method: 'POST' }),
    onSuccess: () => {
      toast('Message queued for another attempt')
      qc.invalidateQueries({ queryKey: ['notifications'] })
      qc.invalidateQueries({ queryKey: ['overview'] })
    },
    onError: (e) => toast(errorMessage(e), 'error'),
  })
  if (!data?.length) return null
  return (
    <Card className="border-red-200">
      <div className="flex items-center gap-2 border-b border-red-100 bg-red-50 px-4 py-3 text-red-800">
        <AlertTriangle className="size-4" aria-hidden />
        <p className="text-sm font-medium">WhatsApp messages could not be delivered — please inform these customers in person</p>
      </div>
      <ul className="divide-y divide-line">
        {data.slice(0, 8).map((m) => (
          <li key={m.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
            <span className="font-medium">{m.message_type === 'MENU' ? 'Menu' : 'Table ready'} → {m.customer_name} {m.queue_number && `(${m.queue_number})`}</span>
            <span className="tabular-nums text-ink-muted">{m.to_phone}</span>
            <span className="min-w-0 flex-1 truncate text-xs text-red-700" title={m.last_error ?? ''}>{m.last_error}</span>
            <Button size="sm" variant="secondary" loading={retry.isPending && retry.variables === m.id} onClick={() => retry.mutate(m.id)}>Retry</Button>
          </li>
        ))}
      </ul>
    </Card>
  )
}
