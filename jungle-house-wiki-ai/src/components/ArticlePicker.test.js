import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { JSDOM } from 'jsdom';
import { transformWithOxc } from 'vite';
import { translations } from '../i18n/translations.js';

// Quiz article picker (2026-11-26): search, category buttons, tick several,
// "select all listed", at most 30.
const articles = [
  { article_id: 1, title: 'Opening SOP', category: 'SOP' },
  { article_id: 2, title: 'Closing SOP', category: 'SOP' },
  { article_id: 3, title: 'Promotion', category: 'SALES' },
  { article_id: 4, title: 'Honey Stick', category: 'PRODUCT' },
  { article_id: 5, title: 'Opening checklist for new staff', category: 'Training' },
];

async function setup({ list = articles, max = 30, start = [] } = {}) {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost:5173' });
  for (const key of ['window', 'document', 'HTMLElement', 'HTMLInputElement', 'Event']) globalThis[key] = dom.window[key];
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const React = await import('react');
  const { createRoot } = await import('react-dom/client');
  const t = (key, vars = {}) =>
    (translations.en[key] || key).replace(/\{(\w+)\}/g, (match, name) => (name in vars ? String(vars[name]) : match));
  const source = (await fs.readFile(new URL('./ArticlePicker.jsx', import.meta.url), 'utf8'))
    .replace(/^import .*;\r?\n/gm, '')
    .replace('export default function ArticlePicker(', 'function ArticlePicker(');
  const compiled = await transformWithOxc(source, 'ArticlePicker.jsx', { jsx: { runtime: 'classic' } });
  const env = { React, useMemo: React.useMemo, useState: React.useState };
  const ArticlePicker = new Function(...Object.keys(env), `${compiled.code}\nreturn ArticlePicker;`)(...Object.values(env));

  const state = { selected: start };
  const root = createRoot(document.getElementById('root'));
  const render = () => root.render(React.createElement(ArticlePicker, {
    articles: list, selected: state.selected, max, t, catLabel: (c) => c, idPrefix: 'test',
    onChange: (ids) => { state.selected = ids; render(); },
  }));
  await React.act(async () => render());

  const act = (fn) => React.act(async () => fn());
  const rows = () => [...document.querySelectorAll('.article-picker-row')].map((row) => row.textContent);
  const type = (text) => act(() => {
    const input = document.querySelector('.article-picker-search');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, text);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  const tick = (title) => act(() => [...document.querySelectorAll('.article-picker-row')]
    .find((row) => row.textContent.includes(title)).querySelector('input').click());
  const button = (text) => [...document.querySelectorAll('button')].find((b) => b.textContent.includes(text));
  return { state, act, rows, type, tick, button, t };
}

test('typing filters the list by title', async () => {
  const { rows, type } = await setup();
  await type('open');
  assert.deepEqual(rows().map((row) => row.split(' — ')[0]), ['Opening SOP', 'Opening checklist for new staff']);
});

test('category buttons narrow the list, All shows everything', async () => {
  const { rows, act, button } = await setup();
  await act(() => button('SALES').click());
  assert.equal(rows().length, 1);
  await act(() => button(translations.en['picker.all']).click());
  assert.equal(rows().length, 5);
});

test('several articles can be ticked and removed again', async () => {
  const { state, tick, act } = await setup();
  await tick('Promotion');
  await tick('Opening SOP');
  assert.deepEqual(state.selected, ['3', '1']);
  assert.ok(document.body.textContent.includes('2 selected'));
  await act(() => document.querySelector('.article-picker-chip button').click());   // ✕ on the first chip
  assert.deepEqual(state.selected, ['1']);
});

test('select all listed ticks only what the search shows', async () => {
  const { state, type, act } = await setup();
  await type('sop');
  await act(() => document.querySelector('.article-picker-all input').click());
  assert.deepEqual(state.selected, ['1', '2']);
  await act(() => document.querySelector('.article-picker-all input').click());      // again: untick them
  assert.deepEqual(state.selected, []);
});

test('no more than the maximum, with a message', async () => {
  const { state, act, t } = await setup({ max: 2 });
  await act(() => document.querySelector('.article-picker-all input').click());
  assert.equal(state.selected.length, 2);
  assert.ok(document.body.textContent.includes(t('picker.max', { max: 2 })));
  const unticked = [...document.querySelectorAll('.article-picker-row input')].filter((box) => !box.checked);
  assert.ok(unticked.every((box) => box.disabled));
});

test('nothing found says so', async () => {
  const { rows, type } = await setup();
  await type('zzz');
  assert.equal(rows().length, 0);
  assert.ok(document.body.textContent.includes(translations.en['picker.none']));
});
