import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { JSDOM } from 'jsdom';
import { transformWithOxc } from 'vite';
import * as attachments from '../utils/messageAttachment.js';
import { translations } from '../i18n/translations.js';

test('member attachments: paste, remove, attachment-only send, failed upload retry and persisted display', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost:5173' });
  for (const key of ['window', 'document', 'HTMLElement', 'HTMLInputElement', 'HTMLTextAreaElement', 'Event', 'File', 'FormData']) {
    globalThis[key] = dom.window[key];
  }
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  HTMLElement.prototype.scrollTo = () => {};
  let revoked = 0;
  URL.createObjectURL = () => 'blob:synthetic-message-image';
  URL.revokeObjectURL = () => { revoked += 1; };
  const React = await import('react');
  const { createRoot } = await import('react-dom/client');
  const t = (key) => translations.en[key] || key;
  const language = { t, tOr: (key, fallback) => translations.en[key] || fallback, locale: 'en-GB' };
  const calls = [];
  let fail = false;
  let messages = [{ message_id: 10, thread_id: 10, sender_id: 2, receiver_id: 1,
    message: 'Synthetic greeting', created_at: new Date().toISOString() }];
  const thread = { thread_id: 10, latest_sender_id: 1, latest_receiver_id: 2, other_user_name: 'Test Member' };
  const api = {
    get: async (url) => ({ data: url === '/messages/users' ? [{ user_id: 2, full_name: 'Test Member' }, { user_id: 3, full_name: 'New Member' }]
      : url.startsWith('/messages/threads/') ? [thread] : messages }),
    post: async (url, payload) => {
      calls.push({ url, payload });
      if (fail) throw { response: { data: { message: 'Synthetic upload failure' } } };
      const file = payload instanceof FormData ? payload.get('attachment') : null;
      const message = payload instanceof FormData ? payload.get('message') : payload.message;
      const sent = { message_id: calls.length + 10, thread_id: 10, sender_id: 1, receiver_id: 2,
        created_at: new Date().toISOString(), message,
        attachments: file ? [{ attachment_id: 'a'.repeat(64), name: file.name, type: file.type, size: file.size,
          url: '/api/messages/attachments/' + 'a'.repeat(64) }] : [] };
      messages.push(sent);
      return { data: { sent_message: sent } };
    },
  };
  const env = { React, useEffect: React.useEffect, useRef: React.useRef, useState: React.useState,
    useMemo: React.useMemo, useCallback: React.useCallback, ...attachments, api, API_BASE_URL: '/api',
    useAuth: () => ({ user: { id: 1, full_name: 'Synthetic Sender' } }), useLanguage: () => language };
  const compile = async (path, suffix) => {
    const source = (await fs.readFile(new URL(path, import.meta.url), 'utf8'))
      .replace(/^import .*;\r?\n/gm, '').replace(/export default function /g, 'function ').replace(/export function /g, 'function ');
    const result = await transformWithOxc(source, path, { jsx: { runtime: 'classic' } });
    return new Function(...Object.keys(env), `${result.code}\n${suffix}`)(...Object.values(env));
  };
  Object.assign(env, await compile('../components/MessageAttachment.jsx', 'return { MessageAttachment, MessageAttachmentPicker };'));
  const Messages = await compile('./Messages.jsx', 'return Messages;');
  const root = createRoot(document.getElementById('root'));
  const flush = async (action) => React.act(async () => { await action(); await new Promise((resolve) => setTimeout(resolve, 0)); });
  const paste = async (selector, file) => flush(() => {
    const event = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(event, 'clipboardData', { value: { items: [{ type: file.type, getAsFile: () => file }] } });
    document.querySelector(selector).dispatchEvent(event);
  });
  const image = new File(['synthetic'], 'screenshot.png', { type: 'image/png' });
  try {
    await flush(() => root.render(React.createElement(Messages)));
    await flush(() => document.querySelector('.messages-thread-item').click());
    await paste('.messages-reply-bar textarea', image);
    assert.equal(document.querySelector('.messages-attachment-draft img').getAttribute('src'), 'blob:synthetic-message-image');
    assert.equal(document.querySelector('.messages-reply-send').disabled, false);
    await flush(() => document.querySelector('.messages-remove-file').click());
    assert.equal(document.querySelector('.messages-attachment-draft'), null);
    assert.equal(document.querySelector('.messages-reply-send').disabled, true);
    assert.ok(revoked > 0);
    await paste('.messages-reply-bar textarea', image);
    fail = true;
    await flush(() => document.querySelector('.messages-reply-send').click());
    assert.ok(document.querySelector('.messages-bubble.failed img'));
    assert.equal(calls[0].payload.get('attachment').name, 'screenshot.png');
    assert.equal(calls[0].payload.get('message'), '');
    fail = false;
    await flush(() => document.querySelector('.messages-delivery-status.failed button').click());
    assert.equal(calls[1].payload.get('attachment').name, 'screenshot.png');
    assert.equal(document.querySelector('.messages-bubble.failed'), null);
    assert.equal(document.querySelector('.messages-bubble img').getAttribute('src'), '/api/messages/attachments/' + 'a'.repeat(64));
    await flush(() => document.querySelector('.messages-top-action').click());
    await flush(() => document.querySelectorAll('.messages-person-row')[1].click());
    const pdf = new File(['synthetic PDF'], 'instructions.pdf', { type: 'application/pdf' });
    await flush(() => {
      const input = document.querySelector('.messages-first-message-form input[type="file"]');
      Object.defineProperty(input, 'files', { configurable: true, value: [pdf] });
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
    assert.equal(document.querySelector('.messages-send-new-btn').disabled, false);
    await flush(() => document.querySelector('.messages-send-new-btn').click());
    assert.equal(calls[2].url, '/messages/send');
    assert.equal(calls[2].payload.get('receiver_id'), '3');
    assert.equal(calls[2].payload.get('attachment').name, 'instructions.pdf');
    assert.equal(calls[2].payload.get('message'), '');
    assert.ok(document.querySelector('.messages-bubble .messages-file-info').textContent.includes('instructions.pdf'));
  } finally {
    await flush(() => root.unmount());
    dom.window.close();
  }
});

test('plain text paste is preserved and unsafe or oversized attachments are rejected', () => {
  let prevented = false;
  let selected = false;
  attachments.pastedImage({ clipboardData: { items: [{ type: 'text/plain' }] },
    preventDefault: () => { prevented = true; } }, () => { selected = true; });
  assert.equal(prevented, false);
  assert.equal(selected, false);
  for (const file of [{ name: 'x.svg', size: 10 }, { name: 'x.png', size: 0 }, { name: 'x.pdf', size: 8 * 1024 * 1024 }]) {
    assert.equal(attachments.validateMessageFile(file), false);
  }
  assert.equal(attachments.validateMessageFile({ name: 'x.docx', size: 100 }), true);
});
