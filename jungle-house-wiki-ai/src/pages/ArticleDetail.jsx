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
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Jerry Can Stocktake Guide":
        "https://junglehouse.notion.site/Jerry-Can-Stocktake-Guide-32737901508780a1a2abee94f095a6c7",
      "Furniture Key Labelling":
        "https://junglehouse.notion.site/Furniture-Key-Labelling-2ad37901508780c4ad6acac38c7d3e50",
      "Sales Report":
        "https://junglehouse.notion.site/Sales-Report-26d37901508780359c96c90c3fd56230",
      "Credit Card Settlement":
        "https://junglehouse.notion.site/Credit-Card-Settlement-26537901508780c892f3e5c5ff85a478",
      "Shopify POS app Closing":
        "https://junglehouse.notion.site/Shopify-POS-app-Closing-2653790150878088af62e7845afae3a9",
      "Updated Daily Sales Report":
        "https://junglehouse.notion.site/Updated-Daily-Sales-Report-319379015087809fb1c0ceb2d31b0f3b",
      "Ice Bin Daily Closing Checklist":
        "https://junglehouse.notion.site/Ice-Bin-Daily-Closing-Checklist-2d9379015087803a80dbea2c5a6e7543",
      "Draining Ice Tong":
        "https://junglehouse.notion.site/Draining-Ice-Tong-2ed37901508780c494bbe42302327644",
      "Washing Juice Tower":
        "https://junglehouse.notion.site/Washing-Juice-Tower-314379015087803594c2f62dfdb84a0c",
      "Shopify POS app Opening":
        "https://junglehouse.notion.site/Shopify-POS-app-Opening-23c37901508780bf8cdfc0d7b2d60535",
      "MBB QR auto Log out":
        "https://junglehouse.notion.site/MBB-QR-auto-Log-out-203379015087802297fac9b35423b65c",
      "How to switch on the Digital photo frame?":
        "https://junglehouse.notion.site/How-to-switch-on-the-Digital-photo-frame-20f37901508780adb845c1368aee23c2",
      "Juice Tower Ice Pack":
        "https://junglehouse.notion.site/Juice-Tower-Ice-Pack-302379015087802c89cecc918bcf05f0",
      "Charging Juice Tower":
        "https://junglehouse.notion.site/Charging-Juice-Tower-3043790150878060aab4fd81aa6c85e8",
      "Petty Cash Operation Sop":
        "https://junglehouse.notion.site/Petty-Cash-Operation-Sop-2fe37901508780fe8ffefbb30d2b9bf7",
      "Opening Notes":
        "https://junglehouse.notion.site/Opening-Notes-29f379015087801cb872d7f39f7ae7d6",
      "Soak cloth":
        "https://junglehouse.notion.site/Soak-cloth-266379015087802ea541d734394e0dd7",
      "DailySales Report":
        "https://junglehouse.notion.site/Daily-Sales-Report-2653790150878036b52aef4adb9cda98",
      "How to keep Credit card receipt & settlement slip?":
        "https://junglehouse.notion.site/How-to-keep-Credit-card-receipt-settlement-slip-1db3790150878090aafce483a59cfc08",
      "What to close every night? (Booth)":
        "https://junglehouse.notion.site/What-to-close-every-night-Booth-23f37901508780548350c9b5ee2e9f66",
      "How to lock the chiller?":
        "https://junglehouse.notion.site/How-to-lock-the-chiller-2403790150878044ada8d41aa70a82b3",
      "Kuching Booth Closing dustbin check list":
        "https://junglehouse.notion.site/Kuching-Booth-Closing-dustbin-check-list-264379015087801ab6c8fc2f17230ad9",
      "Cover Fabric":
        "https://junglehouse.notion.site/Cover-Fabric-2833790150878044848fcd6f14c40519",
      "What to on every morning?":
        "https://junglehouse.notion.site/What-to-on-every-morning-28237901508780f383d4cc1bb8f8fd88",
      "Proper way to replace rubbish bag":
        "https://junglehouse.notion.site/Proper-way-to-replace-rubbish-bag-26337901508780c1b80acaf8f6829005",
      "Receipt printer preparation for opening":
        "https://junglehouse.notion.site/Receipt-printer-preparation-for-opening-23c37901508780d2a6bbe128d6cb8b0a",
      " Gift & Compensation System (Lark Tutorial)":
        "https://junglehouse.notion.site/Gift-Compensation-System-Lark-Tutorial-33d37901508780c5be74d62a068ddc35",
      "How to Handle Unhappy Customers Like a Pro":
        "https://junglehouse.notion.site/How-to-Handle-Unhappy-Customers-Like-a-Pro-2b737901508780a58078f8968fc429d3",
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