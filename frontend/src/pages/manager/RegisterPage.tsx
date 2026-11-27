import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Minus, Plus } from 'lucide-react'
import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { useToast } from '../../components/Toast'
import { Button, Card, ConfirmDialog, ErrorBanner, Field, Input, MessageStatusBadge, PageHeader, QueueStatusBadge, Textarea } from '../../components/ui'
import { api, ApiError } from '../../lib/api'
import { formatTime } from '../../lib/format'
import type { QueueEntry } from '../../lib/types'

const empty = { name: '', phone: '', party_size: 2, notes: '', whatsapp_consent: false }

export function RegisterPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const nameRef = useRef<HTMLInputElement>(null)
  const [form, setForm] = useState(empty)
  const [created, setCreated] = useState<QueueEntry | null>(null)
  const [duplicate, setDuplicate] = useState<QueueEntry | null>(null)
  const [confirmReplace, setConfirmReplace] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const register = useMutation({
    mutationFn: () => api<QueueEntry>('/queue', { method: 'POST', body: { ...form, notes: form.notes || null } }),
    onSuccess: (entry) => {
      setCreated(entry)
      setForm(empty)
      setDuplicate(null)
      setError(null)
      qc.invalidateQueries({ queryKey: ['queue'] })
      qc.invalidateQueries({ queryKey: ['overview'] })
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === 'duplicate_active_registration') {
        setDuplicate(e.details.existing_entry as QueueEntry)
        setError(null)
      } else setError(e instanceof Error ? e.message : 'Registration failed')
    },
  })

  const cancelExisting = useMutation({
    mutationFn: (id: string) => api<QueueEntry>(`/queue/${id}/cancel`, { method: 'PATCH', body: { reason: 'Replaced by a new registration' } }),
    onSuccess: () => {
      setConfirmReplace(false)
      setDuplicate(null)
      toast('Previous registration cancelled')
      register.mutate()
    },
    onError: (e) => toast(e instanceof Error ? e.message : 'Could not cancel', 'error'),
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setCreated(null)
    register.mutate()
  }

  const setSize = (n: number) => setForm((f) => ({ ...f, party_size: Math.min(50, Math.max(1, n)) }))
  const menuMsg = created?.messages.find((m) => m.message_type === 'MENU')

  return (
    <>
      <PageHeader title="Customer Registration" description="Add a waiting customer. The digital menu is sent on WhatsApp automatically." />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <Card className="p-5 sm:p-6">
          <form onSubmit={submit} className="space-y-5">
            {error && <ErrorBanner>{error}</ErrorBanner>}
            <Field label="Customer name">
              <Input ref={nameRef} required maxLength={120} autoFocus autoComplete="off" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Arun Kumar" />
            </Field>
            <Field label="WhatsApp number" hint="Include the country code, or type a local number for this restaurant's country.">
              <Input required type="tel" inputMode="tel" autoComplete="off" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="+91 98765 43210" />
            </Field>
            <Field label="Number of guests">
              <div className="flex items-center gap-2">
                <Button type="button" variant="secondary" aria-label="Fewer guests" onClick={() => setSize(form.party_size - 1)}><Minus className="size-4" /></Button>
                <Input type="number" min={1} max={50} required className="w-20 text-center text-lg font-semibold" value={form.party_size} onChange={(e) => setSize(Number(e.target.value) || 1)} aria-label="Number of guests" />
                <Button type="button" variant="secondary" aria-label="More guests" onClick={() => setSize(form.party_size + 1)}><Plus className="size-4" /></Button>
                <div className="ml-2 hidden gap-1 sm:flex">
                  {[2, 4, 6].map((n) => (
                    <button key={n} type="button" onClick={() => setSize(n)} className="rounded-md border border-line px-2.5 py-1 text-sm hover:bg-brand-50">{n}</button>
                  ))}
                </div>
              </div>
            </Field>
            <Field label="Notes (optional)">
              <Textarea rows={2} maxLength={500} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="e.g. high chair needed" />
            </Field>
            <label className="flex items-start gap-3 rounded-lg border border-line bg-brand-50/50 p-3 text-sm">
              <input type="checkbox" className="mt-0.5 size-4 accent-brand-700" checked={form.whatsapp_consent} onChange={(e) => setForm({ ...form, whatsapp_consent: e.target.checked })} />
              <span>
                <span className="font-medium">Customer agrees to WhatsApp messages</span>
                <span className="block text-ink-muted">Menu link now, and a message when their table is ready. Without consent no messages are sent.</span>
              </span>
            </label>
            <Button type="submit" size="lg" className="w-full sm:w-auto" loading={register.isPending}>Add to waiting list</Button>
          </form>
        </Card>

        <div className="space-y-4">
          {created && (
            <Card className="border-green-200 p-5">
              <div className="flex items-center gap-2 text-ok"><CheckCircle2 className="size-5" aria-hidden /><span className="font-medium">Registered</span></div>
              <p className="mt-3 text-4xl font-bold tracking-tight text-brand-700">{created.queue_number}</p>
              <p className="mt-1 font-medium">{created.customer.full_name} · {created.party_size} guests</p>
              <p className="text-sm text-ink-muted">Arrived {formatTime(created.arrived_at)}</p>
              <div className="mt-3 space-y-1.5 text-sm">
                <p className="flex items-center gap-2">Status: <QueueStatusBadge status={created.status} />{created.allocation && created.status === 'ASSIGNED' && <span className="font-medium">Table {created.allocation.table_number}</span>}</p>
                {menuMsg && <p className="flex items-center gap-2">Menu on WhatsApp: <MessageStatusBadge status={menuMsg.status} title={menuMsg.last_error} /></p>}
              </div>
              <Button variant="secondary" size="sm" className="mt-4" onClick={() => { setCreated(null); nameRef.current?.focus() }}>Register next customer</Button>
            </Card>
          )}
          {duplicate && (
            <Card className="border-amber-300 p-5">
              <p className="font-medium text-amber-800">This number is already in the queue</p>
              <div className="mt-3 text-sm">
                <p className="text-2xl font-bold text-brand-700">{duplicate.queue_number}</p>
                <p className="font-medium">{duplicate.customer.full_name} · {duplicate.party_size} guests</p>
                <p className="text-ink-muted">Arrived {formatTime(duplicate.arrived_at)}</p>
                <p className="mt-1"><QueueStatusBadge status={duplicate.status} /></p>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link to="/manager/waiting-list" className="inline-flex h-8 items-center rounded-lg border border-line px-3 text-sm font-medium hover:bg-brand-50">Keep existing</Link>
                {duplicate.status === 'WAITING' && (
                  <Button size="sm" variant="danger" onClick={() => setConfirmReplace(true)}>Cancel it and register again</Button>
                )}
              </div>
              {duplicate.status === 'ASSIGNED' && <p className="mt-3 text-xs text-ink-muted">This party already has a table. Release it from Allocation History first if needed.</p>}
            </Card>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmReplace}
        title="Replace registration?"
        danger
        confirmLabel="Cancel old & register new"
        loading={cancelExisting.isPending || register.isPending}
        message={<>The existing registration <b>{duplicate?.queue_number}</b> will be cancelled and the customer gets a new queue number at the end of the list. Their earlier priority is lost.</>}
        onClose={() => setConfirmReplace(false)}
        onConfirm={() => duplicate && cancelExisting.mutate(duplicate.id)}
      />
    </>
  )
}
