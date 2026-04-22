"""Repository-layer exceptions shared by persistence implementations."""


class ActiveTrackedPolicyConflictError(Exception):
    """Raised when an active tracked policy already exists for the owner/url key."""


class ActiveTrackedPolicyCheckExecutionConflictError(Exception):
    """Raised when an active tracked-policy check execution already exists."""
