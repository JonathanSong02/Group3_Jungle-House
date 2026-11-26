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
import { aiTaskTestEnv } from './chatTestEnv.js';

// AI keeps running after the page is left (2026-11-26): ask, go to another
// page before the AI answers, come back -- the answer is in that chat.
async function setup(apiOverrides = {}) {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost:5173' });
  for (const key of ['window', 'document', 'localStorage', 'HTMLElement', 'HTMLInputElement', 'HTMLTextAreaElement', 'Event', 'File', 'FormData', 'DOMParser']) {
    globalThis[key] = dom.window[key];
  }
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  HTMLElement.prototype.scrollIntoView = () => {};
  globalThis.alert = (text) => alerts.push(text);
  const alerts = [];
  const React = await import('react');
  const { createRoot } = await import('react-dom/client');
  const replies = [];
  const posts = [];
  const api = {
    post: (url, payload) => {
      posts.push({ url, payload });
      if (url === '/chat/cancel') return Promise.resolve({ data: {} });
      return new Promise((resolve) => replies.push(resolve));
    },
    ...apiOverrides,
  };
  const env = {
    React, useEffect: React.useEffect, useState: React.useState, useRef: React.useRef,
    Link: ({ to, children }) => React.createElement('a', { href: to }, children),
    useAuth: () => ({ user: { id: 'synthetic-background-test', status: 'active', full_name: 'Synthetic User' } }),
    useLanguage: () => ({ language: 'en', t: (key) => translations.en[key] || key }),
    useStaffChat: () => null, API_BASE_URL: '/api', api,
    ...issue, ...escalation, ...safe, imageReferencesForQuestion, imageFailureDetails, displayStoredText,
  };
  Object.assign(env, aiTaskTestEnv(React, api));
  const source = (await fs.readFile(new URL('./Chat.jsx', import.meta.url), 'utf8'))
    .replace(/^import .*;\r?\n/gm, '').replace('export default function Chat()', 'function Chat()');
  const compiled = await transformWithOxc(source, 'Chat.jsx', { jsx: { runtime: 'classic' } });
  const Chat = new Function(...Object.keys(env), `${compiled.code}\nreturn Chat;`)(...Object.values(env));
  const mount = async () => {
    const root = createRoot(document.getElementById('root'));
    await React.act(async () => root.render(React.createElement(Chat)));
    return root;
  };
  const ask = async (text) => {
    await React.act(async () => {
      const element = document.querySelector('.ai-chat-input-row > input');
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(element, text);
      element.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await React.act(async () => document.querySelector('.ai-chat-send-btn').click());
  };
  return { React, env, mount, ask, replies, posts, alerts };
}

const answer = (text) => ({ data: { type: 'text', source: 'ai_provider_answer', reply: text, answer: text, fallback: false, escalation_ready: false } });

test('an answer that arrives after leaving the chat page is there when it opens again', async () => {
  const { React, mount, ask, replies } = await setup();
  localStorage.clear();
  const root = await mount();
  await ask('How many cabinets do I open?');
  assert.ok(document.body.textContent.includes(translations.en['chat.generating']));

  await React.act(async () => root.unmount()); // staff member goes to another page
  await React.act(async () => replies[0](answer('Open cabinets 1 to 3.')));

  const saved = JSON.parse(localStorage.getItem('jh_ai_chat_sessions_synthetic-background-test'));
  assert.ok(saved[0].messages.some((message) => message.sender === 'ai' && message.text === 'Open cabinets 1 to 3.'));

  const again = await mount();
  assert.ok(document.body.textContent.includes('Open cabinets 1 to 3.'));
  assert.ok(!document.body.textContent.includes(translations.en['chat.generating']));
  await React.act(async () => again.unmount());
});

test('coming back while the AI is still answering shows it is still thinking, then the answer', async () => {
  const { React, mount, ask, replies } = await setup();
  localStorage.clear();
  const root = await mount();
  await ask('Closing steps?');
  await React.act(async () => root.unmount());

  const again = await mount();
  assert.ok(document.body.textContent.includes(translations.en['chat.generating']));
  await React.act(async () => replies[0](answer('Lock the shutter last.')));
  assert.ok(document.body.textContent.includes('Lock the shutter last.'));
  assert.ok(!document.body.textContent.includes(translations.en['chat.generating']));
  await React.act(async () => again.unmount());
});

test('Stop still works and sends the cancel with the same request id', async () => {
  const { React, mount, ask, posts } = await setup({
    post: (url, payload, options) => {
      posts.push({ url, payload });
      if (url === '/chat/cancel') return Promise.resolve({ data: {} });
      return new Promise((resolve, reject) => options.signal.addEventListener('abort', () =>
        reject(Object.assign(new Error('canceled'), { code: 'ERR_CANCELED', name: 'CanceledError' }))));
    },
  });
  localStorage.clear();
  const root = await mount();
  await ask('Stock count?');
  const stop = document.querySelector('.ai-chat-stop-btn') || [...document.querySelectorAll('button')].find((button) => button.textContent.includes(translations.en['chat.stop'] || 'Stop'));
  await React.act(async () => stop.click());
  const chat = posts.find((call) => call.url === '/chat');
  const cancel = posts.find((call) => call.url === '/chat/cancel');
  assert.equal(cancel.payload.request_id, chat.payload.request_id);
  assert.ok(document.body.textContent.includes(translations.en['chat.stopped']));
  await React.act(async () => root.unmount());
});
