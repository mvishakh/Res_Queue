// Mirrors the FastAPI response schemas (backend/app/schemas).

export type StaffRole = 'OWNER' | 'QUEUE_MANAGER' | 'WAITER'
export type Dashboard = 'queue-manager' | 'waiter'
export type TableStatus = 'AVAILABLE' | 'OCCUPIED'
export type QueueStatus = 'WAITING' | 'ASSIGNED' | 'COMPLETED' | 'CANCELLED'
export type AllocationStatus = 'ACTIVE' | 'COMPLETED' | 'RELEASED'
export type AllocationType = 'AUTOMATIC' | 'MANUAL_OVERRIDE'
export type MessageStatus = 'PENDING' | 'SENT' | 'DELIVERED' | 'READ' | 'FAILED' | 'SKIPPED'
export type MessageType = 'MENU' | 'TABLE_READY'
export type DietaryType = 'VEG' | 'NON_VEG'

export interface Membership {
  restaurant_id: string
  restaurant_name: string
  restaurant_slug: string
  role: StaffRole
  dashboard: Dashboard
}

export interface Me {
  id: string
  email: string
  full_name: string
  memberships: Membership[]
}

export interface Customer {
  id: string
  full_name: string
  phone_e164: string
  whatsapp_consent: boolean
  whatsapp_consent_at: string | null
}

export interface MessageSummary {
  id: string
  message_type: MessageType
  status: MessageStatus
  last_error: string | null
}

export interface QueueEntry {
  id: string
  queue_number: string
  business_date: string
  party_size: number
  notes: string | null
  status: QueueStatus
  arrived_at: string
  assigned_at: string | null
  completed_at: string | null
  cancelled_at: string | null
  cancellation_reason: string | null
  customer: Customer
  allocation: { allocation_id: string; table_id: string; table_number: string; allocated_at: string } | null
  messages: MessageSummary[]
}

export interface QueueList {
  server_time: string
  items: QueueEntry[]
}

export interface CurrentParty {
  allocation_id: string
  queue_entry_id: string
  queue_number: string
  customer_name: string
  party_size: number
  allocated_at: string
  allocation_type: AllocationType
}

export interface DiningTable {
  id: string
  table_number: string
  capacity: number
  status: TableStatus
  current: CurrentParty | null
  updated_at: string
  can_undo_available: boolean
}

export interface MarkAvailableResult {
  table: DiningTable
  freed_queue_number: string | null
  new_allocation: CurrentParty | null
  message: string
}

export interface Allocation {
  id: string
  table_id: string
  table_number: string
  table_capacity: number
  queue_entry_id: string
  queue_number: string
  customer_name: string
  party_size: number
  status: AllocationStatus
  allocation_type: AllocationType
  allocated_at: string
  ended_at: string | null
  end_reason: 'TABLE_FREED' | 'NO_SHOW' | 'REVERTED' | 'REASSIGNED' | null
  notification_status: MessageStatus | null
}

export interface MessageRecord {
  id: string
  message_type: MessageType
  status: MessageStatus
  to_phone: string
  customer_name: string
  queue_number: string | null
  attempt_count: number
  last_error: string | null
  created_at: string
  sent_at: string | null
  delivered_at: string | null
  read_at: string | null
  failed_at: string | null
}

export interface Overview {
  total_tables: number
  available_tables: number
  occupied_tables: number
  waiting_customers: number
  allocated_today: number
  registered_today: number
  failed_notifications: number
  recent_registrations: {
    id: string
    queue_number: string
    customer_name: string
    party_size: number
    status: QueueStatus
    arrived_at: string
  }[]
  recent_allocations: Allocation[]
  recent_messages: MessageRecord[]
}

export interface Analytics {
  days: number
  registered: number
  served: number
  cancelled: number
  no_shows: number
  avg_wait_minutes: number | null
  median_party_size: number | null
  daily: { date: string; registered: number; served: number; cancelled: number; avg_wait_minutes: number | null }[]
  by_hour: { hour: number; registrations: number }[]
  table_usage: { table_number: string; capacity: number; allocations: number }[]
}

export interface CustomerSummary extends Customer {
  visits: number
  completed_visits: number
  last_visit_at: string | null
}

export interface MenuItem {
  id: string
  category_id: string
  name: string
  description: string | null
  price: string
  image_url: string | null
  dietary_type: DietaryType | null
  is_available: boolean
  sort_order: number
}

export interface MenuCategory {
  id: string
  name: string
  description: string | null
  sort_order: number
  is_active: boolean
  items: MenuItem[]
}

export interface Menu {
  menu_url: string
  menu_published: boolean
  categories: MenuCategory[]
}

export interface PublicMenu {
  restaurant_name: string
  logo_url: string | null
  address: string | null
  currency: string
  intro: string | null
  categories: {
    name: string
    description: string | null
    items: { name: string; description: string | null; price: string; image_url: string | null; dietary_type: DietaryType | null }[]
  }[]
}

export interface Restaurant {
  id: string
  name: string
  slug: string
  address: string | null
  contact_phone: string | null
  timezone: string
  default_phone_region: string
  currency: string
  logo_url: string | null
  menu_published: boolean
  menu_intro: string | null
}

export interface WhatsAppConfig {
  is_enabled: boolean
  phone_number_id: string | null
  menu_template_name: string
  table_ready_template_name: string
  template_language: string
  server_credentials_configured: boolean
  webhook_configured: boolean
}

export interface StaffMember {
  membership_id: string
  staff_id: string
  email: string
  full_name: string
  role: StaffRole
  is_active: boolean
}

export interface ActivityEntry {
  id: string
  action: string
  entity_type: string
  entity_id: string | null
  actor_name: string | null
  details: Record<string, unknown>
  created_at: string
}
