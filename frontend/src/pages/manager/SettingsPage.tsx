import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router'
import { useToast } from '../../components/Toast'
import { Badge, Button, Card, ConfirmDialog, cx, EmptyState, ErrorBanner, Field, Input, Modal, PageHeader, Select, Spinner, Textarea } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import { formatDateTime } from '../../lib/format'
import { useActivity, useRestaurant, useStaff, useTables, useWhatsAppConfig } from '../../lib/queries'
import { ROLE_LABELS } from '../../lib/roles'
import type { DiningTable, Restaurant, StaffRole, WhatsAppConfig } from '../../lib/types'

const TABS = [
  { key: 'restaurant', label: 'Restaurant' },
  { key: 'tables', label: 'Tables' },
  { key: 'staff', label: 'Staff & roles' },
  { key: 'whatsapp', label: 'WhatsApp' },
  { key: 'activity', label: 'Activity log' },
]

/** Owner / administrator settings (route is owner-only; the API enforces it too). */
export function SettingsPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'restaurant'
  return (
    <>
      <PageHeader title="Settings" description="Restaurant configuration for owners and administrators." />
      <div className="mb-6 flex flex-wrap gap-1 border-b border-line" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setParams({ tab: t.key })}
            className={cx('-mb-px border-b-2 px-3 py-2 text-sm font-medium', tab === t.key ? 'border-brand-700 text-brand-800' : 'border-transparent text-ink-muted hover:text-ink')}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'restaurant' && <RestaurantSettings />}
      {tab === 'tables' && <TableSettings />}
      {tab === 'staff' && <StaffSettings />}
      {tab === 'whatsapp' && <WhatsAppSettings />}
      {tab === 'activity' && <ActivityLog />}
    </>
  )
}

function RestaurantSettings() {
  const { data } = useRestaurant()
  return data ? <RestaurantForm key={data.id} initial={data} /> : <Spinner />
}

function RestaurantForm({ initial }: { initial: Restaurant }) {
  const [form, setForm] = useState<Restaurant>(initial)
  const [error, setError] = useState<string | null>(null)
  const qc = useQueryClient()
  const toast = useToast()
  const save = useMutation({
    mutationFn: (f: Restaurant) => {
      const { id: _id, ...body } = f
      return api<Restaurant>('/settings/restaurant', { method: 'PATCH', body })
    },
    onSuccess: () => { setError(null); toast('Restaurant settings saved'); qc.invalidateQueries() },
    onError: (e) => setError(errorMessage(e)),
  })
  const set = (k: keyof Restaurant, v: string | boolean | null) => setForm({ ...form, [k]: v })
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(form) }
  return (
    <Card className="max-w-2xl p-5">
      <form onSubmit={submit} className="space-y-4">
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <Field label="Restaurant name"><Input required value={form.name} onChange={(e) => set('name', e.target.value)} /></Field>
        <Field label="Menu link name" hint={`Public menu address ends with /menu/${form.slug}`}><Input required pattern="[a-z0-9]+(-[a-z0-9]+)*" value={form.slug} onChange={(e) => set('slug', e.target.value.toLowerCase())} /></Field>
        <Field label="Address"><Textarea rows={2} value={form.address ?? ''} onChange={(e) => set('address', e.target.value || null)} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Contact phone"><Input value={form.contact_phone ?? ''} onChange={(e) => set('contact_phone', e.target.value || null)} /></Field>
          <Field label="Logo image URL"><Input type="url" value={form.logo_url ?? ''} onChange={(e) => set('logo_url', e.target.value || null)} /></Field>
          <Field label="Time zone" hint="IANA name, e.g. Asia/Kolkata"><Input required value={form.timezone} onChange={(e) => set('timezone', e.target.value)} /></Field>
          <Field label="Default phone country" hint="2-letter code used for local numbers"><Input required maxLength={2} value={form.default_phone_region} onChange={(e) => set('default_phone_region', e.target.value.toUpperCase())} /></Field>
          <Field label="Currency" hint="3-letter code, e.g. INR"><Input required maxLength={3} value={form.currency} onChange={(e) => set('currency', e.target.value.toUpperCase())} /></Field>
        </div>
        <Field label="Menu welcome text (optional)"><Textarea rows={2} value={form.menu_intro ?? ''} onChange={(e) => set('menu_intro', e.target.value || null)} /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-brand-700" checked={form.menu_published} onChange={(e) => set('menu_published', e.target.checked)} /> Digital menu is published</label>
        <Button type="submit" loading={save.isPending}>Save changes</Button>
      </form>
    </Card>
  )
}

function TableSettings() {
  const { data: tables, isLoading } = useTables()
  const qc = useQueryClient()
  const toast = useToast()
  const [draft, setDraft] = useState<{ id?: string; table_number: string; capacity: number } | null>(null)
  const [removing, setRemoving] = useState<DiningTable | null>(null)
  const [error, setError] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: (d: NonNullable<typeof draft>) =>
      d.id ? api(`/tables/${d.id}`, { method: 'PATCH', body: { table_number: d.table_number, capacity: d.capacity } }) : api('/tables', { method: 'POST', body: d }),
    onSuccess: () => { setDraft(null); toast('Table saved'); qc.invalidateQueries({ queryKey: ['tables'] }) },
    onError: (e) => setError(errorMessage(e)),
  })
  const remove = useMutation({
    mutationFn: (t: DiningTable) => api(`/tables/${t.id}`, { method: 'DELETE' }),
    onSuccess: () => { setRemoving(null); toast('Table removed'); qc.invalidateQueries({ queryKey: ['tables'] }) },
    onError: (e) => { setRemoving(null); toast(errorMessage(e), 'error') },
  })
  return (
    <Card className="max-w-2xl">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <p className="text-sm text-ink-muted">Tables are AVAILABLE or OCCUPIED. New tables start available and are offered to the queue immediately.</p>
        <Button size="sm" onClick={() => { setError(null); setDraft({ table_number: '', capacity: 4 }) }}><Plus className="size-3.5" /> Add table</Button>
      </div>
      {isLoading ? <div className="p-4"><Spinner /></div> : !tables?.length ? <EmptyState title="No tables yet" /> : (
        <ul className="divide-y divide-line">
          {tables.map((t) => (
            <li key={t.id} className="flex items-center gap-3 px-4 py-3 text-sm">
              <span className="w-16 font-semibold">{t.table_number}</span>
              <span className="flex-1 text-ink-muted">Seats {t.capacity}</span>
              {t.status === 'AVAILABLE' ? <Badge tone="ok">Available</Badge> : <Badge>{t.current?.queue_number ?? 'In use'}</Badge>}
              <Button size="sm" variant="ghost" onClick={() => { setError(null); setDraft({ id: t.id, table_number: t.table_number, capacity: t.capacity }) }}>Edit</Button>
              <Button size="sm" variant="ghost" disabled={t.status !== 'AVAILABLE'} title={t.status !== 'AVAILABLE' ? 'Only available tables can be removed' : undefined} onClick={() => setRemoving(t)} aria-label={`Remove ${t.table_number}`}><Trash2 className="size-3.5" /></Button>
            </li>
          ))}
        </ul>
      )}
      <Modal open={!!draft} title={draft?.id ? 'Edit table' : 'Add table'} onClose={() => setDraft(null)}>
        {draft && (
          <form onSubmit={(e) => { e.preventDefault(); save.mutate(draft) }} className="space-y-4">
            {error && <ErrorBanner>{error}</ErrorBanner>}
            <Field label="Table number"><Input required maxLength={20} autoFocus value={draft.table_number} onChange={(e) => setDraft({ ...draft, table_number: e.target.value })} placeholder="T1" /></Field>
            <Field label="Seating capacity"><Input required type="number" min={1} max={50} value={draft.capacity} onChange={(e) => setDraft({ ...draft, capacity: Number(e.target.value) })} /></Field>
            <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setDraft(null)}>Cancel</Button><Button type="submit" loading={save.isPending}>Save</Button></div>
          </form>
        )}
      </Modal>
      <ConfirmDialog open={!!removing} title={`Remove ${removing?.table_number}?`} danger confirmLabel="Remove table" loading={remove.isPending}
        message="The table is removed from the floor plan. Its allocation history is kept." onClose={() => setRemoving(null)} onConfirm={() => removing && remove.mutate(removing)} />
    </Card>
  )
}

function StaffSettings() {
  const { data: staff, isLoading } = useStaff()
  const qc = useQueryClient()
  const toast = useToast()
  const [draft, setDraft] = useState<{ email: string; full_name: string; role: StaffRole; temporary_password: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const add = useMutation({
    mutationFn: (d: NonNullable<typeof draft>) => api('/staff', { method: 'POST', body: d }),
    onSuccess: () => { setDraft(null); toast('Staff member added. Share the temporary password with them securely.'); qc.invalidateQueries({ queryKey: ['staff'] }) },
    onError: (e) => setError(errorMessage(e)),
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { role?: StaffRole; is_active?: boolean } }) => api(`/staff/${id}`, { method: 'PATCH', body }),
    onSuccess: () => { toast('Staff updated'); qc.invalidateQueries({ queryKey: ['staff'] }) },
    onError: (e) => toast(errorMessage(e), 'error'),
  })
  return (
    <Card className="max-w-3xl">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <p className="text-sm text-ink-muted">Owners and Queue Managers use the Queue Manager Dashboard; Waiters use the Waiter Dashboard.</p>
        <Button size="sm" onClick={() => { setError(null); setDraft({ email: '', full_name: '', role: 'WAITER', temporary_password: '' }) }}><Plus className="size-3.5" /> Add staff</Button>
      </div>
      {isLoading ? <div className="p-4"><Spinner /></div> : (
        <ul className="divide-y divide-line">
          {staff?.map((s) => (
            <li key={s.membership_id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{s.full_name} {!s.is_active && <Badge tone="bad">Deactivated</Badge>}</p>
                <p className="text-ink-muted">{s.email}</p>
              </div>
              <Select className="w-auto" value={s.role} onChange={(e) => update.mutate({ id: s.membership_id, body: { role: e.target.value as StaffRole } })} aria-label={`Role for ${s.full_name}`}>
                {(Object.keys(ROLE_LABELS) as StaffRole[]).map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
              </Select>
              <Button size="sm" variant={s.is_active ? 'danger' : 'secondary'} onClick={() => update.mutate({ id: s.membership_id, body: { is_active: !s.is_active } })}>
                {s.is_active ? 'Deactivate' : 'Reactivate'}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <Modal open={!!draft} title="Add staff member" onClose={() => setDraft(null)}>
        {draft && (
          <form onSubmit={(e) => { e.preventDefault(); add.mutate(draft) }} className="space-y-4">
            {error && <ErrorBanner>{error}</ErrorBanner>}
            <Field label="Full name"><Input required value={draft.full_name} onChange={(e) => setDraft({ ...draft, full_name: e.target.value })} /></Field>
            <Field label="Email"><Input required type="email" value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })} /></Field>
            <Field label="Role">
              <Select value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value as StaffRole })}>
                {(Object.keys(ROLE_LABELS) as StaffRole[]).map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
              </Select>
            </Field>
            <Field label="Temporary password" hint="At least 8 characters. Existing Supabase users keep their own password.">
              <Input required minLength={8} type="text" autoComplete="new-password" value={draft.temporary_password} onChange={(e) => setDraft({ ...draft, temporary_password: e.target.value })} />
            </Field>
            <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setDraft(null)}>Cancel</Button><Button type="submit" loading={add.isPending}>Add staff</Button></div>
          </form>
        )}
      </Modal>
    </Card>
  )
}

function WhatsAppSettings() {
  const { data } = useWhatsAppConfig()
  return data ? <WhatsAppForm initial={data} /> : <Spinner />
}

function WhatsAppForm({ initial }: { initial: WhatsAppConfig }) {
  const [form, setForm] = useState<WhatsAppConfig>(initial)
  const [error, setError] = useState<string | null>(null)
  const qc = useQueryClient()
  const toast = useToast()
  const save = useMutation({
    mutationFn: (f: WhatsAppConfig) =>
      api<WhatsAppConfig>('/settings/whatsapp', {
        method: 'PUT',
        body: { is_enabled: f.is_enabled, phone_number_id: f.phone_number_id || null, menu_template_name: f.menu_template_name, table_ready_template_name: f.table_ready_template_name, template_language: f.template_language },
      }),
    onSuccess: () => { setError(null); toast('WhatsApp settings saved'); qc.invalidateQueries({ queryKey: ['whatsapp-config'] }) },
    onError: (e) => setError(errorMessage(e)),
  })
  return (
    <Card className="max-w-2xl p-5">
      <form onSubmit={(e) => { e.preventDefault(); save.mutate(form) }} className="space-y-4">
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <div className="flex flex-wrap gap-2 text-sm">
          <Badge tone={form.server_credentials_configured ? 'ok' : 'bad'}>{form.server_credentials_configured ? 'API credentials configured' : 'API credentials missing on server'}</Badge>
          <Badge tone={form.webhook_configured ? 'ok' : 'warn'}>{form.webhook_configured ? 'Webhook configured' : 'Webhook not configured (no delivery tracking)'}</Badge>
        </div>
        <p className="text-sm text-ink-muted">
          Messages use the official Meta WhatsApp Cloud API with approved templates. The access token is a server secret set by the administrator — it is never stored here.
        </p>
        <label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" className="accent-brand-700" checked={form.is_enabled} onChange={(e) => setForm({ ...form, is_enabled: e.target.checked })} /> Send WhatsApp messages for this restaurant</label>
        <Field label="Phone number ID (optional)" hint="Leave empty to use the server default WHATSAPP_PHONE_NUMBER_ID"><Input value={form.phone_number_id ?? ''} onChange={(e) => setForm({ ...form, phone_number_id: e.target.value })} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Menu template name"><Input required value={form.menu_template_name} onChange={(e) => setForm({ ...form, menu_template_name: e.target.value })} /></Field>
          <Field label="Table-ready template name"><Input required value={form.table_ready_template_name} onChange={(e) => setForm({ ...form, table_ready_template_name: e.target.value })} /></Field>
          <Field label="Template language code" hint="e.g. en, en_US"><Input required value={form.template_language} onChange={(e) => setForm({ ...form, template_language: e.target.value })} /></Field>
        </div>
        <Button type="submit" loading={save.isPending}>Save WhatsApp settings</Button>
      </form>
    </Card>
  )
}

function ActivityLog() {
  const { data, isLoading } = useActivity()
  return (
    <Card className="overflow-hidden">
      {isLoading ? <div className="p-4"><Spinner /></div> : !data?.length ? <EmptyState title="No activity yet" /> : (
        <ul className="divide-y divide-line text-sm">
          {data.map((a) => (
            <li key={a.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2.5">
              <span className="w-32 shrink-0 tabular-nums text-ink-muted">{formatDateTime(a.created_at)}</span>
              <span className="font-medium">{a.action.replaceAll('_', ' ').toLowerCase()}</span>
              <span className="text-ink-muted">{a.actor_name ?? 'System'}</span>
              <span className="min-w-0 flex-1 truncate text-xs text-ink-muted">
                {Object.entries(a.details).filter(([, v]) => v != null && v !== '').map(([k, v]) => `${k.replaceAll('_', ' ')}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`).join(' · ')}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
