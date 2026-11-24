import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { JSDOM } from 'jsdom';
import { transformWithOxc } from 'vite';
import { translations } from '../../i18n/translations.js';
import { translateServerMessage } from '../../i18n/serverMessages.js';

// AI Settings: live model dropdown with labels, masked saved key with Edit,
// and Save only after a successful test of exactly what is on screen.
test('model dropdown, masked key and test-before-save', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost:5173' });
  for (const key of ['window', 'document', 'HTMLElement', 'HTMLInputElement', 'HTMLSelectElement', 'Event']) {
    globalThis[key] = dom.window[key];
  }
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const React = await import('react');
  const { createRoot } = await import('react-dom/client');

  const calls = [];
  const config = { provider: 'gemini', providerLabel: 'Gemini', modelName: 'gemini-3-flash-preview',
    keyHint: '********03hg', testStatus: 'connected', lastTestedAt: '2026-11-23' };
  const models = [
    { id: 'gemini-3.8-flash', label: 'Gemini 3.8 Flash', chat: true, preview: false, recommended: true },
    { id: 'gemini-3-flash-preview', label: 'Gemini 3 Flash Preview', chat: true, preview: true, recommended: false },
    { id: 'gemini-3.1-flash-image', label: 'Image', chat: false, preview: false, recommended: false },
  ];
  const api = {
    get: async (url) => { calls.push({ method: 'get', url }); return { data: { config } }; },
    post: async (url, payload) => {
      calls.push({ method: 'post', url, payload });
      if (url === '/ai-settings/models') return { data: { success: true, models, savedModel: config.modelName } };
      if (url === '/ai-settings/test') return { data: { success: true, message: 'AI provider connected successfully.' } };
      return { data: { success: true, config: { ...config, modelName: payload.model_name } } };
    },
  };
  const env = {
    React, useEffect: React.useEffect, useState: React.useState,
    PageHeader: ({ title }) => React.createElement('h1', null, title),
    api, useAuth: () => ({ user: { id: 1 } }),
    useLanguage: () => ({ t: (key) => translations.en[key] || key }),
    translateServerMessage,
    RetrievalAuditCard: () => null, // tested in RetrievalAuditCard.test.js
  };
  const source = (await fs.readFile(new URL('./AISettings.jsx', import.meta.url), 'utf8'))
    .replace(/^import .*;\r?\n/gm, '').replace('export default function AISettings()', 'function AISettings()');
  const compiled = await transformWithOxc(source, 'AISettings.jsx', { jsx: { runtime: 'classic' } });
  const AISettings = new Function(...Object.keys(env), `${compiled.code}\nreturn AISettings;`)(...Object.values(env));

  const root = createRoot(document.getElementById('root'));
  await React.act(async () => root.render(React.createElement(AISettings)));
  await React.act(async () => {});

  const $ = (selector) => document.querySelector(selector);
  const click = async (element) => React.act(async () => element.click());
  const choose = async (select, value) => React.act(async () => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, value);
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
  const button = (text) => [...document.querySelectorAll('button')].find((b) => b.textContent.includes(text));
  const saveButton = () => button(translations.en['ai.save']);

  // The list was loaded with the saved key (no key sent from the page).
  const listCall = calls.find((c) => c.url === '/ai-settings/models');
  assert.deepEqual(listCall.payload, { provider: 'gemini', api_key: '' });

  // Dropdown with labels, the saved model selected, and a manual option.
  const select = $('select[name="model_name"]');
  assert.ok(select, 'model dropdown shown');
  assert.equal(select.value, 'gemini-3-flash-preview');
  const optionText = [...select.options].map((option) => option.textContent).join('\n');
  assert.match(optionText, /gemini-3\.8-flash.*Recommended/);
  assert.match(optionText, /gemini-3-flash-preview.*Preview/);
  assert.match(optionText, /gemini-3\.1-flash-image.*Not for chat/);
  assert.ok([...select.options].some((option) => option.value === '__manual__'));

  // Saved key is masked, read-only, with Edit; the real key never reaches the page.
  const keyInput = $('input[name="api_key"]');
  assert.equal(keyInput.disabled, true);
  assert.equal(keyInput.value, '********03hg');
  assert.ok(button(translations.en['ai.edit']));

  // Save waits for a successful test of what is on screen.
  assert.equal(saveButton().disabled, true);
  await choose(select, 'gemini-3.8-flash');
  await click(button(translations.en['ai.test']));
  const testCall = calls.find((c) => c.url === '/ai-settings/test');
  assert.equal(testCall.payload.model_name, 'gemini-3.8-flash');
  assert.equal(testCall.payload.api_key, '');
  assert.equal(saveButton().disabled, false);

  // Changing the model after the test needs a new test.
  await choose($('select[name="model_name"]'), 'gemini-3-flash-preview');
  assert.equal(saveButton().disabled, true);
  await choose($('select[name="model_name"]'), 'gemini-3.8-flash');
  await click(button(translations.en['ai.test']));
  await React.act(async () => saveButton().closest('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  const saveCall = calls.find((c) => c.url === '/ai-settings' && c.method === 'post');
  assert.deepEqual({ model: saveCall.payload.model_name, key: saveCall.payload.api_key }, { model: 'gemini-3.8-flash', key: '' });

  // Edit opens an empty key box; Cancel goes back to the saved key.
  await click(button(translations.en['ai.edit']));
  assert.equal($('input[name="api_key"]').disabled, false);
  assert.equal($('input[name="api_key"]').value, '');
  await click(button(translations.en['ai.cancel']));
  assert.equal($('input[name="api_key"]').disabled, true);

  // "Other (type manually)" switches to a text box.
  await choose($('select[name="model_name"]'), '__manual__');
  assert.ok($('input[name="model_name"]'));
  assert.equal($('select[name="model_name"]'), null);

  await React.act(async () => root.unmount());
});
