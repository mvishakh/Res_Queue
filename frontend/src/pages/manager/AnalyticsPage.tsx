import { useState } from 'react'
import { Card, cx, EmptyState, ErrorBanner, PageHeader, Spinner, StatCard } from '../../components/ui'
import { errorMessage } from '../../lib/api'
import { useAnalytics } from '../../lib/queries'

const RANGES = [7, 30, 90]

export function AnalyticsPage() {
  const [days, setDays] = useState(7)
  const { data, isLoading, error } = useAnalytics(days)

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Computed from real queue and allocation records."
        actions={
          <div className="flex rounded-lg border border-line bg-white p-0.5">
            {RANGES.map((d) => (
              <button key={d} onClick={() => setDays(d)} className={cx('rounded-md px-3 py-1.5 text-sm font-medium', d === days ? 'bg-brand-700 text-white' : 'text-ink-muted hover:text-ink')}>
                {d} days
              </button>
            ))}
          </div>
        }
      />
      {error && <ErrorBanner>{errorMessage(error)}</ErrorBanner>}
      {isLoading && <Spinner />}
      {data && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatCard label="Customers registered" value={data.registered} />
            <StatCard label="Customers served" value={data.served} hint="seated at a table" />
            <StatCard label="Average wait" value={data.avg_wait_minutes == null ? '—' : `${Math.round(data.avg_wait_minutes)} min`} hint="arrival → table allocated" />
            <StatCard label="Cancelled" value={data.cancelled} hint={`${data.no_shows} no-shows`} />
            <StatCard label="Median party size" value={data.median_party_size ?? '—'} />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <BarChart
              title="Registrations per day"
              points={data.daily.map((d) => ({
                key: d.date,
                label: new Date(d.date + 'T00:00:00').toLocaleDateString([], { day: 'numeric', month: 'short' }),
                value: d.registered,
                detail: `${d.served} served · ${d.cancelled} cancelled${d.avg_wait_minutes != null ? ` · avg wait ${Math.round(d.avg_wait_minutes)} min` : ''}`,
              }))}
            />
            <BarChart
              title="Registrations by hour of day"
              points={hourPoints(data.by_hour)}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="overflow-hidden">
              <h2 className="border-b border-line px-4 py-3 font-medium">Daily queue performance</h2>
              <div className="max-h-96 overflow-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-white text-left text-xs uppercase tracking-wide text-ink-muted">
                    <tr><th className="px-4 py-2 font-medium">Date</th><th className="px-4 py-2 text-right font-medium">Registered</th><th className="px-4 py-2 text-right font-medium">Served</th><th className="px-4 py-2 text-right font-medium">Cancelled</th><th className="px-4 py-2 text-right font-medium">Avg wait</th></tr>
                  </thead>
                  <tbody className="divide-y divide-line tabular-nums">
                    {[...data.daily].reverse().map((d) => (
                      <tr key={d.date}>
                        <td className="px-4 py-2">{d.date}</td>
                        <td className="px-4 py-2 text-right">{d.registered}</td>
                        <td className="px-4 py-2 text-right">{d.served}</td>
                        <td className="px-4 py-2 text-right">{d.cancelled}</td>
                        <td className="px-4 py-2 text-right">{d.avg_wait_minutes == null ? '—' : `${Math.round(d.avg_wait_minutes)} min`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <Card className="overflow-hidden">
              <h2 className="border-b border-line px-4 py-3 font-medium">Table allocation history</h2>
              {data.table_usage.length === 0 ? <EmptyState title="No allocations in this period" /> : (
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase tracking-wide text-ink-muted">
                    <tr><th className="px-4 py-2 font-medium">Table</th><th className="px-4 py-2 text-right font-medium">Seats</th><th className="px-4 py-2 text-right font-medium">Parties seated</th></tr>
                  </thead>
                  <tbody className="divide-y divide-line tabular-nums">
                    {data.table_usage.map((t) => (
                      <tr key={t.table_number}><td className="px-4 py-2 font-medium">{t.table_number}</td><td className="px-4 py-2 text-right">{t.capacity}</td><td className="px-4 py-2 text-right">{t.allocations}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  )
}

/** Hours from the first to the last hour with registrations (inclusive), zeros kept in between. */
function hourPoints(byHour: { hour: number; registrations: number }[]): Point[] {
  if (!byHour.length) return []
  const counts = new Map(byHour.map((h) => [h.hour, h.registrations]))
  const first = Math.min(...byHour.map((h) => h.hour))
  const last = Math.max(...byHour.map((h) => h.hour))
  return Array.from({ length: last - first + 1 }, (_, i) => {
    const h = first + i
    return { key: String(h), label: `${h}:00`, value: counts.get(h) ?? 0, detail: `${h}:00–${h}:59` }
  })
}

interface Point { key: string; label: string; value: number; detail?: string }

/** Single-series bar chart: one brand hue, thin bars with rounded tops, recessive axis, hover tooltip. */
function BarChart({ title, points }: { title: string; points: Point[] }) {
  const [hover, setHover] = useState<string | null>(null)
  const max = Math.max(1, ...points.map((p) => p.value))
  const ticks = [0, Math.ceil(max / 2), max].filter((v, i, a) => a.indexOf(v) === i)
  const active = points.find((p) => p.key === hover)
  const labelEvery = Math.ceil(points.length / 8)

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="font-medium">{title}</h2>
        <p className="min-h-5 text-right text-xs text-ink-muted" aria-live="polite">
          {active ? <><span className="font-semibold text-ink">{active.label}: {active.value}</span>{active.detail && ` · ${active.detail}`}</> : 'Hover a bar for details'}
        </p>
      </div>
      {points.length === 0 || points.every((p) => p.value === 0) ? (
        <EmptyState title="No data in this period" />
      ) : (
        <div className="flex gap-2">
          <div className="relative h-44 w-6 text-right text-[11px] tabular-nums text-ink-muted" aria-hidden>
            {ticks.map((t) => <span key={t} className="absolute right-0 translate-y-1/2" style={{ bottom: `${(t / max) * 100}%` }}>{t}</span>)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="relative h-44 border-b border-line" role="img" aria-label={`${title}: ${points.map((p) => `${p.label} ${p.value}`).join(', ')}`}>
              {ticks.slice(1).map((t) => <div key={t} className="absolute inset-x-0 border-t border-dashed border-line" style={{ bottom: `${(t / max) * 100}%` }} />)}
              <div className="absolute inset-0 flex items-end gap-[2px]">
                {points.map((p) => (
                  <div
                    key={p.key}
                    className="flex h-full flex-1 cursor-default items-end justify-center"
                    onMouseEnter={() => setHover(p.key)}
                    onMouseLeave={() => setHover(null)}
                  >
                    <div
                      className={cx('w-full max-w-6 rounded-t-[4px] transition-colors', hover === p.key ? 'bg-brand-800' : 'bg-brand-600')}
                      style={{ height: `${(p.value / max) * 100}%`, minHeight: p.value ? 2 : 0 }}
                    />
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-1 flex gap-[2px] text-[11px] text-ink-muted" aria-hidden>
              {points.map((p, i) => <span key={p.key} className="flex-1 truncate text-center">{i % labelEvery === 0 ? p.label : ''}</span>)}
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}
