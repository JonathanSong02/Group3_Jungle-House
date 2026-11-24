import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { JSDOM } from 'jsdom';
import { transformWithOxc } from 'vite';
import { translations } from '../../i18n/translations.js';

// AI Model Settings: "Check search accuracy" card -- start, progress, report.
async function setup(api) {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost:5173' });
  for (const key of ['window', 'document', 'HTMLElement', 'Event']) globalThis[key] = dom.window[key];
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const React = await import('react');
  const { createRoot } = await import('react-dom/client');
  const t = (key, vars = {}) =>
    (translations.en[key] || key).replace(/\{(\w+)\}/g, (match, name) => (name in vars ? String(vars[name]) : match));
  const env = { React, useEffect: React.useEffect, useRef: React.useRef, useState: React.useState,
    api, useLanguage: () => ({ t }) };
  const source = (await fs.readFile(new URL('./RetrievalAuditCard.jsx', import.meta.url), 'utf8'))
    .replace(/^import .*;\r?\n/gm, '')
    .replace('const POLL_MS = 2000;', 'const POLL_MS = 5;')
    .replace('export default function RetrievalAuditCard()', 'function RetrievalAuditCard()');
  const compiled = await transformWithOxc(source, 'RetrievalAuditCard.jsx', { jsx: { runtime: 'classic' } });
  const Card = new Function(...Object.keys(env), `${compiled.code}\nreturn RetrievalAuditCard;`)(...Object.values(env));
  const root = createRoot(document.getElementById('root'));
  await React.act(async () => root.render(React.createElement(Card)));
  await React.act(async () => {});
  return { React, root };
}

const settle = (React, ms = 60) => React.act(() => new Promise((resolve) => setTimeout(resolve, ms)));
const button = (text) => [...document.querySelectorAll('button')].find((b) => b.textContent.includes(text));
const en = translations.en;

const RESULT = {
  articleCount: 512, total: 1200, passed: 1150, rate: 0.9583, wrongArticle: 30, lineCut: 20,
  durationSeconds: 184.2, finishedAt: '2026-11-24T04:00:00+00:00', foundElsewhere: 40,
  duplicates: [{ reason: 'same_title', titles: ['Stirrer & Tissue Location SOP'], articles: [
    { article_id: 31, title: 'Stirrer & Tissue Location SOP', category: 'SOP' },
    { article_id: 88, title: 'Stirrer & Tissue Location SOP', category: 'Notion' }] }],
  misses: Array.from({ length: 12 }, (_, i) => ({
    question: `cabinet unlock ${i}`, article_id: i, article_title: 'JHKC Opening Checklist',
    expected: 'Unlock all cabinet doors from B, C, E, F, K and L.',
    cause: i % 2 ? 'line_cut' : 'wrong_article', picked: ['Promotion', 'Closing'],
  })),
};

test('start, progress, then score, causes and misses', async () => {
  const calls = [];
  let gets = 0;
  const states = [
    { status: 'idle', result: null },
    { status: 'running', done: 300, total: 1200, result: null },
    { status: 'done', done: 1200, total: 1200, result: RESULT },
  ];
  const api = {
    get: async (url) => { calls.push(['get', url]); return { data: { audit: states[Math.min(gets++ ? 2 : 0, 2)] } }; },
    post: async (url) => { calls.push(['post', url]); return { data: { audit: states[1] } }; },
  };
  const { React, root } = await setup(api);

  assert.match(document.body.textContent, new RegExp(en['ai.audit.never'].slice(0, 15)));
  await React.act(async () => button(en['ai.audit.start']).click());
  assert.deepEqual(calls.find((c) => c[0] === 'post'), ['post', '/ai-settings/retrieval-audit']);
  assert.match(document.body.textContent, /300 \/ 1200 questions/);
  assert.equal(button(en['ai.audit.checking']).disabled, true, 'cannot start twice');

  await settle(React); // polls until done
  const text = document.body.textContent;
  assert.match(text, /95\.8%/);
  assert.match(text, /1150 of 1200 questions · 512 articles/);
  assert.match(text, /took 184s/);
  assert.match(text, /Includes 40 found in another article/);
  assert.match(text, /Duplicate articles \(1\)/);
  assert.match(text, /2 with the same title/);
  assert.match(text, /#88 Stirrer & Tissue Location SOP · Notion/);
  assert.equal(document.querySelectorAll('.ais-audit-misses:not(.ais-audit-duplicates) li').length, 10, 'first 10 shown');
  assert.equal(document.querySelectorAll('.ais-audit-cause.line_cut').length, 5);
  assert.match(text, /Search picked:.*Promotion · Closing/);
  await React.act(async () => button('Show all (12)').click());
  assert.equal(document.querySelectorAll('.ais-audit-misses:not(.ais-audit-duplicates) li').length, 12);
  assert.equal(button(en['ai.audit.start']).disabled, false);

  await React.act(async () => root.unmount());
});

test('a failed start shows a message', async () => {
  const api = {
    get: async () => ({ data: { audit: { status: 'idle', result: null } } }),
    post: async () => { const error = new Error('x'); error.response = { status: 500 }; throw error; },
  };
  const { React, root } = await setup(api);
  await React.act(async () => button(en['ai.audit.start']).click());
  assert.match(document.body.textContent, new RegExp(en['ai.audit.failed']));
  await React.act(async () => root.unmount());
});
