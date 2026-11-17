// The one place that decides which stored or AI-generated HTML may reach the page.
//
// Article content (editor, Notion Sync), Team Lead answers and AI replies can contain HTML. Every page that
// shows such HTML must pass it through sanitizeHtml() before dangerouslySetInnerHTML. It is an ALLOWLIST:
// only the tags, attributes and URL schemes listed below survive; everything else is removed by DOMPurify
// (a well-tested sanitizer) plus the URL checks in this file.
//
// Pages keep their own small extras (rewriting old static file URLs, table classes, auto-links) through the
// `transform` option. The transform runs BEFORE sanitizing, on an inert copy, so whatever it adds is checked
// by the same rules.

import createDOMPurify from 'dompurify';

// Tags our content uses: editor and Notion output (headings, lists, tables, quotes, code, links, images,
// file links) plus the plain formatting and layout tags that pasted HTML brings. Not here, so removed:
// script, style, link, meta, base, title, iframe, frame, object, embed, form and every form control, svg,
// math, template and anything else.
export const ALLOWED_TAGS = [
  'a', 'abbr', 'article', 'aside', 'audio', 'b', 'big', 'blockquote', 'br', 'caption', 'center', 'cite',
  'code', 'col', 'colgroup', 'dd', 'del', 'details', 'div', 'dl', 'dt', 'em', 'figcaption', 'figure',
  'font', 'footer', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hr', 'i', 'img', 'ins', 'kbd', 'li',
  'mark', 'ol', 'p', 'picture', 'pre', 'q', 's', 'samp', 'section', 'small', 'source', 'span', 'strike',
  'strong', 'sub', 'summary', 'sup', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'tt', 'u',
  'ul', 'video', 'wbr',
];

// Attributes that only describe content or layout. They can never run code or load anything, so their
// values are kept as they are. (style is NOT here: inline styles stay removed, as before.)
const PLAIN_ATTRIBUTES = [
  'abbr', 'align', 'alt', 'bgcolor', 'border', 'cellpadding', 'cellspacing', 'class', 'color', 'colspan',
  'controls', 'data-file-name', 'datetime', 'dir', 'face', 'headers', 'height', 'id', 'lang', 'loading',
  'loop', 'muted', 'open', 'playsinline', 'preload', 'rel', 'reversed', 'rowspan', 'scope', 'size',
  'sizes', 'span', 'start', 'target', 'title', 'type', 'valign', 'value', 'width',
];

// Attributes that hold a URL. Each value must pass isSafeUrl() (srcset: every candidate).
const URL_ATTRIBUTES = ['href', 'src', 'srcset', 'cite', 'poster', 'data-file-url'];

export const ALLOWED_ATTRIBUTES = [...PLAIN_ATTRIBUTES, ...URL_ATTRIBUTES];

const ALLOWED_SCHEMES = new Set(['http', 'https', 'mailto', 'tel']);
const DATA_IMAGE = /^data:image\/(?:png|jpe?g|gif|webp|bmp|avif);/;

// Browsers ignore whitespace and control characters inside a URL scheme ("java<TAB>script:" still runs).
// Remove them all before deciding, so the check sees what the browser will see. Code points instead of a
// regular expression, so no invisible character ever has to be written into this file.
const IGNORED_URL_CODE_POINTS = [
  [0x0000, 0x0020], // control characters and space
  [0x007f, 0x00a0], // DEL, C1 controls, no-break space
  [0x1680, 0x1680], [0x180e, 0x180e], [0x2000, 0x2029], [0x205f, 0x205f], [0x3000, 0x3000], [0xfeff, 0xfeff],
];

function isIgnoredUrlCharacter(character) {
  const code = character.codePointAt(0);
  return IGNORED_URL_CODE_POINTS.some(([from, to]) => code >= from && code <= to);
}

export function normaliseUrl(value) {
  return Array.from(String(value ?? '')).filter((character) => !isIgnoredUrlCharacter(character)).join('');
}

// Allowed: http:, https:, mailto:, tel:, relative paths ("/static/...", "uploads/x.png", "?x"), "#anchors".
// data:image/... only where allowDataImage is set (an <img> source). Everything else, including
// javascript:, vbscript:, data:text/html and unknown schemes, is refused. The value is expected to be
// entity-decoded already (getAttribute() returns it decoded).
export function isSafeUrl(value, { allowDataImage = false } = {}) {
  const url = normaliseUrl(value).toLowerCase();
  if (!url) return false;
  if (allowDataImage && DATA_IMAGE.test(url)) return true;

  const scheme = url.match(/^([a-z][a-z0-9+.-]*):/);
  return scheme ? ALLOWED_SCHEMES.has(scheme[1]) : true;
}

function isSafeSrcset(value, allowDataImage) {
  const candidates = String(value || '').split(',').map((part) => part.trim()).filter(Boolean);
  return candidates.length > 0 &&
    candidates.every((candidate) => isSafeUrl(candidate.split(/\s+/)[0], { allowDataImage }));
}

const NEW_TAB_REL = ['noopener', 'noreferrer'];

const PURIFY_CONFIG = {
  ALLOWED_TAGS,
  ALLOWED_ATTR: ALLOWED_ATTRIBUTES,
  // Plain attributes are not URLs, so DOMPurify must not test them against the URL pattern
  // (a file name such as "Notes: week 1.pdf" would otherwise be dropped).
  ADD_URI_SAFE_ATTR: PLAIN_ATTRIBUTES,
  ALLOW_DATA_ATTR: false,
  ALLOW_UNKNOWN_PROTOCOLS: false,
  // Second line of defence for URL attributes; isSafeUrl() in the hook below is the stricter check.
  ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel):|[^a-z]|[a-z+.-]+(?:[^a-z+.\-:]|$))/i,
  KEEP_CONTENT: true,
};

function addRules(purifier) {
  purifier.addHook('uponSanitizeAttribute', (node, data) => {
    const name = data.attrName;
    const tag = node.nodeName.toLowerCase();
    const allowDataImage = (tag === 'img' || tag === 'source') && (name === 'src' || name === 'srcset');

    if (name === 'srcset') {
      if (!isSafeSrcset(data.attrValue, allowDataImage)) data.keepAttr = false;
    } else if (URL_ATTRIBUTES.includes(name)) {
      if (!isSafeUrl(data.attrValue, { allowDataImage })) data.keepAttr = false;
    } else if (name === 'target') {
      // Only "open in a new tab"; anything else (_top, _parent, a named frame) is dropped.
      if (String(data.attrValue).trim().toLowerCase() !== '_blank') data.keepAttr = false;
      else data.attrValue = '_blank';
    }
  });

  purifier.addHook('afterSanitizeAttributes', (node) => {
    if (node.nodeName === 'A' && node.getAttribute('target') === '_blank') {
      const rel = (node.getAttribute('rel') || '').split(/\s+/).filter(Boolean);
      NEW_TAB_REL.forEach((value) => { if (!rel.includes(value)) rel.push(value); });
      node.setAttribute('rel', rel.join(' '));
    }
  });
}

// One sanitizer per window. Tests pass a jsdom window; the app uses the browser window.
export function createSafeHtml(win) {
  const purifier = createDOMPurify(win);
  if (!purifier.isSupported) {
    throw new Error('HTML sanitizer is not supported in this environment.');
  }
  addRules(purifier);

  // Entity decoding through a <textarea>: its content is plain text, so nothing is created or loaded here.
  // The decoded text is then sanitized like any other input, so decoding can never skip the sanitizer.
  function decodeEntities(value) {
    const textarea = win.document.createElement('textarea');
    textarea.innerHTML = value;
    return textarea.value;
  }

  function sanitize(html, { decodeEntities: decode = false, transform } = {}) {
    let source = String(html ?? '');
    if (decode) source = decodeEntities(source);

    if (typeof transform === 'function') {
      // An inert document: nothing in it runs or loads.
      const parsed = new win.DOMParser().parseFromString('<!doctype html><body></body>', 'text/html');
      const root = parsed.createElement('div');
      root.innerHTML = source;
      transform(root, parsed);
      source = root.innerHTML;
    }

    const fragment = purifier.sanitize(source, { ...PURIFY_CONFIG, RETURN_DOM_FRAGMENT: true });

    // Images without a usable source only show a broken-image icon (Notion sometimes loses the URL, and an
    // unsafe source is removed above).
    fragment.querySelectorAll('img').forEach((image) => {
      if (!image.getAttribute('src') && !image.getAttribute('srcset')) image.remove();
    });

    const container = win.document.createElement('div');
    container.appendChild(fragment);
    return container.innerHTML;
  }

  return { sanitize, decodeEntities };
}

let browserSafeHtml = null;

// Use this in the app. Without a browser window it returns an empty string (fail closed).
export function sanitizeHtml(html, options) {
  if (typeof window === 'undefined' || !window.document) return '';
  browserSafeHtml = browserSafeHtml || createSafeHtml(window);
  return browserSafeHtml.sanitize(html, options);
}

export function decodeHtmlEntities(value) {
  if (typeof window === 'undefined' || !window.document) return String(value ?? '');
  browserSafeHtml = browserSafeHtml || createSafeHtml(window);
  return browserSafeHtml.decodeEntities(String(value ?? ''));
}

// ---------------------------------------------------------------------------------------------------------
// The article editor (Jodit) is the one place that cannot use the allowlist above: authors need the full
// editing HTML (inline styles for alignment, colours and sizes, classes). Jodit itself already removes event
// attributes, javascript: links and iframe srcdoc when content is loaded. What it lets through are tags that
// act on the WHOLE page the moment they are inserted: <base> (moves every relative request, including /api,
// to another site), <meta> (a refresh redirects the editor), <link> and <style> (restyle or load into the
// whole app), and <script>. This removes exactly those. Jodit calls it (cleanHTML.sanitizer) on an inert copy
// before the content goes into the page. Normal content is returned unchanged.
// ---------------------------------------------------------------------------------------------------------
const PAGE_LEVEL_TAGS = 'base, meta, link, style, script';

export function createEditorHtmlCleaner(win) {
  return function removePageLevelTags(html) {
    const value = String(html ?? '');
    if (!/<\s*\/?\s*(base|meta|link|style|script)\b/i.test(value)) return value;   // nothing to remove

    const parsed = new win.DOMParser().parseFromString('<!doctype html><body></body>', 'text/html');
    const root = parsed.createElement('div');
    root.innerHTML = value;
    root.querySelectorAll(PAGE_LEVEL_TAGS).forEach((element) => element.remove());
    return root.innerHTML;
  };
}

let browserEditorCleaner = null;

export function removePageLevelTags(html) {
  if (typeof window === 'undefined' || !window.document) return '';
  browserEditorCleaner = browserEditorCleaner || createEditorHtmlCleaner(window);
  return browserEditorCleaner(html);
}

// Stored content loaded INTO the editor. Jodit writes the first value straight into the page before any of
// its cleaning runs, so stored HTML is cleaned here first. This is DOMPurify's standard HTML allowlist, which
// keeps what authors edit (inline styles, classes, tables, data attributes, links that open a new tab) and
// removes event attributes, javascript: and other script URLs, script, svg and math. Page-level tags
// (base, meta, link, style) are removed as well.
const EDITOR_PURIFY_CONFIG = {
  USE_PROFILES: { html: true },
  ADD_ATTR: ['target'],
  FORBID_TAGS: ['style', 'link', 'meta', 'base'],
  KEEP_CONTENT: true,
};

export function createStoredEditorHtmlCleaner(win) {
  const purifier = createDOMPurify(win);
  if (!purifier.isSupported) {
    throw new Error('HTML sanitizer is not supported in this environment.');
  }
  return (html) => {
    const value = String(html ?? '');
    return value.includes('<') ? purifier.sanitize(value, EDITOR_PURIFY_CONFIG) : value;
  };
}

let browserStoredEditorCleaner = null;

export function cleanStoredEditorHtml(html) {
  if (typeof window === 'undefined' || !window.document) return '';
  browserStoredEditorCleaner = browserStoredEditorCleaner || createStoredEditorHtmlCleaner(window);
  return browserStoredEditorCleaner(html);
}

// "Looks like HTML": the same test the chat and article pages already used.
const HTML_CONTENT_PATTERN = /<\/?[a-z][\s\S]*>/i;

export function isHtmlContent(text) {
  return HTML_CONTENT_PATTERN.test(String(text || ''));
}

// Rewrites a srcset value candidate by candidate (used by the pages' static-URL transforms).
export function rewriteSrcset(value, rewrite) {
  return String(value || '').split(',').map((candidate) => {
    const item = candidate.trim();
    const boundary = item.search(/\s/);
    return boundary < 0 ? rewrite(item) : `${rewrite(item.slice(0, boundary))}${item.slice(boundary)}`;
  }).join(', ');
}
