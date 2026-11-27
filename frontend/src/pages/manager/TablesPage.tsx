import { TableCard } from '../../components/TableCard'
import { Card, EmptyState, ErrorBanner, PageHeader, Spinner } from '../../components/ui'
import { errorMessage } from '../../lib/api'
import { useTables } from '../../lib/queries'
import { useAuth } from '../../auth/AuthContext'
import { isOwner } from '../../lib/roles'
import { Link } from 'react-router'

/** Read-only floor view for the Queue Manager. Freeing tables is done on the Waiter Dashboard. */
export function TablesPage() {
  const { membership } = useAuth()
  const { data: tables, isLoading, error } = useTables()
  const available = tables?.filter((t) => t.status === 'AVAILABLE') ?? []
  const seats = tables?.reduce((n, t) => n + t.capacity, 0) ?? 0

  return (
    <>
      <PageHeader
        title="Tables Overview"
        description="Live table availability and allocations. Waiters mark tables available from their dashboard; allocation is automatic."
        actions={isOwner(membership?.role) ? <Link to="/manager/settings?tab=tables" className="inline-flex h-10 items-center rounded-lg border border-line bg-white px-4 text-sm font-medium hover:bg-brand-50">Configure tables</Link> : undefined}
      />
      {error && <ErrorBanner>{errorMessage(error)}</ErrorBanner>}
      {isLoading && <Spinner />}
      {tables && (
        <>
          <p className="mb-4 text-sm text-ink-muted">
            <span className="font-semibold text-ok">{available.length}</span> of {tables.length} tables available · {seats} seats in total
          </p>
          {tables.length === 0 ? (
            <Card><EmptyState title="No tables configured">{isOwner(membership?.role) ? 'Add tables in Settings.' : 'Ask the owner to add tables.'}</EmptyState></Card>
          ) : (
            <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
              {tables.map((t) => <TableCard key={t.id} table={t} canFree={false} />)}
            </div>
          )}
        </>
      )}
    </>
  )
}
