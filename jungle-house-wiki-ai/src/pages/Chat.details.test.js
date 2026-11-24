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

// AI-first answers: "Show more details" opens the article in place, with the
// same ArticleBody as the Knowledge Base page; related articles are buttons
// that ask about that article.
test('show more details opens the article in place and related articles ask about it', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost:5173' });
  for (const key of ['window', 'document', 'localStorage', 'HTMLElement', 'HTMLInputElement', 'HTMLTextAreaElement',
    'Event', 'File', 'FormData', 'DOMParser', 'NodeFilter', 'Node']) {
    globalThis[key] = dom.window[key];
  }
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  HTMLElement.prototype.scrollIntoView = () => {};
  const React = await import('react');
  const { createRoot } = await import('react-dom/client');
  const posts = [];
  const gets = [];
  const t = (key) => translations.en[key] || key;
  const api = {
    get: async (url) => {
      gets.push(url);
      if (url === '/articles/9') {
        return { data: { article_id: 9, title: 'Ice Bin', category: 'SOP',
          content: '<p>Put the ice in the ice bin first.</p><p><a href="https://example.com/ice">Ice guide</a></p>' } };
      }
      return { data: [] };
    },
    post: async (url, payload) => {
      posts.push(payload);
      return { data: { type: 'text', source: 'ai_provider_answer', reply: 'After buying ice, store it in the ice bin.',
        answer: 'After buying ice, store it in the ice bin.', article_id: 9, title: 'Ice Bin', fallback: false,
        escalation_ready: false, related_articles: [{ title: 'Kiosk Closing', article_id: 6 }, { title: 'Ice Bin Cleaning', article_id: 7 }] } };
    },
  };
  const compile = async (path, name, extraEnv) => {
    const source = (await fs.readFile(new URL(path, import.meta.url), 'utf8'))
      .replace(/^import [\s\S]*?;\r?\n/gm, '').replace(`export default function ${name}(`, `function ${name}(`);
    const code = (await transformWithOxc(source, path, { jsx: { runtime: 'classic' } })).code;
    return new Function(...Object.keys(extraEnv), `${code}\nreturn ${name};`)(...Object.values(extraEnv));
  };
  const base = { React, useEffect: React.useEffect, useState: React.useState, useRef: React.useRef,
    useLanguage: () => ({ language: 'en', t }), api, API_BASE_URL: '/api',
    rewriteSrcset: safe.rewriteSrcset, sanitizeHtml: safe.sanitizeHtml };
  const ArticleBody = await compile('../components/ArticleBody.jsx', 'ArticleBody', base);
  const ChatArticleDetails = await compile('../components/ChatArticleDetails.jsx', 'ChatArticleDetails', { ...base, ArticleBody });
  const env = {
    ...base, ChatArticleDetails,
    Link: ({ to, children }) => React.createElement('a', { href: to }, children),
    useAuth: () => ({ user: { id: 'synthetic-details-test', status: 'active', full_name: 'Synthetic User' } }),
    useStaffChat: () => null,
    ...issue, ...escalation, ...safe, imageReferencesForQuestion, imageFailureDetails, displayStoredText,
  };
  const Chat = await compile('./Chat.jsx', 'Chat', env);

  localStorage.clear();
  const root = createRoot(document.getElementById('root'));
  await React.act(async () => root.render(React.createElement(Chat)));
  const ask = async (text) => {
    await React.act(async () => {
      const element = document.querySelector('.ai-chat-input-row > input');
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(element, text);
      element.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await React.act(async () => document.querySelector('.ai-chat-send-btn').click());
  };
  await ask('after buying ice what do I do');
  const toggle = () => document.querySelector('.chat-article-details-toggle');

  // Collapsed by default: the answer only.
  assert.ok(document.body.textContent.includes('After buying ice, store it in the ice bin.'));
  assert.equal(toggle().textContent.includes(t('chat.showMoreDetails')), true);
  assert.equal(document.querySelector('.chat-article-details .article-content'), null);

  // Opens in place with the Knowledge Base article body (text and links).
  await React.act(async () => toggle().click());
  await React.act(async () => {});
  assert.ok(gets.includes('/articles/9'));
  const body = document.querySelector('.chat-article-details .article-detail-page .article-content');
  assert.ok(body, 'article body shown inside the chat');
  assert.ok(body.textContent.includes('Put the ice in the ice bin first.'));
  assert.equal(body.querySelector('a').getAttribute('href'), 'https://example.com/ice');
  assert.equal(window.location.pathname, '/');   // no page change

  // Closes again.
  await React.act(async () => toggle().click());
  assert.equal(document.querySelector('.chat-article-details .article-content'), null);

  // Related articles are numbered buttons that ask about that article.
  assert.ok(document.body.textContent.includes(t('chat.relatedArticles')));
  const related = [...document.querySelectorAll('.related-article-btn')];
  assert.deepEqual(related.map((button) => button.querySelector('.clarify-option-label').textContent), ['Kiosk Closing', 'Ice Bin Cleaning']);
  await React.act(async () => related[0].click());
  assert.equal(posts[1].question, 'Kiosk Closing');
  await React.act(async () => root.unmount());
});
