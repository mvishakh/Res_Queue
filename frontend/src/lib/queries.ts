import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import type {
  ActivityEntry, Allocation, Analytics, CustomerSummary, DiningTable, Menu, MessageRecord, MessageStatus,
  Overview, QueueList, QueueStatus, Restaurant, StaffMember, WhatsAppConfig,
} from './types'

// Realtime invalidates these keys; the interval is only a safety net if the socket drops.
const SAFETY_REFETCH = 60_000

export const useTables = () =>
  useQuery({ queryKey: ['tables'], queryFn: () => api<DiningTable[]>('/tables'), refetchInterval: SAFETY_REFETCH })

export const useQueue = (statuses: QueueStatus[], search = '') =>
  useQuery({
    queryKey: ['queue', statuses, search],
    queryFn: () => {
      const p = new URLSearchParams()
      statuses.forEach((s) => p.append('status', s))
      if (search.trim()) p.set('search', search.trim())
      return api<QueueList>(`/queue?${p}`)
    },
    refetchInterval: SAFETY_REFETCH,
  })

export const useAllocations = (limit = 100) =>
  useQuery({ queryKey: ['allocations', limit], queryFn: () => api<Allocation[]>(`/allocations?limit=${limit}`), refetchInterval: SAFETY_REFETCH })

export const useOverview = () =>
  useQuery({ queryKey: ['overview'], queryFn: () => api<Overview>('/dashboard/overview'), refetchInterval: SAFETY_REFETCH })

export const useNotifications = (status?: MessageStatus) =>
  useQuery({
    queryKey: ['notifications', status ?? 'all'],
    queryFn: () => api<MessageRecord[]>(`/notifications${status ? `?status=${status}` : ''}`),
  })

export const useCustomers = (search: string) =>
  useQuery({ queryKey: ['customers', search], queryFn: () => api<CustomerSummary[]>(`/customers?search=${encodeURIComponent(search)}`) })

export const useAnalytics = (days: number) =>
  useQuery({ queryKey: ['analytics', days], queryFn: () => api<Analytics>(`/analytics?days=${days}`) })

export const useMenu = () => useQuery({ queryKey: ['menu'], queryFn: () => api<Menu>('/menu') })

export const useRestaurant = () => useQuery({ queryKey: ['restaurant'], queryFn: () => api<Restaurant>('/settings/restaurant') })

export const useWhatsAppConfig = () => useQuery({ queryKey: ['whatsapp-config'], queryFn: () => api<WhatsAppConfig>('/settings/whatsapp') })

export const useStaff = () => useQuery({ queryKey: ['staff'], queryFn: () => api<StaffMember[]>('/staff') })

export const useActivity = () => useQuery({ queryKey: ['activity'], queryFn: () => api<ActivityEntry[]>('/activity?limit=50') })
