import { Bell, CircleCheckBig, LayoutGrid, UserRound } from 'lucide-react'
import { NavLink, Outlet } from 'react-router'
import { useAuth } from '../auth/AuthContext'
import { cx } from '../components/ui'
import { useRealtimeSync } from '../lib/realtime'

/** Dashboard 2 — Waiter Dashboard. Deliberately minimal: tables first. */
export function WaiterLayout() {
  const { membership } = useAuth()
  useRealtimeSync(membership?.restaurant_id, membership?.role)

  const nav = [
    { to: '/waiter', label: 'Tables', long: 'Table Overview', icon: LayoutGrid, end: true },
    { to: '/waiter/availability', label: 'Free a table', long: 'Table Availability', icon: CircleCheckBig },
    { to: '/waiter/updates', label: 'Updates', long: 'Allocation Updates', icon: Bell },
    { to: '/waiter/profile', label: 'Profile', long: 'Profile', icon: UserRound },
  ]
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    cx('flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium', isActive ? 'bg-brand-50 text-brand-800' : 'text-ink-muted hover:text-ink')

  return (
    <div className="flex min-h-full flex-col pb-20 md:pb-0">
      <header className="sticky top-0 z-30 border-b border-line bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="grid size-8 place-items-center rounded-lg bg-brand-700 text-xs font-bold text-white">SQ</div>
            <div>
              <p className="text-sm font-semibold leading-tight">Waiter Dashboard</p>
              <p className="text-xs text-ink-muted">{membership?.restaurant_name}</p>
            </div>
          </div>
          <nav className="ml-auto hidden gap-1 md:flex">
            {nav.map(({ to, long, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} className={linkClass}>
                <Icon className="size-4" aria-hidden /> {long}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-5">
        <Outlet />
      </main>
      {/* Thumb-friendly bottom navigation on phones */}
      <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t border-line bg-white md:hidden">
        {nav.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => cx('flex flex-col items-center gap-0.5 py-2.5 text-[11px] font-medium', isActive ? 'text-brand-700' : 'text-ink-muted')}
          >
            <Icon className="size-5" aria-hidden />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
