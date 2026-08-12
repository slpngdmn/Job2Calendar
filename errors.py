"""Exception types shared across the Job2Calendar modules."""


class Job2CalendarError(Exception):
    """Base class for all Job2Calendar failures."""


class ApiError(Job2CalendarError):
    """Raised when the Teletalk API cannot be queried successfully."""


class StorageError(Job2CalendarError):
    """Raised when local JSON state cannot be read or written."""


class CalendarError(Job2CalendarError):
    """Raised when the ICS feed cannot be read or written."""


class NotificationError(Job2CalendarError):
    """Raised when a notification could not be delivered."""
