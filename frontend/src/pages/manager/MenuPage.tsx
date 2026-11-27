import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Copy, ExternalLink, ImagePlus, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useToast } from '../../components/Toast'
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorBanner, Field, Input, Modal, PageHeader, Select, Spinner, Textarea } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import { formatPrice } from '../../lib/format'
import { useMenu, useRestaurant } from '../../lib/queries'
import type { DietaryType, MenuCategory, MenuItem } from '../../lib/types'

type ItemDraft = { id?: string; category_id: string; name: string; description: string; price: string; dietary_type: DietaryType | ''; is_available: boolean }

export function MenuPage() {
  const { data: menu, isLoading, error } = useMenu()
  const { data: restaurant } = useRestaurant()
  const qc = useQueryClient()
  const toast = useToast()
  const [catDraft, setCatDraft] = useState<{ id?: string; name: string; description: string } | null>(null)
  const [itemDraft, setItemDraft] = useState<ItemDraft | null>(null)
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [deleting, setDeleting] = useState<{ kind: 'category' | 'item'; id: string; name: string } | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const refresh = () => qc.invalidateQueries({ queryKey: ['menu'] })

  const saveCategory = useMutation({
    mutationFn: (d: NonNullable<typeof catDraft>) =>
      d.id
        ? api(`/menu/categories/${d.id}`, { method: 'PATCH', body: { name: d.name, description: d.description || null } })
        : api('/menu/categories', { method: 'POST', body: { name: d.name, description: d.description || null, sort_order: menu?.categories.length ?? 0 } }),
    onSuccess: () => { setCatDraft(null); refresh(); toast('Category saved') },
    onError: (e) => setFormError(errorMessage(e)),
  })

  const saveItem = useMutation({
    mutationFn: async (d: ItemDraft) => {
      const body = { category_id: d.category_id, name: d.name, description: d.description || null, price: d.price, dietary_type: d.dietary_type || null, is_available: d.is_available }
      const item = d.id
        ? await api<MenuItem>(`/menu/items/${d.id}`, { method: 'PATCH', body })
        : await api<MenuItem>('/menu/items', { method: 'POST', body })
      if (imageFile) {
        const form = new FormData()
        form.append('file', imageFile)
        await api(`/menu/items/${item.id}/image`, { method: 'POST', form })
      }
    },
    onSuccess: () => { setItemDraft(null); setImageFile(null); refresh(); toast('Menu item saved') },
    onError: (e) => { setFormError(errorMessage(e)); refresh() },
  })

  const toggleAvailable = useMutation({
    mutationFn: (i: MenuItem) => api(`/menu/items/${i.id}`, { method: 'PATCH', body: { is_available: !i.is_available } }),
    onSuccess: refresh,
    onError: (e) => toast(errorMessage(e), 'error'),
  })

  const remove = useMutation({
    mutationFn: (d: NonNullable<typeof deleting>) => api(`/menu/${d.kind === 'category' ? 'categories' : 'items'}/${d.id}`, { method: 'DELETE' }),
    onSuccess: () => { setDeleting(null); refresh(); toast('Deleted') },
    onError: (e) => { setDeleting(null); toast(errorMessage(e), 'error') },
  })

  const openItem = (category: MenuCategory, item?: MenuItem) => {
    setFormError(null)
    setImageFile(null)
    setItemDraft(
      item
        ? { id: item.id, category_id: item.category_id, name: item.name, description: item.description ?? '', price: item.price, dietary_type: item.dietary_type ?? '', is_available: item.is_available }
        : { category_id: category.id, name: '', description: '', price: '', dietary_type: '', is_available: true },
    )
  }

  const submitItem = (e: FormEvent) => { e.preventDefault(); if (itemDraft) saveItem.mutate(itemDraft) }
  const submitCat = (e: FormEvent) => { e.preventDefault(); if (catDraft) saveCategory.mutate(catDraft) }
  const currency = restaurant?.currency ?? 'INR'

  return (
    <>
      <PageHeader
        title="Menu Management"
        description="The digital menu customers receive on WhatsApp. No ordering — it's a menu to browse while waiting."
        actions={<Button onClick={() => { setFormError(null); setCatDraft({ name: '', description: '' }) }}><Plus className="size-4" /> Add category</Button>}
      />
      {error && <ErrorBanner>{errorMessage(error)}</ErrorBanner>}
      {menu && (
        <Card className="mb-6 flex flex-wrap items-center gap-3 p-4 text-sm">
          <span className="font-medium">Public menu link</span>
          <code className="min-w-0 flex-1 truncate rounded bg-canvas px-2 py-1">{menu.menu_url}</code>
          {!menu.menu_published && <Badge tone="warn">Unpublished — enable in Settings</Badge>}
          <Button size="sm" variant="secondary" onClick={() => navigator.clipboard?.writeText(menu.menu_url).then(() => toast('Link copied'))}><Copy className="size-3.5" /> Copy</Button>
          <a href={menu.menu_url} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line px-3 font-medium hover:bg-brand-50"><ExternalLink className="size-3.5" /> Preview</a>
        </Card>
      )}
      {isLoading && <Spinner />}
      {menu && menu.categories.length === 0 && <Card><EmptyState title="Your menu is empty">Add a category such as “Starters”, then add dishes to it.</EmptyState></Card>}
      <div className="space-y-6">
        {menu?.categories.map((c) => (
          <Card key={c.id}>
            <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
              <h2 className="font-semibold">{c.name}</h2>
              {!c.is_active && <Badge>Hidden</Badge>}
              <span className="text-sm text-ink-muted">{c.items.length} items</span>
              <div className="ml-auto flex gap-1">
                <Button size="sm" variant="ghost" onClick={() => { setFormError(null); setCatDraft({ id: c.id, name: c.name, description: c.description ?? '' }) }} aria-label={`Rename ${c.name}`}><Pencil className="size-3.5" /></Button>
                <Button size="sm" variant="ghost" onClick={() => setDeleting({ kind: 'category', id: c.id, name: c.name })} aria-label={`Delete ${c.name}`}><Trash2 className="size-3.5" /></Button>
                <Button size="sm" variant="secondary" onClick={() => openItem(c)}><Plus className="size-3.5" /> Add item</Button>
              </div>
            </div>
            {c.items.length === 0 ? <EmptyState title="No items in this category" /> : (
              <ul className="divide-y divide-line">
                {c.items.map((i) => (
                  <li key={i.id} className="flex items-center gap-3 px-4 py-3">
                    {i.image_url ? <img src={i.image_url} alt="" className="size-14 shrink-0 rounded-lg object-cover" /> : <div className="grid size-14 shrink-0 place-items-center rounded-lg bg-canvas text-ink-muted"><ImagePlus className="size-5" /></div>}
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-2 font-medium">
                        {i.dietary_type && <DietDot type={i.dietary_type} />}
                        <span className="truncate">{i.name}</span>
                      </p>
                      {i.description && <p className="truncate text-sm text-ink-muted">{i.description}</p>}
                    </div>
                    <span className="font-medium tabular-nums">{formatPrice(i.price, currency)}</span>
                    <label className="flex items-center gap-1.5 text-xs text-ink-muted">
                      <input type="checkbox" className="accent-brand-700" checked={i.is_available} onChange={() => toggleAvailable.mutate(i)} /> Available
                    </label>
                    <Button size="sm" variant="ghost" onClick={() => openItem(c, i)} aria-label={`Edit ${i.name}`}><Pencil className="size-3.5" /></Button>
                    <Button size="sm" variant="ghost" onClick={() => setDeleting({ kind: 'item', id: i.id, name: i.name })} aria-label={`Delete ${i.name}`}><Trash2 className="size-3.5" /></Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        ))}
      </div>

      <Modal open={!!catDraft} title={catDraft?.id ? 'Edit category' : 'New category'} onClose={() => setCatDraft(null)}>
        {catDraft && (
          <form onSubmit={submitCat} className="space-y-4">
            {formError && <ErrorBanner>{formError}</ErrorBanner>}
            <Field label="Name"><Input required maxLength={80} autoFocus value={catDraft.name} onChange={(e) => setCatDraft({ ...catDraft, name: e.target.value })} /></Field>
            <Field label="Description (optional)"><Input maxLength={500} value={catDraft.description} onChange={(e) => setCatDraft({ ...catDraft, description: e.target.value })} /></Field>
            <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setCatDraft(null)}>Cancel</Button><Button type="submit" loading={saveCategory.isPending}>Save</Button></div>
          </form>
        )}
      </Modal>

      <Modal open={!!itemDraft} title={itemDraft?.id ? 'Edit item' : 'New item'} onClose={() => setItemDraft(null)}>
        {itemDraft && menu && (
          <form onSubmit={submitItem} className="space-y-4">
            {formError && <ErrorBanner>{formError}</ErrorBanner>}
            <Field label="Name"><Input required maxLength={120} autoFocus value={itemDraft.name} onChange={(e) => setItemDraft({ ...itemDraft, name: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label={`Price (${currency})`}><Input required type="number" min="0" step="0.01" inputMode="decimal" value={itemDraft.price} onChange={(e) => setItemDraft({ ...itemDraft, price: e.target.value })} /></Field>
              <Field label="Category">
                <Select value={itemDraft.category_id} onChange={(e) => setItemDraft({ ...itemDraft, category_id: e.target.value })}>
                  {menu.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </Select>
              </Field>
            </div>
            <Field label="Description (optional)"><Textarea rows={2} maxLength={1000} value={itemDraft.description} onChange={(e) => setItemDraft({ ...itemDraft, description: e.target.value })} /></Field>
            <Field label="Vegetarian / non-vegetarian">
              <Select value={itemDraft.dietary_type} onChange={(e) => setItemDraft({ ...itemDraft, dietary_type: e.target.value as DietaryType | '' })}>
                <option value="">Not shown</option>
                <option value="VEG">Vegetarian</option>
                <option value="NON_VEG">Non-vegetarian</option>
              </Select>
            </Field>
            <Field label="Photo (optional)" hint="JPEG, PNG or WebP, up to 5 MB">
              <Input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setImageFile(e.target.files?.[0] ?? null)} />
            </Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-brand-700" checked={itemDraft.is_available} onChange={(e) => setItemDraft({ ...itemDraft, is_available: e.target.checked })} /> Available today</label>
            <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setItemDraft(null)}>Cancel</Button><Button type="submit" loading={saveItem.isPending}>Save item</Button></div>
          </form>
        )}
      </Modal>

      <ConfirmDialog
        open={!!deleting}
        title={`Delete ${deleting?.name}?`}
        danger
        confirmLabel="Delete"
        loading={remove.isPending}
        message={deleting?.kind === 'category' ? 'Only empty categories can be deleted.' : 'This item will be removed from the digital menu.'}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting)}
      />
    </>
  )
}

export function DietDot({ type }: { type: DietaryType }) {
  const veg = type === 'VEG'
  return (
    <span
      title={veg ? 'Vegetarian' : 'Non-vegetarian'}
      aria-label={veg ? 'Vegetarian' : 'Non-vegetarian'}
      className={`inline-grid size-3.5 shrink-0 place-items-center rounded-[3px] border-[1.5px] ${veg ? 'border-green-700' : 'border-red-700'}`}
    >
      <span className={`size-1.5 rounded-full ${veg ? 'bg-green-700' : 'bg-red-700'}`} />
    </span>
  )
}
