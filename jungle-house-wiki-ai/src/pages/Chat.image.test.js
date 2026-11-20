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

test('standard and Staff composers preserve file selection, preview, image+text and refreshed image references', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost:5173' });
  for (const key of ['window', 'document', 'localStorage', 'HTMLElement', 'HTMLInputElement', 'HTMLTextAreaElement', 'Event', 'File', 'FormData', 'DOMParser']) {
    globalThis[key] = dom.window[key];
  }
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  HTMLElement.prototype.scrollIntoView = () => {};
  URL.createObjectURL = () => 'blob:synthetic-preview';
  URL.revokeObjectURL = () => {};
  const React = await import('react');
  const { createRoot } = await import('react-dom/client');
  const reference = 'a'.repeat(64);
  const calls = [];
  let failImage = false;
  let showOptions = false;
  let staff = null;
  const env = {
    React, useEffect: React.useEffect, useState: React.useState, useRef: React.useRef,
    Link: ({ to, children }) => React.createElement('a', { href: to }, children),
    useAuth: () => ({ user: { id: 'synthetic-image-test', status: 'active', full_name: 'Synthetic User' } }),
    useLanguage: () => ({ language: 'en', t: (key) => translations.en[key] || key }),
    useStaffChat: () => staff, API_BASE_URL: '/api',
    api: { post: async (url, payload) => {
      calls.push({ url, payload });
      if (failImage) throw { response: { status: 503, data: {
        message: 'Image storage needs a database update.', source: 'image_service_unavailable',
        code: 'IMAGE_SCHEMA_NOT_READY', error_id: 'b'.repeat(16),
      } } };
      if (showOptions) return { data: {
        type: 'options', source: 'image_related_articles', answer: 'Related articles',
        confidence_kind: 'not_calibrated', answer_evidence: 'current_kb', fallback: false,
        options: [{ title: 'Staff belongings Area', article_id: 123, answer: 'Keep personal items on the shelf.',
          source: 'image_related_articles', confidence_kind: 'not_calibrated', answer_evidence: 'current_kb',
          link: '/knowledge/123' }],
      } };
      return { data: { reply: 'Matching article', answer: '<h2>Full article</h2><p>Final opening instruction.</p>', source: 'image_article_match',
        title: 'Staff belongings Area', article_id: 123,
        confidence_kind: 'not_calibrated', answer_evidence: 'current_kb', attachment_refs: [reference],
        uploaded_image_url: `/api/chat/attachments/${reference}?chat=main-test` } };
    } }, ...issue, ...escalation, ...safe, imageReferencesForQuestion,
    imageFailureDetails, displayStoredText,
  };
  const source = (await fs.readFile(new URL('./Chat.jsx', import.meta.url), 'utf8'))
    .replace(/^import .*;\r?\n/gm, '').replace('export default function Chat()', 'function Chat()');
  const compiled = await transformWithOxc(source, 'Chat.jsx', { jsx: { runtime: 'classic' } });
  const Chat = new Function(...Object.keys(env), `${compiled.code}\nreturn Chat;`)(...Object.values(env));
  const renderImages = new Function(...Object.keys(env), `${compiled.code}\nreturn renderImages;`)(...Object.values(env));
  for (const staffMode of [false, true]) {
    localStorage.clear();
    calls.length = 0;
    staff = staffMode ? { publish: () => {}, command: null } : null;
    let root = createRoot(document.getElementById('root'));
    const mount = async () => React.act(async () => root.render(React.createElement(Chat)));
    const setText = async (value) => React.act(async () => {
      const element = document.querySelector(staffMode ? 'textarea' : '.ai-chat-input-row > input');
      const proto = staffMode ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(element, value);
      element.dispatchEvent(new Event('input', { bubbles: true }));
    });
    const send = async () => React.act(async () => document.querySelector(staffMode ? '.staff-send-button' : '.ai-chat-send-btn').click());
    await mount();
    assert.equal(document.querySelectorAll('input[type=file]').length, 1);
    assert.equal(document.querySelector('[capture]'), null);
    const input = document.querySelector('input[type=file]');
    const photo = new File(['synthetic'], 'fixture.png', { type: 'image/png' });
    Object.defineProperty(input, 'files', { configurable: true, value: [photo] });
    await React.act(async () => input.dispatchEvent(new Event('change', { bubbles: true })));
    const preview = staffMode ? '.staff-attachment-preview img' : '.chat-upload-preview img';
    assert.equal(document.querySelector(preview).getAttribute('src'), 'blob:synthetic-preview');
    const questionInput = document.querySelector(staffMode ? 'textarea' : '.ai-chat-input-row > input');
    const paste = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(paste, 'clipboardData', { value: {
      items: [{ type: 'image/png', getAsFile: () => photo }],
    } });
    await React.act(async () => questionInput.dispatchEvent(paste));
    assert.equal(paste.defaultPrevented, true);
    assert.equal(document.querySelector(preview).getAttribute('src'), 'blob:synthetic-preview');
    await setText('Where should I put this bottle?');
    await send();
    assert.equal(calls[0].payload.get('attachment'), photo);
    assert.equal(calls[0].payload.get('question'), 'Where should I put this bottle?');
    const savedImageSelector = '.message-bubble.user img';
    const savedImageUrl = `/api/chat/attachments/${reference}?chat=main-test`;
    assert.equal(document.querySelector(savedImageSelector)?.getAttribute('src'), savedImageUrl);
    assert.equal(document.querySelector('.message-bubble.user a'), null);
    assert.ok(localStorage.getItem('jh_ai_chat_sessions_synthetic-image-test').includes(reference));
    assert.ok(document.querySelector('.message-bubble.ai a[href="/knowledge/123"]'));
    assert.ok(document.body.textContent.includes('Final opening instruction.'));
    assert.ok(!document.body.textContent.includes('Fallback'));
    await React.act(async () => root.unmount());
    root = createRoot(document.getElementById('root'));
    await mount();
    assert.equal(document.querySelector(savedImageSelector)?.getAttribute('src'), savedImageUrl);
    await setText('Where should I put it?');
    await send();
    assert.deepEqual(calls.at(-1).payload.attachment_refs, [reference]);
    await setText('Attendance policy');
    await send();
    assert.equal(calls.at(-1).payload.attachment_refs, undefined);
    showOptions = true;
    await setText('Show related articles');
    await send();
    const optionsMessage = [...document.querySelectorAll('.message-bubble.ai')].at(-1);
    assert.ok(!optionsMessage.textContent.includes('0%'));
    await React.act(async () => optionsMessage.querySelector('button').click());
    const selectedMessage = [...document.querySelectorAll('.message-bubble.ai')].at(-1);
    assert.ok(!selectedMessage.textContent.includes('0%'));
    assert.ok(selectedMessage.querySelector('a[href="/knowledge/123"]'));
    showOptions = false;
    const beforeFailures = document.body.textContent.match(/Match score \(not probability\)/g)?.length || 0;
    failImage = true;
    const retryInput = document.querySelector('input[type=file]');
    Object.defineProperty(retryInput, 'files', { configurable: true, value: [photo] });
    await React.act(async () => retryInput.dispatchEvent(new Event('change', { bubbles: true })));
    await setText('Where should I put this bottle?');
    await send();
    assert.ok(document.body.textContent.includes('Image storage needs a database update.'));
    assert.ok(document.body.textContent.includes('Support reference: ' + 'b'.repeat(16)));
    assert.ok(document.body.textContent.includes('image_service_unavailable'));
    assert.equal(document.body.textContent.match(/Match score \(not probability\)/g)?.length || 0, beforeFailures);
    failImage = false;
    await React.act(async () => root.unmount());
  }
  const attachmentRoot = createRoot(document.getElementById('root'));
  await React.act(async () => attachmentRoot.render(renderImages([
    `/api/chat/attachments/${reference}?chat=main-test`,
    '/static/uploads/chat/synthetic.pdf',
    '/static/uploads/chat/synthetic.docx',
  ])));
  assert.equal(document.querySelectorAll('img').length, 1);
  assert.deepEqual([...document.querySelectorAll('a')].map((link) => link.getAttribute('href')), [
    '/static/uploads/chat/synthetic.pdf', '/static/uploads/chat/synthetic.docx',
  ]);
  await React.act(async () => attachmentRoot.unmount());
  dom.window.close();
});
