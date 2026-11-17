// Tests for the shared HTML sanitizer. jsdom (a test-only devDependency) provides the DOM that DOMPurify
// needs in Node. The real browser check is done separately in headless Chrome.
import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import {
  ALLOWED_ATTRIBUTES,
  ALLOWED_TAGS,
  createEditorHtmlCleaner,
  createSafeHtml,
  createStoredEditorHtmlCleaner,
  isHtmlContent,
  isSafeUrl,
  normaliseUrl,
  rewriteSrcset,
} from './safeHtml.js';

const { window } = new JSDOM('<!doctype html><html><head></head><body></body></html>', { url: 'https://app.example/chat' });
const { sanitize } = createSafeHtml(window);

function parse(html) {
  const container = window.document.createElement('div');
  container.innerHTML = html;
  return container;
}

// Everything the sanitizer must never let through, found anywhere in its output.
function assertNothingExecutable(html, label) {
  const root = parse(html);
  const forbiddenTags = 'script, style, link, meta, base, title, iframe, frame, frameset, object, embed, form, ' +
    'input, button, select, textarea, option, svg, math, template, noscript, applet, animate, set';
  assert.equal(root.querySelectorAll(forbiddenTags).length, 0, `${label}: forbidden tag survived: ${html}`);
  root.querySelectorAll('*').forEach((element) => {
    Array.from(element.attributes).forEach(({ name, value }) => {
      assert.ok(!/^on/i.test(name), `${label}: event attribute ${name} survived`);
      assert.ok(!['style', 'srcdoc', 'formaction', 'action', 'xlink:href', 'background'].includes(name.toLowerCase()),
        `${label}: attribute ${name} survived`);
      if (['href', 'src', 'cite', 'poster', 'data-file-url'].includes(name)) {
        assert.ok(isSafeUrl(value, { allowDataImage: element.tagName === 'IMG' }), `${label}: unsafe ${name}="${value}"`);
      }
    });
  });
}

const DANGEROUS = {
  'tab inside javascript:': '<a href="java&#x09;script:alert(1)">tab</a>',
  'newline inside javascript:': '<a href="java&#x0A;script:alert(1)">newline</a>',
  'carriage return inside javascript:': '<a href="java&#x0D;script:alert(1)">cr</a>',
  'entity-encoded javascript:': '<a href="&#106;avascript:alert(1)">entity</a>',
  'named entity colon': '<a href="javascript&colon;alert(1)">colon</a>',
  'upper-case JAVASCRIPT:': '<a href="JAVASCRIPT:alert(1)">upper</a>',
  'leading spaces and controls': '<a href="  \u0001javascript:alert(1)">lead</a>',
  'vbscript:': '<a href="vbscript:msgbox(1)">vb</a>',
  'data:text/html link': '<a href="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==">data</a>',
  'base tag': '<base href="https://evil.example/"><p>after base</p>',
  'meta refresh': '<meta http-equiv="refresh" content="0;url=https://evil.example/"><p>x</p>',
  'stylesheet link': '<link rel="stylesheet" href="https://evil.example/x.css"><p>x</p>',
  'style tag': '<style>body{display:none}</style><p>x</p>',
  'svg onload': '<svg onload="alert(1)"><circle r="5"></circle></svg>',
  'svg link with xlink:href': '<svg><a xlink:href="javascript:alert(1)"><text y="20">svg link</text></a></svg>',
  'svg animate sets href': '<svg><a><animate attributeName="href" to="javascript:alert(1)"/><text y="20">x</text></a></svg>',
  'img onerror': '<img src="x" onerror="alert(1)">',
  'img javascript src': '<img src="javascript:alert(1)">',
  'iframe srcdoc': '<iframe srcdoc="<script>alert(1)</script>"></iframe>',
  'iframe src': '<iframe src="https://evil.example/"></iframe>',
  'form with button': '<form action="javascript:alert(1)"><input name="x"><button formaction="javascript:alert(1)">go</button></form>',
  'math link': '<math href="javascript:alert(1)"><mi>x</mi></math>',
  'math mXSS': '<math><mtext><table><mglyph><style><img src=x onerror=alert(1)>',
  'object data': '<object data="javascript:alert(1)"></object>',
  'embed': '<embed src="javascript:alert(1)">',
  'image map area': '<map name="m"><area shape="rect" coords="0,0,9,9" href="javascript:alert(1)"></map>',
  'unclosed script': '<scr<script>ipt>alert(1)</script>',
  'noscript trick': '<noscript><p title="</noscript><img src=x onerror=alert(1)>"></noscript>',
  'template': '<template><img src=x onerror=alert(1)></template>',
  'style attribute': '<p style="background:url(javascript:alert(1))">x</p>',
  'data-file-url javascript': '<a href="#" class="article-inline-file" data-file-url="javascript:alert(1)">f</a>',
  'srcset with javascript': '<img src="/static/a.png" srcset="/static/a.png 1x, javascript:alert(1) 2x">',
  'video poster javascript': '<video poster="javascript:alert(1)" src="javascript:alert(2)"></video>',
  'blockquote cite javascript': '<blockquote cite="javascript:alert(1)">q</blockquote>',
};

for (const [label, input] of Object.entries(DANGEROUS)) {
  test(`neutralised: ${label}`, () => {
    const output = sanitize(input);
    assertNothingExecutable(output, label);
    assert.ok(!/javascript:|vbscript:|data:text\/html/i.test(normaliseUrl(output)), `${label}: ${output}`);
  });
}

test('the tab-split javascript: link keeps its text but has no href', () => {
  const link = parse(sanitize('<a href="java&#x09;script:alert(1)" target="_blank">Click me</a>')).querySelector('a');
  assert.ok(link);
  assert.equal(link.textContent, 'Click me');
  assert.equal(link.hasAttribute('href'), false);
});

test('the same rule also catches the attack after entity decoding (article pages decode first)', () => {
  const output = sanitize('&lt;a href="java&amp;#x09;script:alert(1)"&gt;x&lt;/a&gt;&lt;base href="https://evil.example/"&gt;', { decodeEntities: true });
  assertNothingExecutable(output, 'decoded');
  assert.equal(parse(output).querySelector('a')?.hasAttribute('href'), false);
  assert.equal(parse(output).querySelector('base'), null);
});

test('decoding twice still ends in the sanitizer (no second decode afterwards)', () => {
  const output = sanitize('&amp;lt;img src=x onerror=alert(1)&amp;gt;', { decodeEntities: true });
  // One decode leaves escaped text, which is shown as text, never parsed as a tag.
  assert.equal(parse(output).querySelector('img'), null);
  assert.match(output, /&lt;img/);
});

test('a transform cannot sneak anything past the rules', () => {
  const output = sanitize('<p>x</p>', {
    transform(root, doc) {
      const link = doc.createElement('a');
      link.setAttribute('href', 'java\tscript:alert(1)');
      link.setAttribute('onclick', 'alert(1)');
      link.textContent = 'added';
      root.appendChild(link);
      root.appendChild(doc.createElement('base')).setAttribute('href', 'https://evil.example/');
    },
  });
  assertNothingExecutable(output, 'transform');
  assert.match(output, /added/);
});

test('URL rules: allowed and refused values', () => {
  for (const ok of ['https://example.com/a', 'http://x.y', 'mailto:a@b.c', 'tel:+60123', '/static/uploads/a.png',
    'uploads/articles/a.pdf', '#section-2', '?page=2', '//cdn.example/x.png', './Notes:%20week%201.pdf']) {
    assert.equal(isSafeUrl(ok), true, ok);
  }
  // "Notes:week.pdf" is read by a browser as a URL with the unknown scheme "notes:", so it is refused too.
  for (const bad of ['javascript:alert(1)', 'java\tscript:x', 'java\nscript:x', ' javascript:x', 'JaVaScRiPt:x',
    'vbscript:x', 'data:text/html,x', 'data:image/png;base64,AAAA', 'file:///etc/passwd', 'ftp://x', 'blob:x', '',
    'Notes:%20week%201.pdf']) {
    assert.equal(isSafeUrl(bad), false, JSON.stringify(bad));
  }
  assert.equal(isSafeUrl('data:image/png;base64,AAAA', { allowDataImage: true }), true);
  assert.equal(isSafeUrl('data:image/svg+xml;base64,AAAA', { allowDataImage: true }), false);
  assert.equal(isSafeUrl('data:text/html,x', { allowDataImage: true }), false);
});

// ---------------------------------------------------------------------------------------------------------
// Normal content must survive unchanged (except inline styles, which were already removed before).
// ---------------------------------------------------------------------------------------------------------
test('editor and Notion content keeps its structure', () => {
  const input = [
    '<h1>Kiosk Opening</h1><h2>Before</h2><h3>Steps</h3>',
    '<p><strong>Bold</strong> <b>b</b> <em>em</em> <i>i</i> <u>u</u> <s>s</s> <code>code</code><br>line</p>',
    '<ul><li>one</li><li>two<ol><li>nested</li></ol></li></ul>',
    '<blockquote>quote</blockquote><pre><code>x = 1</code></pre><hr>',
    '<table class="jodit-table"><thead><tr><th colspan="2">Head</th></tr></thead>',
    '<tbody><tr><td rowspan="2">A</td><td>B</td></tr><tr><td>C</td></tr></tbody></table>',
    '<p><a href="https://www.notion.so/abc" target="_blank" rel="noopener noreferrer">Notion page</a></p>',
    '<p><img src="/static/uploads/articles/a.png" width="300" alt="photo"></p>',
  ].join('');
  const output = sanitize(input);
  const root = parse(output);
  assert.equal(root.querySelectorAll('h1, h2, h3, ul, ol, li, blockquote, pre, code, hr, table, thead, tbody, tr, th, td, img, a, strong, b, em, i, u, s, br').length,
    parse(input).querySelectorAll('h1, h2, h3, ul, ol, li, blockquote, pre, code, hr, table, thead, tbody, tr, th, td, img, a, strong, b, em, i, u, s, br').length);
  assert.equal(root.querySelector('th').getAttribute('colspan'), '2');
  assert.equal(root.querySelector('td').getAttribute('rowspan'), '2');
  assert.equal(root.querySelector('table').className, 'jodit-table');
  assert.equal(root.querySelector('img').getAttribute('src'), '/static/uploads/articles/a.png');
  assert.equal(root.querySelector('img').getAttribute('width'), '300');
  assert.equal(root.querySelector('a').getAttribute('href'), 'https://www.notion.so/abc');
  assert.equal(output, input);   // byte for byte: nothing in normal content is touched
});

test('inline file links keep their data attributes and class', () => {
  const input = '<p><a href="#" class="article-inline-file" data-file-url="/static/uploads/articles/r.pdf" ' +
    'data-file-name="Notes: week 1.pdf">📄 Notes <span class="article-inline-file-caret">▾</span></a></p>';
  const link = parse(sanitize(input)).querySelector('a');
  assert.equal(link.getAttribute('href'), '#');
  assert.equal(link.className, 'article-inline-file');
  assert.equal(link.dataset.fileUrl, '/static/uploads/articles/r.pdf');
  assert.equal(link.dataset.fileName, 'Notes: week 1.pdf');
  assert.equal(link.querySelector('span').className, 'article-inline-file-caret');
});

test('other data attributes and inline styles are removed (as before)', () => {
  const root = parse(sanitize('<p style="text-align:center" data-x="1">x</p>'));
  assert.equal(root.querySelector('p').attributes.length, 0);
});

test('links that open a new tab always get rel="noopener noreferrer"', () => {
  const root = parse(sanitize('<a href="https://x.example" target="_blank">a</a><a href="https://x.example" target="_blank" rel="nofollow">b</a><a href="/k" target="_top">c</a>'));
  const [a, b, c] = root.querySelectorAll('a');
  assert.equal(a.getAttribute('rel'), 'noopener noreferrer');
  assert.equal(b.getAttribute('rel'), 'nofollow noopener noreferrer');
  assert.equal(c.hasAttribute('target'), false);
  assert.equal(c.getAttribute('href'), '/k');
});

test('images with an empty or unsafe source are removed; raster data images are kept', () => {
  const root = parse(sanitize('<img src=""><img><img src="javascript:x"><img src="data:image/png;base64,iVBORw0KGgo="><img srcset="/static/a.png 1x">'));
  const images = root.querySelectorAll('img');
  assert.equal(images.length, 2);
  assert.ok(images[0].getAttribute('src').startsWith('data:image/png'));
  assert.equal(images[1].getAttribute('srcset'), '/static/a.png 1x');
});

test('a page transform can still rewrite old static URLs (they are then checked like any URL)', () => {
  const oldHost = 'https://group3jungle-house-production.up.railway.app';
  const rewrite = (url) => (url.startsWith(`${oldHost}/static/`) ? url.slice(oldHost.length) : url);
  const output = sanitize(
    `<img src="${oldHost}/static/uploads/a.png" srcset="${oldHost}/static/uploads/a.png 1x, ${oldHost}/static/uploads/b.png 2x">` +
    `<a href="${oldHost}/static/uploads/r.pdf">file</a><a href="https://example.com/x">external</a>`,
    {
      transform(root) {
        root.querySelectorAll('img[src], a[href]').forEach((element) => {
          const attribute = element.tagName === 'A' ? 'href' : 'src';
          element.setAttribute(attribute, rewrite(element.getAttribute(attribute)));
        });
        root.querySelectorAll('img[srcset]').forEach((element) => {
          element.setAttribute('srcset', rewriteSrcset(element.getAttribute('srcset'), rewrite));
        });
      },
    },
  );
  const root = parse(output);
  assert.equal(root.querySelector('img').getAttribute('src'), '/static/uploads/a.png');
  assert.equal(root.querySelector('img').getAttribute('srcset'), '/static/uploads/a.png 1x, /static/uploads/b.png 2x');
  assert.deepEqual([...root.querySelectorAll('a')].map((a) => a.getAttribute('href')), ['/static/uploads/r.pdf', 'https://example.com/x']);
});

test('plain text and unknown tags keep their text', () => {
  assert.equal(sanitize('Hello & <b>bold</b> < 5'), 'Hello &amp; <b>bold</b> &lt; 5');
  assert.equal(sanitize('<custom-tag>kept text</custom-tag>'), 'kept text');
  assert.equal(sanitize(null), '');
  assert.equal(sanitize(undefined), '');
});

test('the allowlist has no executable or document-level tag and no event or style attribute', () => {
  for (const tag of ['script', 'style', 'link', 'meta', 'base', 'iframe', 'object', 'embed', 'form', 'input', 'svg', 'math']) {
    assert.ok(!ALLOWED_TAGS.includes(tag), tag);
  }
  assert.ok(!ALLOWED_ATTRIBUTES.some((name) => /^on|^style$|^srcdoc$|^formaction$|^action$/.test(name)));
});

test('editor cleaner removes only page-level tags and keeps all authoring HTML', () => {
  const clean = createEditorHtmlCleaner(window);
  const styled = '<p style="text-align: center;">Centred <span style="color: rgb(0, 128, 0);">green</span></p>' +
    '<table style="border-collapse: collapse;"><tbody><tr><td style="width: 50%;">a</td></tr></tbody></table>';
  assert.equal(clean(styled), styled);                       // normal editor content is returned as it is
  const cleaned = clean(`${styled}<base href="https://evil.example/"><meta http-equiv="refresh" content="0;url=https://evil.example/">` +
    '<link rel="stylesheet" href="https://evil.example/x.css"><style>body{display:none}</style><script>alert(1)</script>' +
    '<svg><style>@import "https://evil.example/x.css";</style></svg>');
  assert.equal(parse(cleaned).querySelectorAll('base, meta, link, style, script').length, 0);
  assert.ok(cleaned.startsWith(styled));
  assert.equal(clean(''), '');
  assert.equal(clean(null), '');
});

test('stored content loaded into the editor keeps authoring HTML but loses everything executable', () => {
  const clean = createStoredEditorHtmlCleaner(window);
  const authoring = '<h2>Kiosk</h2><p style="text-align: center;">Centred <span style="color: rgb(0, 128, 0);">green</span> ' +
    '<strong>b</strong> <em>i</em> <u>u</u> <s>s</s></p><ul><li>one</li></ul>' +
    '<table style="border-collapse: collapse; width: 100%;"><tbody><tr><td style="width: 50%;" colspan="2">a</td></tr></tbody></table>' +
    '<p><img src="/static/uploads/articles/a.png" alt="a" style="width: 300px;"></p>' +
    '<p><a href="https://example.com/x" target="_blank" rel="noopener noreferrer">link</a></p>' +
    '<p><a href="#" class="article-inline-file" data-file-url="/static/uploads/articles/r.pdf" data-file-name="r.pdf">r.pdf</a></p>' +
    '<p><input type="checkbox" disabled="" checked=""> Notion to-do</p>';
  const kept = parse(clean(authoring));
  assert.equal(kept.querySelector('p').getAttribute('style'), 'text-align: center;');
  assert.equal(kept.querySelector('span').getAttribute('style'), 'color: rgb(0, 128, 0);');
  assert.equal(kept.querySelector('table').getAttribute('style'), 'border-collapse: collapse; width: 100%;');
  assert.equal(kept.querySelector('td').getAttribute('colspan'), '2');
  assert.equal(kept.querySelector('img').getAttribute('style'), 'width: 300px;');
  assert.equal(kept.querySelector('a[target]').getAttribute('target'), '_blank');
  assert.equal(kept.querySelector('.article-inline-file').dataset.fileUrl, '/static/uploads/articles/r.pdf');
  assert.ok(kept.querySelector('input[type=checkbox][disabled][checked]'));
  assert.equal(kept.innerHTML, parse(authoring).innerHTML);     // nothing an author made is changed

  const dangerous = parse(clean(
    '<img src=x onerror="alert(1)"><a href="java&#x09;script:alert(1)">t</a><a href="javascript:alert(1)">j</a>' +
    '<base href="https://evil.example/"><meta http-equiv="refresh" content="0;url=https://evil.example/">' +
    '<link rel="stylesheet" href="https://evil.example/x.css"><style>body{display:none}</style><script>alert(1)</script>' +
    '<svg onload="alert(1)"></svg><iframe srcdoc="<script>alert(1)</script>"></iframe><p onclick="alert(1)">x</p>'));
  assert.equal(dangerous.querySelectorAll('base, meta, link, style, script, svg, iframe').length, 0);
  dangerous.querySelectorAll('*').forEach((element) => {
    assert.ok(![...element.attributes].some((a) => /^on|^srcdoc$/i.test(a.name)), element.outerHTML);
  });
  dangerous.querySelectorAll('a').forEach((link) => assert.equal(link.hasAttribute('href'), false));
  assert.equal(clean('plain text, no tags'), 'plain text, no tags');
});

test('isHtmlContent matches the old detection', () => {
  assert.equal(isHtmlContent('<p>x</p>'), true);
  assert.equal(isHtmlContent('a < b and c > d'), false);
  assert.equal(isHtmlContent('Step 1: open kiosk'), false);
});
