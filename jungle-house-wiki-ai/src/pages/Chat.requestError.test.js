// A failed AI Chat request must show a short, friendly message in the staff
// member's language: never the browser's raw request error ("Network Error",
// "Request failed with status code 500"), a server error page, or a file path.
// Mounts the real Chat page with its imports replaced, like Chat.image.test.js.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { JSDOM } from 'jsdom';
import { transformWithOxc } from 'vite';
import * as issue from '../utils/chatIssueContext.js';
import * as escalation from '../utils/escalationResponse.js';
import * as safe from '../utils/safeHtml.js';
import { imageReferencesForQuestion } from '../utils/imageAttachmentContext.js';
import { imageFailureDetails } from '../utils/imageServiceError.js';
import { displayStoredText } from '../utils/storedChatText.js';
import { translations } from '../i18n/translations.js';

const FAKE_PATH = '/app/backend/src/app.py';
const FAKE_SECRET = 'sk-FAKE-SECRET-123';

function requestError(message, response) {
  // The shape Axios throws: a real Error whose message is technical text.
  return Object.assign(new Error(message), response ? { response } : { code: 'ERR_NETWORK' });
}

const FAILURES = [
  { name: 'server not reached', key: 'chat.error.connection',
    error: () => requestError('Network Error') },
  { name: 'timeout', key: 'chat.error.connection',
    error: () => requestError('timeout of 120000ms exceeded') },
  { name: 'server error page', key: 'chat.error.unavailable',
    error: () => requestError('Request failed with status code 500', { status: 500,
      data: `<html><body>Internal Server Error at ${FAKE_PATH} api_key=${FAKE_SECRET}</body></html>` }) },
  { name: 'gateway error with empty body', key: 'chat.error.unavailable',
    error: () => requestError('Request failed with status code 502', { status: 502, data: {} }) },
  { name: 'blank server message', key: 'chat.error.unavailable',
    error: () => requestError('Request failed with status code 503', { status: 503, data: { message: '   ' } }) },
  { name: 'signed out', key: 'chat.error.session',
    error: () => requestError('Request failed with status code 401', { status: 401, data: { code: 'SESSION_EXPIRED' } }) },
  { name: 'stale security token', key: 'chat.error.security',
    error: () => requestError('Request failed with status code 403', { status: 403, data: { code: 'CSRF_INVALID' } }) },
];

const TECHNICAL = ['Network Error', 'status code', 'timeout of', 'Flask', 'backend', FAKE_PATH, FAKE_SECRET, '<html'];

test('a failed chat request shows a friendly message in en, zh and ms, never the technical error', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost:5173' });
  for (const key of ['window', 'document', 'localStorage', 'HTMLElement', 'HTMLInputElement', 'HTMLTextAreaElement', 'Event', 'File', 'FormData', 'DOMParser']) {
    globalThis[key] = dom.window[key];
  }
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  HTMLElement.prototype.scrollIntoView = () => {};
  const React = await import('react');
  const { createRoot } = await import('react-dom/client');
  let language = 'en';
  let nextFailure = null;
  const originalConsoleError = console.error;
  console.error = () => {};  // Chat.jsx logs the failure to the browser console; keep test output clean.
  try {
    const env = {
      React, useEffect: React.useEffect, useState: React.useState, useRef: React.useRef,
      Link: ({ to, children }) => React.createElement('a', { href: to }, children),
      useAuth: () => ({ user: { id: 'synthetic-error-test', status: 'active', full_name: 'Synthetic User' } }),
      useLanguage: () => ({ language, t: (key, values = {}) => String(translations[language][key] || key)
        .replace(/\{(\w+)\}/g, (match, name) => (name in values ? values[name] : match)) }),
      useStaffChat: () => null, API_BASE_URL: '/api',
      api: { post: async () => { throw nextFailure(); } },
      ...issue, ...escalation, ...safe, imageReferencesForQuestion, imageFailureDetails, displayStoredText,
    };
    const source = (await fs.readFile(new URL('./Chat.jsx', import.meta.url), 'utf8'))
      .replace(/^import .*;\r?\n/gm, '').replace('export default function Chat()', 'function Chat()');
    const compiled = await transformWithOxc(source, 'Chat.jsx', { jsx: { runtime: 'classic' } });
    const Chat = new Function(...Object.keys(env), `${compiled.code}\nreturn Chat;`)(...Object.values(env));

    const ask = async (failure) => {
      nextFailure = failure;
      await React.act(async () => {
        const element = document.querySelector('.ai-chat-input-row > input');
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(element, 'How do I close the kiosk?');
        element.dispatchEvent(new Event('input', { bubbles: true }));
      });
      await React.act(async () => document.querySelector('.ai-chat-send-btn').click());
      return [...document.querySelectorAll('.message-bubble.ai')].at(-1).textContent;
    };

    for (const lang of ['en', 'zh', 'ms']) {
      language = lang;
      localStorage.clear();
      const root = createRoot(document.getElementById('root'));
      await React.act(async () => root.render(React.createElement(Chat)));

      for (const failure of FAILURES) {
        const shown = await ask(failure.error);
        assert.ok(translations[lang][failure.key], `${lang} has ${failure.key}`);
        assert.ok(shown.includes(translations[lang][failure.key]), `${lang} / ${failure.name}: ${shown}`);
        for (const text of TECHNICAL) assert.ok(!shown.includes(text), `${lang} / ${failure.name} shows "${text}"`);
      }

      // The server's own message is fixed, friendly text and is still shown as sent.
      const attachmentMessage = 'Lampiran tidak tersedia. Sila lampirkan imej sekali lagi.';
      const shownServerMessage = await ask(() => requestError('Request failed with status code 400', {
        status: 400, data: { message: attachmentMessage, source: 'attachment_unavailable' } }));
      assert.ok(shownServerMessage.includes(attachmentMessage));

      // The chat crash reply carries a ticket number: unchanged, the translated ticket text.
      const shownTicket = await ask(() => requestError('Request failed with status code 500', {
        status: 500, data: { reply: 'Sorry, something went wrong while answering.', escalation: true,
          escalation_id: 42, fallback: true, confidence: 0 } }));
      assert.ok(shownTicket.includes(translations[lang]['chat.ticketErrorSaved'].replace('{id}', '42')));

      // Nothing technical was saved into the browser's chat history either.
      const saved = Object.keys(localStorage).map((key) => localStorage.getItem(key)).join('\n');
      for (const text of TECHNICAL) assert.ok(!saved.includes(text), `${lang}: chat history saved "${text}"`);
      await React.act(async () => root.unmount());
    }
  } finally {
    console.error = originalConsoleError;
    dom.window.close();
  }
});

test('every new chat error message exists in English, Chinese and Malay', () => {
  for (const key of ['chat.error.session', 'chat.error.security', 'chat.error.unavailable', 'chat.error.connection']) {
    for (const lang of ['en', 'zh', 'ms']) {
      assert.equal(typeof translations[lang][key], 'string', `${lang} ${key}`);
      assert.ok(translations[lang][key].trim().length > 0, `${lang} ${key}`);
    }
  }
});
