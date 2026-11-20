// Keeps English, Chinese and Malay in step, and makes sure every key the pages use exists.
// A key missing from all three dictionaries silently shows its English fallback (or the key
// itself) in every language, which is how about 120 Training & Quiz texts stayed English.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SUPPORTED_LANGUAGES, translations } from './translations.js';
import { translateServerMessage } from './serverMessages.js';

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const placeholders = (text) => [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();

function sourceFiles(dir = SRC) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    return /\.(jsx?|mjs)$/.test(entry.name) && !/\.test\.js$/.test(entry.name) ? [full] : [];
  });
}

test('English, Chinese and Malay have exactly the same keys', () => {
  const english = Object.keys(translations.en).sort();
  assert.deepEqual(SUPPORTED_LANGUAGES, ['en', 'zh', 'ms']);
  for (const language of SUPPORTED_LANGUAGES) {
    const keys = Object.keys(translations[language]).sort();
    assert.deepEqual(keys.filter((key) => !(key in translations.en)), [], `${language} has keys English does not`);
    assert.deepEqual(english.filter((key) => !(key in translations[language])), [], `${language} is missing keys`);
  }
});

test('every text is filled in and keeps the same {placeholders} as English', () => {
  for (const [key, english] of Object.entries(translations.en)) {
    for (const language of SUPPORTED_LANGUAGES) {
      const text = translations[language][key];
      assert.equal(typeof text, 'string', `${language} ${key}`);
      assert.ok(text.trim(), `${language} ${key} is empty`);
      assert.deepEqual(placeholders(text), placeholders(english), `${language} ${key} placeholders`);
    }
  }
});

test('every key the pages ask for with t() or tOr() exists in all three languages', () => {
  // StaffPreferences.jsx and StaffLayout.jsx also call a local t() whose short keys
  // ("newChat", "settings") come from StaffPreferences' own en/zh/ms dictionary.
  const staffSource = fs.readFileSync(path.join(SRC, 'components', 'StaffPreferences.jsx'), 'utf8');
  const staffDictionary = staffSource.slice(staffSource.indexOf('const translations = {'));
  const staffKeys = new Set(
    [...staffDictionary.slice(0, staffDictionary.indexOf('\n};')).matchAll(/(\w+):\s*'/g)].map((match) => match[1])
  );
  assert.ok(staffKeys.has('newChat') && staffKeys.has('viewHistory'), 'StaffPreferences keys were read');
  const missing = [];
  for (const file of sourceFiles()) {
    // Comment lines only describe calls (e.g. "t('key', { n: 3 })"); skip them.
    const code = fs.readFileSync(file, 'utf8').split(/\r?\n/)
      .filter((line) => !/^\s*(\/\/|\/\*|\*)/.test(line)).join('\n');
    // Only a whole literal key: t('a.b') or t('a.b', vars). A key built with + or `${}` is skipped.
    for (const match of code.matchAll(/(?<![\w.$])(?:t|tOr|appT)\(\s*(['"])([^'"\n]+)\1\s*[,)]/g)) {
      const key = match[2];
      if (key in translations.en || staffKeys.has(key)) continue;
      missing.push(`${path.relative(SRC, file)}: ${key}`);
    }
  }
  assert.deepEqual(missing, []);
});

test('every server message mapping points at a key that exists', () => {
  const code = fs.readFileSync(path.join(SRC, 'i18n', 'serverMessages.js'), 'utf8');
  const keys = [...code.matchAll(/:\s*'([\w.]+)',?\s*$/gm), ...code.matchAll(/\/, '([\w.]+)', \(m\)/g)]
    .map((match) => match[1]);
  assert.ok(keys.length > 100, 'mappings were found');
  assert.deepEqual(keys.filter((key) => !(key in translations.en)), []);
});

test('server messages shown on the sign-in and escalation pages are translated, unknown ones are kept', () => {
  const t = (key, vars) => String(translations.zh[key]).replace(/\{(\w+)\}/g, (match, name) => vars?.[name] ?? match);
  assert.equal(translateServerMessage(t, 'Password reset link is invalid or expired.'), translations.zh['auth.reset.invalidLink']);
  assert.equal(translateServerMessage(t, 'Email is already registered.'), translations.zh['srv.auth.emailRegistered']);
  assert.equal(translateServerMessage(t, 'Network Error'), translations.zh['srv.client.networkError']);
  assert.equal(translateServerMessage(t, '3 escalation(s) moved to Trash Bin successfully.'),
    translations.zh['esc.msg.bulkMoved'].replace('{n}', '3'));
  assert.equal(translateServerMessage(t, 'A message nobody mapped.'), 'A message nobody mapped.');
});
