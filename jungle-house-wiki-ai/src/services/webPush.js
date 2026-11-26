// Turn AI-ready phone / browser notifications on or off (2026-11-26, step 2).
// The service worker (public/sw.js) only shows notifications; it never caches
// pages. The words shown come from translations.js and are stored with the
// subscription, so the notification is in the language the staff member uses.
import api from './api';
import { keyBytes, pushSupport } from './webPushSupport';

const PROMPT_DONE_KEY = 'jh_push_prompt_done';

export function currentSupport() {
  if (typeof window === 'undefined') return 'unsupported';
  return pushSupport({ navigator: window.navigator, window });
}

async function existingSubscription() {
  const registration = await navigator.serviceWorker.getRegistration('/');
  return registration ? registration.pushManager.getSubscription() : null;
}

// 'unsupported' | 'ios-install' | 'denied' | 'off' | 'on'
export async function pushState() {
  const support = currentSupport();
  if (support !== 'supported') return support;
  if (Notification.permission === 'denied') return 'denied';
  try {
    const subscription = await existingSubscription();
    return subscription && Notification.permission === 'granted' ? 'on' : 'off';
  } catch {
    return 'off';
  }
}

export function pushLabels(t) {
  return { chat: t('aiTask.doneChat'), quiz: t('aiTask.doneQuiz'), view: t('aiTask.view') };
}

// Must be called straight from a tap: iPhones only show the permission
// question for a direct user action, so nothing is awaited before it.
export async function enablePush(labels) {
  const support = currentSupport();
  if (support !== 'supported') return support;
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') return permission === 'denied' ? 'denied' : 'off';
  const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
  await navigator.serviceWorker.ready;
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    const { data } = await api.get('/push/public-key');
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: keyBytes(data.publicKey),
    });
  }
  await api.post('/push/subscribe', { subscription: subscription.toJSON(), labels });
  markPromptDone();
  return 'on';
}

export async function disablePush() {
  if (currentSupport() !== 'supported') return currentSupport();
  const subscription = await existingSubscription();
  if (subscription) {
    await api.post('/push/unsubscribe', { endpoint: subscription.endpoint }).catch(() => {});
    await subscription.unsubscribe().catch(() => {});
  }
  markPromptDone();
  return 'off';
}

// On every app start while signed in: the same browser may now belong to a
// different staff member, or the language may have changed.
export async function refreshPush(labels) {
  if (currentSupport() !== 'supported' || Notification.permission !== 'granted') return;
  try {
    const subscription = await existingSubscription();
    if (subscription) await api.post('/push/subscribe', { subscription: subscription.toJSON(), labels });
  } catch {
    // Not important: the next start tries again.
  }
}

export function promptDone() {
  try {
    return localStorage.getItem(PROMPT_DONE_KEY) === '1';
  } catch {
    return true;
  }
}

export function markPromptDone() {
  try {
    localStorage.setItem(PROMPT_DONE_KEY, '1');
  } catch {
    // Private mode: the question may be asked again next time.
  }
}
