"""Transport-layer abuse protection and request throttling.

Layer: transport/security.
This module applies coarse request-rate protection before business handlers run.
It keeps abuse controls out of routes/services while still letting the app use
verified subject identity for user-scoped limits on expensive endpoints.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import ceil
import re
from threading import Lock
import time
from typing import Callable, Iterable, Literal, Pattern

from fastapi import Request
from starlette.responses import Response

from ..auth.subject_resolver import AuthSubjectResolver, ResolvedSubject, SubjectResolutionError

RateLimitKeyStrategy = Literal["ip", "subject_or_ip"]


@dataclass(frozen=True)
class RateLimitPolicy:
    """Static policy definition for one protected request class."""

    name: str
    request_limit: int
    window_seconds: int
    methods: frozenset[str]
    path_pattern: Pattern[str]
    key_strategy: RateLimitKeyStrategy

    def matches(self, *, method: str, path: str) -> bool:
        """Return True when this policy applies to the incoming request."""

        normalized_method = method.upper()
        return normalized_method in self.methods and bool(self.path_pattern.match(path))


@dataclass(frozen=True)
class RateLimitEvaluation:
    """Result of consuming one request against a single policy bucket."""

    policy: RateLimitPolicy
    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int
    retry_after_seconds: int | None

    @property
    def header_values(self) -> dict[str, str]:
        """Serialize response headers describing the active policy state."""

        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(self.reset_after_seconds),
            "X-RateLimit-Policy": self.policy.name,
        }
        if self.retry_after_seconds is not None:
            headers["Retry-After"] = str(self.retry_after_seconds)
        return headers


@dataclass(frozen=True)
class _StoreConsumption:
    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int
    retry_after_seconds: int | None


class RateLimitExceededError(Exception):
    """Raised when one policy denies the request."""

    def __init__(self, evaluation: RateLimitEvaluation) -> None:
        super().__init__(evaluation.policy.name)
        self.evaluation = evaluation

    @property
    def detail(self) -> str:
        retry_after_seconds = self.evaluation.retry_after_seconds or 1
        return (
            f"Rate limit exceeded for {self.evaluation.policy.name}. "
            f"Retry in {retry_after_seconds} seconds."
        )


class SlidingWindowRateLimitStore:
    """In-process sliding-window counter store.

    This is intentionally process-local for the current single-service MVP.
    The limiter contract is designed so a Redis-backed store can replace this
    later without changing route or middleware wiring.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._buckets: dict[str, deque[float]] = {}

    def consume(
        self,
        *,
        bucket_key: str,
        request_limit: int,
        window_seconds: int,
    ) -> _StoreConsumption:
        """Record one request and return the remaining budget for the bucket."""

        now = time.monotonic()
        window_start = now - window_seconds

        with self._lock:
            bucket = self._buckets.setdefault(bucket_key, deque())
            while bucket and bucket[0] <= window_start:
                bucket.popleft()

            if len(bucket) >= request_limit:
                retry_after_seconds = max(1, ceil(window_seconds - (now - bucket[0])))
                return _StoreConsumption(
                    allowed=False,
                    limit=request_limit,
                    remaining=0,
                    reset_after_seconds=retry_after_seconds,
                    retry_after_seconds=retry_after_seconds,
                )

            bucket.append(now)
            reset_after_seconds = max(1, ceil(window_seconds - (now - bucket[0])))
            return _StoreConsumption(
                allowed=True,
                limit=request_limit,
                remaining=max(0, request_limit - len(bucket)),
                reset_after_seconds=reset_after_seconds,
                retry_after_seconds=None,
            )

    def clear(self) -> None:
        """Reset all buckets. Used by tests and local demo resets."""

        with self._lock:
            self._buckets.clear()


class RequestRateLimiter:
    """Evaluate request policies and attach response metadata."""

    def __init__(
        self,
        *,
        policies: Iterable[RateLimitPolicy],
        subject_resolver_provider: Callable[[], AuthSubjectResolver] | None = None,
        store: SlidingWindowRateLimitStore | None = None,
    ) -> None:
        self._policies = tuple(policies)
        self._subject_resolver_provider = subject_resolver_provider
        self._store = store or SlidingWindowRateLimitStore()

    def evaluate(self, request: Request) -> list[RateLimitEvaluation]:
        """Consume all matching policy buckets for the request or raise 429."""

        matching_policies = [
            policy
            for policy in self._policies
            if policy.request_limit > 0
            and policy.window_seconds > 0
            and policy.matches(method=request.method, path=request.url.path)
        ]
        if not matching_policies:
            return []

        resolved_subject = self._resolve_subject_if_available(request)
        client_ip = resolve_client_ip(request)
        evaluations: list[RateLimitEvaluation] = []

        for policy in matching_policies:
            bucket_key = self._build_bucket_key(
                policy=policy,
                client_ip=client_ip,
                resolved_subject=resolved_subject,
            )
            consumption = self._store.consume(
                bucket_key=bucket_key,
                request_limit=policy.request_limit,
                window_seconds=policy.window_seconds,
            )
            evaluation = RateLimitEvaluation(
                policy=policy,
                allowed=consumption.allowed,
                limit=consumption.limit,
                remaining=consumption.remaining,
                reset_after_seconds=consumption.reset_after_seconds,
                retry_after_seconds=consumption.retry_after_seconds,
            )
            evaluations.append(evaluation)
            if not evaluation.allowed:
                raise RateLimitExceededError(evaluation)

        return evaluations

    def apply_headers(
        self,
        *,
        response: Response,
        evaluations: Iterable[RateLimitEvaluation],
    ) -> None:
        """Attach the closest-to-exhausted policy headers to the response."""

        selected = self._select_response_evaluation(evaluations)
        if not selected:
            return

        for key, value in selected.header_values.items():
            response.headers[key] = value

    def clear(self) -> None:
        """Reset limiter state."""

        self._store.clear()

    def _resolve_subject_if_available(self, request: Request) -> ResolvedSubject | None:
        cached_subject = getattr(request.state, "resolved_subject", None)
        if isinstance(cached_subject, ResolvedSubject):
            return cached_subject

        if self._subject_resolver_provider is None:
            return None

        authorization_header = request.headers.get("authorization")
        if not authorization_header:
            return None

        try:
            resolved_subject = self._subject_resolver_provider().resolve(
                authorization_header=authorization_header
            )
        except SubjectResolutionError:
            return None

        request.state.resolved_subject = resolved_subject
        return resolved_subject

    def _build_bucket_key(
        self,
        *,
        policy: RateLimitPolicy,
        client_ip: str,
        resolved_subject: ResolvedSubject | None,
    ) -> str:
        if policy.key_strategy == "ip":
            identifier = f"ip:{client_ip}"
        else:
            if resolved_subject:
                identifier = f"subject:{resolved_subject.subject_id}"
            else:
                identifier = f"ip:{client_ip}"

        return f"{policy.name}:{identifier}"

    def _select_response_evaluation(
        self, evaluations: Iterable[RateLimitEvaluation]
    ) -> RateLimitEvaluation | None:
        collected = list(evaluations)
        if not collected:
            return None

        return min(
            collected,
            key=lambda evaluation: (
                evaluation.remaining,
                evaluation.reset_after_seconds,
                evaluation.limit,
            ),
        )


def resolve_client_ip(request: Request) -> str:
    """Return the best available client IP from proxy-aware headers."""

    cf_connecting_ip = request.headers.get("cf-connecting-ip", "").strip()
    if cf_connecting_ip:
        return cf_connecting_ip

    x_forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if x_forwarded_for:
        forwarded_ip = x_forwarded_for.split(",")[0].strip()
        if forwarded_ip:
            return forwarded_ip

    x_real_ip = request.headers.get("x-real-ip", "").strip()
    if x_real_ip:
        return x_real_ip

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def build_default_rate_limit_policies(*, settings: object) -> tuple[RateLimitPolicy, ...]:
    """Build the default abuse-protection policies from environment settings."""

    api_pattern = re.compile(r"^/api/v1(?:/.*)?$")
    analysis_pattern = re.compile(r"^/api/v1/reports/analyze$|^/api/v1/agreements/[^/]+/analyses$")

    policies = (
        RateLimitPolicy(
            name="api_requests",
            request_limit=getattr(settings, "api_rate_limit_requests_per_window"),
            window_seconds=getattr(settings, "api_rate_limit_window_seconds"),
            methods=frozenset({"GET", "POST"}),
            path_pattern=api_pattern,
            key_strategy="ip",
        ),
        RateLimitPolicy(
            name="agreement_creation",
            request_limit=getattr(settings, "agreement_create_rate_limit_requests"),
            window_seconds=getattr(settings, "agreement_create_rate_limit_window_seconds"),
            methods=frozenset({"POST"}),
            path_pattern=re.compile(r"^/api/v1/agreements$"),
            key_strategy="subject_or_ip",
        ),
        RateLimitPolicy(
            name="analysis_generation_burst",
            request_limit=getattr(settings, "analysis_rate_limit_requests"),
            window_seconds=getattr(settings, "analysis_rate_limit_window_seconds"),
            methods=frozenset({"POST"}),
            path_pattern=analysis_pattern,
            key_strategy="subject_or_ip",
        ),
        RateLimitPolicy(
            name="analysis_generation_hourly",
            request_limit=getattr(settings, "analysis_hourly_rate_limit_requests"),
            window_seconds=getattr(settings, "analysis_hourly_rate_limit_window_seconds"),
            methods=frozenset({"POST"}),
            path_pattern=analysis_pattern,
            key_strategy="subject_or_ip",
        ),
    )

    return tuple(
        policy for policy in policies if policy.request_limit > 0 and policy.window_seconds > 0
    )
