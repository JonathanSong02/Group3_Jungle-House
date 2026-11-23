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

// When the AI asks a clarifying question it can offer short answers as
// buttons; clicking one sends it as the next question, like typing it.
test('clarifying question options are buttons that send the chosen answer', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost:5173' });
  for (const key of ['window', 'document', 'localStorage', 'HTMLElement', 'HTMLInputElement', 'HTMLTextAreaElement', 'Event', 'File', 'FormData', 'DOMParser']) {
    globalThis[key] = dom.window[key];
  }
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  HTMLElement.prototype.scrollIntoView = () => {};
  const React = await import('react');
  const { createRoot } = await import('react-dom/client');
  const calls = [];
  let staff = null;
  const env = {
    React, useEffect: React.useEffect, useState: React.useState, useRef: React.useRef,
    Link: ({ to, children }) => React.createElement('a', { href: to }, children),
    useAuth: () => ({ user: { id: 'synthetic-clarify-test', status: 'active', full_name: 'Synthetic User' } }),
    useLanguage: () => ({ language: 'en', t: (key) => translations.en[key] || key }),
    useStaffChat: () => staff, API_BASE_URL: '/api',
    api: { post: async (url, payload) => {
      calls.push({ url, payload });
      if (calls.length === 1) {
        return { data: { type: 'text', source: 'ai_provider_clarify', reply: 'Which store do you mean?',
          answer: 'Which store do you mean?', fallback: false, escalation_ready: false,
          clarify_options: ['ST3', 'Spring Mall'] } };
      }
      return { data: { type: 'text', source: 'ai_provider_answer', reply: 'Open the ST3 shutter first.',
        answer: 'Open the ST3 shutter first.', fallback: false, escalation_ready: false } };
    } }, ...issue, ...escalation, ...safe, imageReferencesForQuestion,
    imageFailureDetails, displayStoredText,
  };
  const source = (await fs.readFile(new URL('./Chat.jsx', import.meta.url), 'utf8'))
    .replace(/^import .*;\r?\n/gm, '').replace('export default function Chat()', 'function Chat()');
  const compiled = await transformWithOxc(source, 'Chat.jsx', { jsx: { runtime: 'classic' } });
  const Chat = new Function(...Object.keys(env), `${compiled.code}\nreturn Chat;`)(...Object.values(env));

  for (const staffMode of [false, true]) {
    localStorage.clear();
    calls.length = 0;
    staff = staffMode ? { publish: () => {}, command: null } : null;
    const root = createRoot(document.getElementById('root'));
    await React.act(async () => root.render(React.createElement(Chat)));
    await React.act(async () => {
      const element = document.querySelector(staffMode ? 'textarea' : '.ai-chat-input-row > input');
      const proto = staffMode ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(element, 'How do I open the shop?');
      element.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await React.act(async () => document.querySelector(staffMode ? '.staff-send-button' : '.ai-chat-send-btn').click());

    const options = [...document.querySelectorAll('.clarify-option-btn')];
    assert.deepEqual(options.map((button) => button.textContent), ['ST3', 'Spring Mall'], `staffMode=${staffMode}`);

    await React.act(async () => options[0].click());
    assert.equal(calls.length, 2);
    assert.equal(calls[1].payload.question, 'ST3');
    assert.ok(document.body.textContent.includes('Open the ST3 shutter first.'));
    // The question the staff member "sent" by clicking shows as their own message.
    assert.ok([...document.querySelectorAll('.message-bubble.user')].some((bubble) => bubble.textContent.includes('ST3')));
    await React.act(async () => root.unmount());
  }
});
