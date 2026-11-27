import {
  BarChart3, ClipboardList, History, LayoutDashboard, LayoutGrid, LogOut, Menu as MenuIcon, Settings, UserPlus, Users, UtensilsCrossed, X,
} from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router'
import { useAuth } from '../auth/AuthContext'
import { cx } from '../components/ui'
import { useRealtimeSync } from '../lib/realtime'
import { isOwner, ROLE_LABELS } from '../lib/roles'

/** Dashboard 1 — Queue Manager Dashboard (receptionists, queue managers, owners/administrators). */
export function QueueManagerLayout() {
  const { me, membership, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  useRealtimeSync(membership?.restaurant_id, membership?.role)

  const nav = [
    { to: '/manager', label: 'Dashboard', icon: LayoutDashboard, end: true },
    { to: '/manager/register', label: 'Customer Registration', icon: UserPlus },
    { to: '/manager/waiting-list', label: 'Waiting List', icon: ClipboardList },
    { to: '/manager/tables', label: 'Tables Overview', icon: LayoutGrid },
    { to: '/manager/customers', label: 'Customers', icon: Users },
    { to: '/manager/menu', label: 'Menu Management', icon: UtensilsCrossed },
    { to: '/manager/allocations', label: 'Allocation History', icon: History },
    { to: '/manager/analytics', label: 'Analytics', icon: BarChart3 },
    ...(isOwner(membership?.role) ? [{ to: '/manager/settings', label: 'Settings', icon: Settings }] : []),
  ]

  const sidebar = (
    <nav className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-5 py-5">
        <div className="grid size-9 place-items-center rounded-lg bg-brand-700 text-sm font-bold text-white">SQ</div>
        <div className="min-w-0">
          <p className="font-semibold leading-tight">Smart Queue</p>
          <p className="truncate text-xs text-ink-muted">{membership?.restaurant_name}</p>
        </div>
      </div>
      <ul className="flex-1 space-y-0.5 px-3">
        {nav.map(({ to, label, icon: Icon, end }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={end}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                cx(
                  'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                  isActive ? 'bg-brand-50 text-brand-800' : 'text-ink-muted hover:bg-brand-50/60 hover:text-ink',
                )
              }
            >
              <Icon className="size-4.5" aria-hidden />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="border-t border-line p-4">
        <p className="truncate text-sm font-medium">{me?.full_name}</p>
        <p className="text-xs text-ink-muted">{membership && ROLE_LABELS[membership.role]}</p>
        <button onClick={() => signOut()} className="mt-3 flex items-center gap-2 text-sm text-ink-muted hover:text-ink">
          <LogOut className="size-4" aria-hidden /> Sign out
        </button>
      </div>
    </nav>
  )

  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-line bg-white lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-ink/40" />
          <aside className="absolute inset-y-0 left-0 w-72 bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>{sidebar}</aside>
        </div>
      )}
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-white/95 px-4 py-3 backdrop-blur lg:hidden">
          <button onClick={() => setOpen(!open)} aria-label="Open navigation" className="rounded-md p-1.5 hover:bg-brand-50">
            {open ? <X className="size-5" /> : <MenuIcon className="size-5" />}
          </button>
          <p className="font-semibold">Smart Queue</p>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
