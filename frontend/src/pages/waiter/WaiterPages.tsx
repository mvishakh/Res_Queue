import { LogOut } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { TableCard, useMarkAvailable } from '../../components/TableCard'
import { Badge, Button, Card, EmptyState, ErrorBanner, PageHeader, Select, Spinner } from '../../components/ui'
import { errorMessage } from '../../lib/api'
import { formatTime } from '../../lib/format'
import { useAllocations, useTables } from '../../lib/queries'
import { ROLE_LABELS } from '../../lib/roles'

/** Table Overview — the waiter's home screen. */
export function WaiterTablesPage() {
  const { data: tables, isLoading, error } = useTables()
  const available = tables?.filter((t) => t.status === 'AVAILABLE').length ?? 0

  return (
    <>
      <PageHeader
        title="Table Overview"
        description="When guests leave, tap Mark as Available. The next matching customer is seated and notified automatically."
      />
      {error && <ErrorBanner>{errorMessage(error)}</ErrorBanner>}
      {isLoading && <Spinner />}
      {tables && (
        <>
          <p className="mb-4 text-sm text-ink-muted">
            <span className="font-semibold text-ok">{available}</span> of {tables.length} tables available
          </p>
          {tables.length === 0 ? (
            <Card><EmptyState title="No tables configured">The restaurant owner adds tables in Settings.</EmptyState></Card>
          ) : (
            <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
              {tables.map((t) => <TableCard key={t.id} table={t} canFree />)}
            </div>
          )}
        </>
      )}
    </>
  )
}

/** Table Availability — just the tables that can be freed, as a fast list. */
export function WaiterAvailabilityPage() {
  const { data: tables, isLoading, error } = useTables()
  const markAvailable = useMarkAvailable()
  const occupied = tables?.filter((t) => t.status === 'OCCUPIED') ?? []

  return (
    <>
      <PageHeader title="Table Availability" description="Tables with guests. Free a table as soon as the guests have left." />
      {error && <ErrorBanner>{errorMessage(error)}</ErrorBanner>}
      {isLoading && <Spinner />}
      {tables && (
        <Card>
          {occupied.length === 0 ? (
            <EmptyState title="Every table is available" />
          ) : (
            <ul className="divide-y divide-line">
              {occupied.map((t) => (
                <li key={t.id} className="flex items-center gap-4 px-4 py-3">
                  <div className="w-14 text-xl font-semibold">{t.table_number}</div>
                  <div className="min-w-0 flex-1 text-sm">
                    {t.current ? (
                      <>
                        <p className="truncate font-medium">{t.current.queue_number} · {t.current.customer_name}</p>
                        <p className="text-ink-muted">{t.current.party_size} guests · since {formatTime(t.current.allocated_at)}</p>
                      </>
                    ) : (
                      <p className="text-ink-muted">Seats {t.capacity}</p>
                    )}
                  </div>
                  <Button
                    variant="success"
                    loading={markAvailable.isPending && markAvailable.variables?.id === t.id}
                    onClick={() => markAvailable.mutate(t)}
                  >
                    Mark as Available
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </>
  )
}

/** Allocation Updates — what the engine just did, newest first. */
export function WaiterUpdatesPage() {
  const { data, isLoading, error } = useAllocations(40)
  return (
    <>
      <PageHeader title="Allocation Updates" description="Tables the system has assigned. Updates appear automatically." />
      {error && <ErrorBanner>{errorMessage(error)}</ErrorBanner>}
      {isLoading && <Spinner />}
      {data && (
        <Card>
          {data.length === 0 ? (
            <EmptyState title="No allocations yet" />
          ) : (
            <ul className="divide-y divide-line">
              {data.map((a) => (
                <li key={a.id} className="flex items-center gap-4 px-4 py-3 text-sm">
                  <div className="w-14 text-lg font-semibold">{a.table_number}</div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{a.queue_number} · {a.customer_name} · {a.party_size} guests</p>
                    <p className="text-ink-muted">
                      {formatTime(a.allocated_at)}
                      {a.allocation_type === 'MANUAL_OVERRIDE' && ' · manual override'}
                    </p>
                  </div>
                  {a.status === 'ACTIVE' ? <Badge tone="brand">Seated</Badge> : a.status === 'COMPLETED' ? <Badge>Finished</Badge> : <Badge tone="warn">Released</Badge>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </>
  )
}

export function WaiterProfilePage() {
  const { me, membership, signOut, selectRestaurant } = useAuth()
  return (
    <>
      <PageHeader title="Profile" />
      <Card className="max-w-md space-y-4 p-5">
        <div>
          <p className="text-lg font-semibold">{me?.full_name}</p>
          <p className="text-sm text-ink-muted">{me?.email}</p>
        </div>
        <p className="text-sm">
          {membership && ROLE_LABELS[membership.role]} at <span className="font-medium">{membership?.restaurant_name}</span>
        </p>
        {me && me.memberships.length > 1 && (
          <Select value={membership?.restaurant_id} onChange={(e) => selectRestaurant(e.target.value)} aria-label="Restaurant">
            {me.memberships.map((m) => <option key={m.restaurant_id} value={m.restaurant_id}>{m.restaurant_name}</option>)}
          </Select>
        )}
        <Button variant="secondary" onClick={() => signOut()}><LogOut className="size-4" aria-hidden /> Sign out</Button>
      </Card>
    </>
  )
}
