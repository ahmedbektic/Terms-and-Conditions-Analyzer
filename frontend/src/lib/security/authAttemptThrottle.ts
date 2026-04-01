/* Architecture note:
 * Shared client-side auth throttling for web and extension password flows.
 * This only protects the shipped clients; backend rate limiting remains the
 * authoritative server-side control for API abuse.
 */

export interface AuthAttemptThrottlePolicy {
  actionKey: string;
  actionLabel: string;
  maxAttempts: number;
  windowMs: number;
  lockoutMs: number;
}

export interface AuthAttemptThrottleStore {
  read: (key: string) => Promise<AuthAttemptThrottleState | null>;
  write: (key: string, state: AuthAttemptThrottleState) => Promise<void>;
  remove: (key: string) => Promise<void>;
}

export interface AuthAttemptThrottleState {
  attemptTimestamps: number[];
  blockedUntil: number | null;
}

export const PASSWORD_SIGN_IN_ATTEMPT_POLICY: AuthAttemptThrottlePolicy = {
  actionKey: 'password_sign_in',
  actionLabel: 'sign-in',
  maxAttempts: 5,
  windowMs: 10 * 60 * 1000,
  lockoutMs: 15 * 60 * 1000,
};

export const PASSWORD_SIGN_UP_ATTEMPT_POLICY: AuthAttemptThrottlePolicy = {
  actionKey: 'password_sign_up',
  actionLabel: 'account creation',
  maxAttempts: 3,
  windowMs: 30 * 60 * 1000,
  lockoutMs: 30 * 60 * 1000,
};

export class AuthAttemptThrottle {
  private readonly policy: AuthAttemptThrottlePolicy;
  private readonly store: AuthAttemptThrottleStore;
  private readonly now: () => number;
  private readonly keyPrefix: string;

  constructor(options: {
    policy: AuthAttemptThrottlePolicy;
    store: AuthAttemptThrottleStore;
    keyPrefix?: string;
    now?: () => number;
  }) {
    this.policy = options.policy;
    this.store = options.store;
    this.now = options.now ?? (() => Date.now());
    this.keyPrefix = options.keyPrefix ?? 'auth_attempt_throttle';
  }

  async registerAttempt(identifier: string): Promise<void> {
    const normalizedIdentifier = normalizeAuthAttemptIdentifier(identifier);
    const key = this.buildKey(normalizedIdentifier);
    const state = sanitizeState(await this.store.read(key), this.now(), this.policy.windowMs);

    if (state.blockedUntil && state.blockedUntil > this.now()) {
      throw new Error(buildBlockedMessage(this.policy.actionLabel, state.blockedUntil - this.now()));
    }

    if (state.attemptTimestamps.length >= this.policy.maxAttempts) {
      const blockedUntil = this.now() + this.policy.lockoutMs;
      await this.store.write(key, {
        attemptTimestamps: state.attemptTimestamps,
        blockedUntil,
      });
      throw new Error(buildBlockedMessage(this.policy.actionLabel, this.policy.lockoutMs));
    }

    state.attemptTimestamps.push(this.now());
    await this.store.write(key, state);
  }

  async clear(identifier: string): Promise<void> {
    const normalizedIdentifier = normalizeAuthAttemptIdentifier(identifier);
    await this.store.remove(this.buildKey(normalizedIdentifier));
  }

  private buildKey(identifier: string): string {
    return `${this.keyPrefix}:${this.policy.actionKey}:${identifier}`;
  }
}

export function createBrowserLocalStorageThrottleStore(): AuthAttemptThrottleStore {
  return {
    async read(key) {
      const storage = getLocalStorage();
      if (!storage) {
        return null;
      }

      const rawValue = storage.getItem(key);
      if (!rawValue) {
        return null;
      }

      try {
        const parsed = JSON.parse(rawValue) as AuthAttemptThrottleState;
        return isThrottleState(parsed) ? parsed : null;
      } catch {
        return null;
      }
    },
    async write(key, state) {
      const storage = getLocalStorage();
      if (!storage) {
        return;
      }

      storage.setItem(key, JSON.stringify(state));
    },
    async remove(key) {
      const storage = getLocalStorage();
      if (!storage) {
        return;
      }

      storage.removeItem(key);
    },
  };
}

export function normalizeAuthAttemptIdentifier(value: string): string {
  return value.trim().toLowerCase();
}

function sanitizeState(
  state: AuthAttemptThrottleState | null,
  now: number,
  windowMs: number,
): AuthAttemptThrottleState {
  const attemptTimestamps = (state?.attemptTimestamps ?? []).filter(
    (timestamp) => Number.isFinite(timestamp) && now - timestamp < windowMs,
  );
  const blockedUntil =
    state?.blockedUntil && Number.isFinite(state.blockedUntil) && state.blockedUntil > now
      ? state.blockedUntil
      : null;

  return {
    attemptTimestamps,
    blockedUntil,
  };
}

function buildBlockedMessage(actionLabel: string, durationMs: number): string {
  return `Too many ${actionLabel} attempts. Retry in ${formatDuration(durationMs)}.`;
}

function formatDuration(durationMs: number): string {
  const totalSeconds = Math.max(1, Math.ceil(durationMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes > 0 && seconds > 0) {
    return `${minutes}m ${seconds}s`;
  }
  if (minutes > 0) {
    return `${minutes}m`;
  }
  return `${seconds}s`;
}

function getLocalStorage(): Storage | null {
  try {
    if (typeof window === 'undefined') {
      return null;
    }
    return window.localStorage;
  } catch {
    return null;
  }
}

function isThrottleState(value: unknown): value is AuthAttemptThrottleState {
  if (!value || typeof value !== 'object') {
    return false;
  }

  const candidate = value as AuthAttemptThrottleState;
  return Array.isArray(candidate.attemptTimestamps);
}
