import { useQuery } from '@tanstack/react-query'
import { MapPin } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { FullPageMessage, Spinner, cx } from '../components/ui'
import { api } from '../lib/api'
import { formatPrice } from '../lib/format'
import type { PublicMenu } from '../lib/types'
import { DietDot } from './manager/MenuPage'

/**
 * The public digital menu opened from the WhatsApp link. A simple, mobile-first menu —
 * no login, no ordering, no queue tracking, no customer data.
 */
export function PublicMenuPage() {
  const { slug = '' } = useParams()
  const { data, isLoading, error } = useQuery({
    queryKey: ['public-menu', slug],
    queryFn: () => api<PublicMenu>(`/public/menu/${encodeURIComponent(slug)}`, { auth: false }),
    retry: 1,
  })
  const [active, setActive] = useState(0)

  useEffect(() => {
    if (data) document.title = `${data.restaurant_name} — Menu`
  }, [data])

  if (isLoading) return <FullPageMessage><Spinner label="Loading menu…" /></FullPageMessage>
  if (error || !data) return <FullPageMessage title="Menu not available">Please ask the restaurant staff for a menu.</FullPageMessage>

  return (
    <div className="mx-auto min-h-full max-w-xl bg-white pb-12">
      <header className="px-5 pt-8 pb-4 text-center">
        {data.logo_url && <img src={data.logo_url} alt="" className="mx-auto mb-3 size-16 rounded-full object-cover" />}
        <h1 className="text-2xl font-bold tracking-tight">{data.restaurant_name}</h1>
        {data.address && <p className="mt-1 flex items-center justify-center gap-1 text-sm text-ink-muted"><MapPin className="size-3.5" aria-hidden />{data.address}</p>}
        {data.intro && <p className="mt-3 text-sm text-ink-muted">{data.intro}</p>}
      </header>

      {data.categories.length > 1 && (
        <nav className="sticky top-0 z-10 flex gap-2 overflow-x-auto border-y border-line bg-white/95 px-4 py-2.5 backdrop-blur">
          {data.categories.map((c, i) => (
            <a
              key={c.name}
              href={`#cat-${i}`}
              onClick={() => setActive(i)}
              className={cx('shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium', active === i ? 'bg-brand-700 text-white' : 'bg-brand-50 text-brand-800')}
            >
              {c.name}
            </a>
          ))}
        </nav>
      )}

      {data.categories.length === 0 && <p className="px-5 py-10 text-center text-ink-muted">The menu is being updated. Please check back soon.</p>}

      {data.categories.map((c, i) => (
        <section key={c.name} id={`cat-${i}`} className="scroll-mt-16 px-5 pt-6">
          <h2 className="text-lg font-semibold">{c.name}</h2>
          {c.description && <p className="text-sm text-ink-muted">{c.description}</p>}
          <ul className="mt-2 divide-y divide-line">
            {c.items.map((item) => (
              <li key={item.name} className="flex gap-4 py-4">
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 font-medium">
                    {item.dietary_type && <DietDot type={item.dietary_type} />}
                    {item.name}
                  </p>
                  <p className="mt-0.5 font-medium text-brand-800">{formatPrice(item.price, data.currency)}</p>
                  {item.description && <p className="mt-1 text-sm text-ink-muted">{item.description}</p>}
                </div>
                {item.image_url && <img src={item.image_url} alt={item.name} loading="lazy" className="size-24 shrink-0 rounded-xl object-cover" />}
              </li>
            ))}
          </ul>
        </section>
      ))}
      <p className="mt-10 text-center text-xs text-ink-muted">We'll message you on WhatsApp when your table is ready.</p>
    </div>
  )
}
