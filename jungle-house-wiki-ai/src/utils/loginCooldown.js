// Small pure helpers for the login lock countdown (no React, no network), so they can be unit tested.

// mm:ss for the countdown. Never negative.
export function formatCooldown(seconds) {
  const safeSeconds = Math.max(0, Math.floor(Number(seconds) || 0));
  const minutes = Math.floor(safeSeconds / 60);
  const remainingSeconds = safeSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
}

function positiveSeconds(value) {
  const seconds = Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(seconds) && seconds > 0 ? seconds : null;
}

// How long the SERVER says the lock still lasts. The JSON body is preferred because a proxy can drop
// response headers; the Retry-After header is the second source. null when the server gave neither.
export function readRetryAfterSeconds(responseData, headers) {
  const fromBody = positiveSeconds(responseData?.retry_after_seconds);
  if (fromBody) return fromBody;
  const header = headers?.['retry-after'] ?? headers?.get?.('retry-after');
  return positiveSeconds(header);
}

function normaliseEmail(value) {
  return String(value || '').trim().toLowerCase();
}

// The server locks one account on this device, not the whole device. So the form is locked only while the
// email typed is the one that was locked; a colleague can still sign in to their own account here.
export function isLockedFor(lockedEmail, typedEmail, cooldownSeconds) {
  return Number(cooldownSeconds) > 0 && Boolean(lockedEmail) && normaliseEmail(lockedEmail) === normaliseEmail(typedEmail);
}
