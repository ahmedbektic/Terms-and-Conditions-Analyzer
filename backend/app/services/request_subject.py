"""Shared owner-subject value object for authenticated service calls.

Services use this small immutable type instead of dealing with transport-layer
auth details directly. It keeps owner scoping explicit without coupling domain
logic to FastAPI or JWT parsing concerns.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RequestSubject:
    """Identity tuple used for owner-scoped data access."""

    subject_type: str
    subject_id: str
