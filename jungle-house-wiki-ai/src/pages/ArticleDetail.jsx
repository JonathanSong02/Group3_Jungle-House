import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import PageHeader from "../components/PageHeader";

const API_BASE_URL = "https://group3jungle-house-production.up.railway.app";

export default function ArticleDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [article, setArticle] = useState(null);
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(true);

  function getFileUrl(url) {
    if (!url) return "";

    if (url.startsWith("http://") || url.startsWith("https://")) {
      return url;
    }

    if (url.startsWith("/")) {
      return `${API_BASE_URL}${url}`;
    }

    return `${API_BASE_URL}/${url}`;
  }

  function isImageFile(url, type) {
    if (type && type.startsWith("image/")) return true;

    const lowerUrl = String(url || "").toLowerCase();

    return (
      lowerUrl.endsWith(".jpg") ||
      lowerUrl.endsWith(".jpeg") ||
      lowerUrl.endsWith(".png") ||
      lowerUrl.endsWith(".gif") ||
      lowerUrl.endsWith(".webp")
    );
  }

  useEffect(() => {
    setLoading(true);

    fetch(`${API_BASE_URL}/api/articles/${id}`)
      .then((res) => {
        if (!res.ok) {
          throw new Error("Article not found");
        }
        return res.json();
      })
      .then((articleData) => {
        console.log("Article detail data:", articleData);

        if (articleData && articleData.article_id) {
          setArticle(articleData);
        } else {
          setArticle(null);
        }

        return fetch(`${API_BASE_URL}/api/article-links/${id}`);
      })
      .then((res) => {
        if (!res.ok) {
          return [];
        }
        return res.json();
      })
      .then((linksData) => {
        setLinks(Array.isArray(linksData) ? linksData : []);
      })
      .catch((err) => {
        console.error("Failed to load article detail:", err);
        setArticle(null);
        setLinks([]);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [id]);

  // Legacy exact-title link table. Kept ONLY so older plain-text SOP
  // articles that already rely on these exact phrases keep working.
  // New links should NOT be added here — write them straight into the
  // article content instead, either as:
  //   - a raw URL (auto-detected), or
  //   - Markdown-style [Display Text](https://...), or
  //   - a real <a href="..."> link inserted via the editor's Link toolbar
  //     button (for rich/HTML articles).
  function getLegacyLinkMap() {
    return {
      "QWERTYUIOPhhhhhhhhhhh":
        "1",
      
    };
  }

  // Splits a plain text string into a flat list of tokens:
  //   { type: "text", value }  or  { type: "link", href, label }
  //
  // Recognises, in priority order:
  //   1. Markdown-style links:  [Display Text](https://...)
  //   2. Raw URLs:              https://...
  //   3. Legacy exact-title matches (see getLegacyLinkMap above)
  //
  // This is the single source of truth for link detection, used both for
  // legacy plain-text article content and for auto-linking stray URLs
  // inside rich HTML article content.
  function buildLinkTokens(text) {
    const pattern = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|(https?:\/\/\S+)/g;
    const tokens = [];
    let lastIndex = 0;
    let match;

    while ((match = pattern.exec(text)) !== null) {
      if (match.index > lastIndex) {
        tokens.push({ type: "text", value: text.slice(lastIndex, match.index) });
      }

      if (match[1] && match[2]) {
        tokens.push({ type: "link", href: match[2], label: match[1] });
      } else if (match[3]) {
        tokens.push({ type: "link", href: match[3], label: match[3] });
      }

      lastIndex = pattern.lastIndex;
    }

    if (lastIndex < text.length) {
      tokens.push({ type: "text", value: text.slice(lastIndex) });
    }

    // Backward-compat pass: expand remaining plain text using the legacy
    // exact-title map so old SOP articles keep their existing links.
    const legacyLinkMap = getLegacyLinkMap();
    const expanded = [];

    tokens.forEach((token) => {
      if (token.type !== "text") {
        expanded.push(token);
        return;
      }

      let parts = [token.value];

      Object.keys(legacyLinkMap).forEach((label) => {
        parts = parts.flatMap((part) => {
          if (typeof part !== "string" || !part.includes(label)) return part;

          const split = part.split(label);
          const rebuilt = [];

          split.forEach((chunk, i) => {
            if (chunk) rebuilt.push(chunk);

            if (i < split.length - 1) {
              rebuilt.push({ type: "link", href: legacyLinkMap[label], label });
            }
          });

          return rebuilt;
        });
      });

      parts.forEach((part) => {
        if (typeof part === "string") {
          if (part) expanded.push({ type: "text", value: part });
        } else {
          expanded.push(part);
        }
      });
    });

    return expanded;
  }

  // Renders a plain text line as React nodes, turning any detected link
  // tokens into clickable <a> elements.
  function renderLinkedText(line, keyPrefix) {
    return buildLinkTokens(line).map((token, index) =>
      token.type === "link" ? (
        <a
          key={`${keyPrefix}-link-${index}`}
          href={token.href}
          target="_blank"
          rel="noopener noreferrer"
          className="sop-inline-link"
        >
          {token.label}
        </a>
      ) : (
        token.value
      )
    );
  }

  // Walks a parsed HTML fragment and turns any raw URL / markdown-style
  // link found in plain text nodes into a real <a> element. Text that is
  // already inside an <a> tag (e.g. links inserted via the editor's Link
  // toolbar button) is left untouched.
  function autoLinkPlainText(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    let currentNode;

    while ((currentNode = walker.nextNode())) {
      if (currentNode.parentElement && currentNode.parentElement.closest("a")) {
        continue;
      }

      if (currentNode.nodeValue && currentNode.nodeValue.trim()) {
        textNodes.push(currentNode);
      }
    }

    textNodes.forEach((textNode) => {
      const tokens = buildLinkTokens(textNode.nodeValue);

      if (tokens.length === 1 && tokens[0].type === "text") {
        return;
      }

      const fragment = document.createDocumentFragment();

      tokens.forEach((token) => {
        if (token.type === "link") {
          const anchor = document.createElement("a");
          anchor.href = token.href;
          anchor.target = "_blank";
          anchor.rel = "noopener noreferrer";
          anchor.className = "sop-inline-link";
          anchor.textContent = token.label;
          fragment.appendChild(anchor);
        } else if (token.value) {
          fragment.appendChild(document.createTextNode(token.value));
        }
      });

      textNode.replaceWith(fragment);
    });
  }

  const decodeHtmlEntities = (value) => {
    const textarea = document.createElement("textarea");
    textarea.innerHTML = value;
    return textarea.value;
  };

  const sanitizeTableHtml = (html) => {
    const decodedHtml = decodeHtmlEntities(String(html || ""));

    const parser = new DOMParser();
    const documentHtml = parser.parseFromString(
      `<div>${decodedHtml}</div>`,
      "text/html"
    );

    const wrapper = documentHtml.body.firstChild;

    if (!wrapper) return "";

    wrapper
      .querySelectorAll("script, iframe, object, embed, form, input, button")
      .forEach((element) => {
        element.remove();
      });

    wrapper.querySelectorAll("*").forEach((element) => {
      Array.from(element.attributes).forEach((attribute) => {
        const attributeName = attribute.name.toLowerCase();
        const attributeValue = attribute.value.toLowerCase();

        if (
          attributeName.startsWith("on") ||
          attributeName === "style" ||
          attributeValue.includes("javascript:")
        ) {
          element.removeAttribute(attribute.name);
        }
      });
    });

    wrapper.querySelectorAll("table").forEach((table) => {
      table.classList.add("article-data-table");
    });

    autoLinkPlainText(wrapper);

    return wrapper.innerHTML;
  };

  const renderNormalContentLines = (content) => {
    if (!content) return null;

    const lines = content.split("\n");

    return lines.map((line, index) => {
      const trimmedLine = line.trim();

      if (!trimmedLine) return null;

      if (trimmedLine.startsWith("[IMAGE]")) {
        const imgUrl = trimmedLine.replace("[IMAGE]", "").trim();
        const finalImgUrl = getFileUrl(imgUrl);

        return (
          <div key={index} className="sop-image-wrapper">
            <img
              src={finalImgUrl}
              alt="SOP Visual Reference"
              className="sop-image"
              loading="lazy"
              onError={(e) => {
                console.error("Image failed to load:", finalImgUrl);
                e.currentTarget.style.display = "none";
              }}
            />
          </div>
        );
      }

      const formattedLine = renderLinkedText(line, index);

      if (trimmedLine.endsWith(":") && trimmedLine.length < 50) {
        return (
          <h3 key={index} className="sop-section-header">
            {formattedLine}
          </h3>
        );
      }

      if (/^\d+\./.test(trimmedLine)) {
        return (
          <div key={index} className="sop-step-main">
            {formattedLine}
          </div>
        );
      }

      if (
        /^[oA-Z]\./.test(trimmedLine) ||
        trimmedLine.startsWith("o ") ||
        trimmedLine.startsWith(" ")
      ) {
        return (
          <div key={index} className="sop-step-sub">
            {formattedLine}
          </div>
        );
      }

      return (
        <p key={index} className="sop-paragraph">
          {formattedLine}
        </p>
      );
    });
  };

  const renderContent = (content) => {
    if (!content) return null;

    const decodedContent = decodeHtmlEntities(String(content || ""));

    // Articles created/edited with the rich text editor (Jodit) store real
    // HTML (e.g. "<p><img src=...></p>"), not the legacy plain-text format
    // with "[IMAGE]" markers. Render that HTML directly instead of falling
    // through to the line-by-line legacy parser, which just escapes the
    // tags as visible text.
    if (/<\/?[a-z][\s\S]*>/i.test(decodedContent)) {
      return (
        <div
          className="article-rich-content"
          dangerouslySetInnerHTML={{ __html: sanitizeTableHtml(content) }}
        />
      );
    }

    const tableRegex = /(<table[\s\S]*?<\/table>)/gi;
    const contentParts = decodedContent.split(tableRegex);

    return contentParts.map((part, index) => {
      if (!part || !part.trim()) return null;

      const trimmedPart = part.trim().toLowerCase();

      if (trimmedPart.startsWith("<table")) {
        return (
          <div key={`table-${index}`} className="article-table-wrapper">
            <div
              dangerouslySetInnerHTML={{
                __html: sanitizeTableHtml(part),
              }}
            />
          </div>
        );
      }

      return (
        <div key={`content-${index}`}>
          {renderNormalContentLines(part)}
        </div>
      );
    });
  };

  if (loading) {
    return (
      <div className="page-container">
        <p>Loading article...</p>
      </div>
    );
  }

  if (!article) {
    return (
      <div className="page-container">
        <p>Article not found.</p>
      </div>
    );
  }

  const attachmentUrl = getFileUrl(article.attachment_url);
  const attachmentIsImage = isImageFile(
    article.attachment_url,
    article.attachment_type
  );

  return (
    <div>
      <button
        className="back-btn text-link"
        onClick={() => navigate(-1)}
        style={{
          marginBottom: "16px",
          cursor: "pointer",
          background: "none",
          border: "none",
          padding: 0,
        }}
      >
        &larr; Back to Knowledge Base
      </button>

      <PageHeader
        title={article.title}
        subtitle={
          article.sub_category
            ? `${article.category} > ${article.sub_category}`
            : `Category: ${article.category}`
        }
      />

      <div className="card-like article-container">
        <div className="article-content">{renderContent(article.content)}</div>

        {article.attachment_url && (
          <div className="article-attachment-section">
            <h3>Attached File</h3>

            {attachmentIsImage ? (
              <div className="sop-image-wrapper">
                <img
                  src={attachmentUrl}
                  alt="Article attachment"
                  className="sop-image"
                  loading="lazy"
                  onError={(e) => {
                    console.error(
                      "Attachment image failed to load:",
                      attachmentUrl
                    );
                    e.currentTarget.style.display = "none";
                  }}
                />
              </div>
            ) : (
              <a
                href={attachmentUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-link"
              >
                View attached file
              </a>
            )}
          </div>
        )}

        {links.length > 0 && (
          <div className="related-links-section">
            <h3>Related Links</h3>
            <ul>
              {links.map((link) => (
                <li key={link.link_id}>
                  <a
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-link"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}