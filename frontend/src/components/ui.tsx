import { Loader2, X } from 'lucide-react'
import { useEffect, useRef, type ButtonHTMLAttributes, type ComponentProps, type ReactNode } from 'react'
import type { MessageStatus, QueueStatus } from '../lib/types'

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'success'
const VARIANTS: Record<Variant, string> = {
  primary: 'bg-brand-700 text-white hover:bg-brand-800 disabled:bg-brand-300',
  secondary: 'bg-white text-ink border border-line hover:bg-brand-50 disabled:text-ink-muted',
  danger: 'bg-white text-red-700 border border-red-200 hover:bg-red-50',
  ghost: 'text-ink-muted hover:bg-brand-50 hover:text-ink',
  success: 'bg-ok text-white hover:bg-green-700 disabled:bg-green-300',
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md' | 'lg'; loading?: boolean }) {
  const sizes = { sm: 'h-8 px-3 text-sm', md: 'h-10 px-4 text-sm', lg: 'h-12 px-5 text-base' }
  return (
    <button
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed',
        VARIANTS[variant],
        sizes[size],
        className,
      )}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  )
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx('rounded-xl border border-line bg-white', className)}>{children}</div>
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-ink-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

export function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string | null; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium">{label}</span>
      {children}
      {error ? <span className="mt-1 block text-sm text-red-700">{error}</span> : hint && <span className="mt-1 block text-xs text-ink-muted">{hint}</span>}
    </label>
  )
}

const inputClass =
  'w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm outline-none placeholder:text-ink-muted/70 focus:border-brand-500 focus:ring-2 focus:ring-brand-100'

export const Input = ({ className, ...p }: ComponentProps<'input'>) => <input className={cx(inputClass, className)} {...p} />
export const Textarea = ({ className, ...p }: ComponentProps<'textarea'>) => <textarea className={cx(inputClass, className)} {...p} />
export const Select = ({ className, ...p }: ComponentProps<'select'>) => <select className={cx(inputClass, className)} {...p} />

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink-muted" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden /> {label ?? 'Loading…'}
    </div>
  )
}

export function FullPageMessage({ title, children }: { title?: string; children?: ReactNode }) {
  return (
    <div className="flex min-h-full items-center justify-center p-6">
      <div className="max-w-md text-center">
        {title && <h1 className="mb-2 text-xl font-semibold">{title}</h1>}
        <div className="flex flex-col items-center text-sm text-ink-muted">{children}</div>
      </div>
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-6 py-12 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 text-sm text-ink-muted">{children}</div>}
    </div>
  )
}

export function ErrorBanner({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">{children}</div>
}

export function Badge({ tone = 'neutral', children }: { tone?: 'neutral' | 'brand' | 'ok' | 'warn' | 'bad' | 'info'; children: ReactNode }) {
  const tones = {
    neutral: 'bg-slate-100 text-slate-700',
    brand: 'bg-brand-100 text-brand-800',
    ok: 'bg-ok-soft text-green-800',
    warn: 'bg-amber-100 text-amber-800',
    bad: 'bg-red-100 text-red-800',
    info: 'bg-sky-100 text-sky-800',
  }
  return <span className={cx('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap', tones[tone])}>{children}</span>
}

const QUEUE_TONES: Record<QueueStatus, 'brand' | 'ok' | 'neutral' | 'bad'> = {
  WAITING: 'brand',
  ASSIGNED: 'ok',
  COMPLETED: 'neutral',
  CANCELLED: 'bad',
}
export const QueueStatusBadge = ({ status }: { status: QueueStatus }) => (
  <Badge tone={QUEUE_TONES[status]}>{status.charAt(0) + status.slice(1).toLowerCase()}</Badge>
)

const MSG: Record<MessageStatus, { tone: 'neutral' | 'brand' | 'ok' | 'warn' | 'bad' | 'info'; label: string }> = {
  PENDING: { tone: 'warn', label: 'Sending' },
  SENT: { tone: 'info', label: 'Sent' },
  DELIVERED: { tone: 'ok', label: 'Delivered' },
  READ: { tone: 'ok', label: 'Read' },
  FAILED: { tone: 'bad', label: 'Failed' },
  SKIPPED: { tone: 'neutral', label: 'Not sent' },
}
export const MessageStatusBadge = ({ status, title }: { status: MessageStatus; title?: string | null }) => (
  <span title={title ?? undefined}><Badge tone={MSG[status].tone}>{MSG[status].label}</Badge></span>
)

export function Modal({ open, title, onClose, children, footer }: { open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    ref.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-0 sm:items-center sm:p-4" onMouseDown={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="max-h-[90vh] w-full overflow-y-auto rounded-t-2xl bg-white shadow-xl outline-none sm:max-w-lg sm:rounded-2xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="font-semibold">{title}</h2>
          <button onClick={onClose} className="rounded-md p-1 text-ink-muted hover:bg-brand-50" aria-label="Close"><X className="size-5" /></button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  )
}

export function ConfirmDialog({
  open, title, message, confirmLabel = 'Confirm', danger, loading, onConfirm, onClose, children,
}: {
  open: boolean; title: string; message: ReactNode; confirmLabel?: string; danger?: boolean; loading?: boolean
  onConfirm: () => void; onClose: () => void; children?: ReactNode
}) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Go back</Button>
          <Button variant={danger ? 'danger' : 'primary'} loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
        </>
      }
    >
      <div className="text-sm text-ink-muted">{message}</div>
      {children}
    </Modal>
  )
}

export function StatCard({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: 'ok' | 'bad' }) {
  return (
    <Card className="p-4">
      <p className="text-sm text-ink-muted">{label}</p>
      <p className={cx('mt-1 text-3xl font-semibold tabular-nums', tone === 'ok' && 'text-ok', tone === 'bad' && 'text-red-700')}>{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-muted">{hint}</p>}
    </Card>
  )
}
