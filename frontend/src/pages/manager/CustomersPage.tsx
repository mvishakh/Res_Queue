import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { useState } from 'react'
import { Card, EmptyState, ErrorBanner, Input, MessageStatusBadge, Modal, PageHeader, QueueStatusBadge, Spinner } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import { formatDateTime } from '../../lib/format'
import { useCustomers } from '../../lib/queries'
import type { Customer, QueueEntry } from '../../lib/types'

export function CustomersPage() {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const { data, isLoading, error } = useCustomers(search)

  return (
    <>
      <PageHeader title="Customers" description="Customer records and their waiting-list history." />
      <div className="relative mb-4 w-full sm:w-80">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
        <Input className="pl-9" placeholder="Search name or phone" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search customers" />
      </div>
      {error && <ErrorBanner>{errorMessage(error)}</ErrorBanner>}
      <Card className="overflow-hidden">
        {isLoading ? <div className="p-6"><Spinner /></div> : !data?.length ? <EmptyState title="No customers yet" /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="border-b border-line bg-canvas/60 text-left text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">WhatsApp</th>
                  <th className="px-4 py-3 font-medium">Consent</th>
                  <th className="px-4 py-3 text-right font-medium">Visits</th>
                  <th className="px-4 py-3 font-medium">Last visit</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.map((c) => (
                  <tr key={c.id} className="cursor-pointer hover:bg-brand-50/40" onClick={() => setSelected(c.id)}>
                    <td className="px-4 py-3 font-medium text-brand-800">{c.full_name}</td>
                    <td className="px-4 py-3 tabular-nums">{c.phone_e164}</td>
                    <td className="px-4 py-3">{c.whatsapp_consent ? 'Yes' : 'No'}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{c.visits}</td>
                    <td className="px-4 py-3">{formatDateTime(c.last_visit_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {selected && <CustomerDetail id={selected} onClose={() => setSelected(null)} />}
    </>
  )
}

function CustomerDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['customer', id],
    queryFn: () => api<{ customer: Customer; history: QueueEntry[] }>(`/customers/${id}`),
  })
  return (
    <Modal open title={data?.customer.full_name ?? 'Customer'} onClose={onClose}>
      {isLoading || !data ? <Spinner /> : (
        <>
          <p className="text-sm tabular-nums">{data.customer.phone_e164}</p>
          <p className="text-sm text-ink-muted">
            WhatsApp consent: {data.customer.whatsapp_consent ? 'given' : 'not given'}
            {data.customer.whatsapp_consent_at && ` (recorded ${formatDateTime(data.customer.whatsapp_consent_at)})`}
          </p>
          <h3 className="mt-4 mb-2 text-sm font-medium">Visit history</h3>
          <ul className="divide-y divide-line rounded-lg border border-line">
            {data.history.map((e) => (
              <li key={e.id} className="space-y-1 px-3 py-2.5 text-sm">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-brand-700">{e.queue_number}</span>
                  <span className="text-ink-muted">{formatDateTime(e.arrived_at)} · {e.party_size} guests</span>
                  <span className="ml-auto"><QueueStatusBadge status={e.status} /></span>
                </div>
                <div className="flex flex-wrap gap-2 text-xs text-ink-muted">
                  {e.allocation && <span>Table {e.allocation.table_number}</span>}
                  {e.cancellation_reason && <span>{e.cancellation_reason}</span>}
                  {e.messages.map((m) => (
                    <span key={m.id} className="flex items-center gap-1">{m.message_type === 'MENU' ? 'Menu' : 'Table ready'}: <MessageStatusBadge status={m.status} title={m.last_error} /></span>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </Modal>
  )
}
