from enum import StrEnum


class StaffRole(StrEnum):
    OWNER = "OWNER"  # Restaurant owner / administrator
    QUEUE_MANAGER = "QUEUE_MANAGER"  # Receptionist / waiting-list manager
    WAITER = "WAITER"  # Waiter / floor staff


class TableStatus(StrEnum):
    """Exactly two table statuses — this is a finalized business rule."""

    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"


class QueueStatus(StrEnum):
    WAITING = "WAITING"
    ASSIGNED = "ASSIGNED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class AllocationStatus(StrEnum):
    """Lifecycle of an allocation record (history), not a table status."""

    ACTIVE = "ACTIVE"  # party is seated at / heading to the table
    COMPLETED = "COMPLETED"  # party finished, waiter marked the table available
    RELEASED = "RELEASED"  # ended by a staff correction (no-show, undo, reassignment)


class AllocationType(StrEnum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class AllocationEndReason(StrEnum):
    TABLE_FREED = "TABLE_FREED"
    NO_SHOW = "NO_SHOW"
    REVERTED = "REVERTED"
    REASSIGNED = "REASSIGNED"


class DietaryType(StrEnum):
    VEG = "VEG"
    NON_VEG = "NON_VEG"


class MessageType(StrEnum):
    MENU = "MENU"
    TABLE_READY = "TABLE_READY"


class MessageStatus(StrEnum):
    PENDING = "PENDING"  # in the outbox, waiting to be sent / retried
    SENT = "SENT"  # accepted by Meta (has a wamid)
    DELIVERED = "DELIVERED"
    READ = "READ"
    FAILED = "FAILED"  # permanently failed — staff are alerted
    SKIPPED = "SKIPPED"  # intentionally not sent (no consent, WhatsApp disabled, superseded)
