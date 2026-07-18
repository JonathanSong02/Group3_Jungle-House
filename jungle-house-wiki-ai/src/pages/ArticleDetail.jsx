import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import PageHeader from "../components/PageHeader";

const API_BASE_URL = "https://group3jungle-house-production.up.railway.app";

export default function ArticleDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [article, setArticle] = useState(null);
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openAttachmentIndex, setOpenAttachmentIndex] = useState(null);
  const contentRef = useRef(null);

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

  function isPdfFile(url, type) {
    if (type && type.includes("pdf")) return true;
    return String(url || "").toLowerCase().endsWith(".pdf");
  }

  function getAttachmentFileName(file) {
    if (file?.name) return file.name;

    const rawName = String(file?.url || "").split("/").pop() || "Attached file";
    // Stored filenames are prefixed with a millisecond timestamp
    // (e.g. "1731999999999_Opening SOP.pdf") to keep them unique on disk.
    return rawName.replace(/^\d+_/, "");
  }

  // Builds the combined, de-duplicated list of every file attached to this
  // article. image_files (JSON array) holds every uploaded file; the legacy
  // attachment_url/attachment_type columns just mirror the first entry, but
  // older articles created before multi-file support only ever populated
  // those two columns, so fall back to them when image_files is empty.
  function getAttachments(currentArticle) {
    if (!currentArticle) return [];

    let files = [];
    const rawImageFiles = currentArticle.image_files;

    if (Array.isArray(rawImageFiles)) {
      files = rawImageFiles;
    } else if (rawImageFiles) {
      try {
        const parsed = JSON.parse(rawImageFiles);
        if (Array.isArray(parsed)) files = parsed;
      } catch (error) {
        console.error("Parse image_files error:", error);
      }
    }

    if (files.length === 0 && currentArticle.attachment_url) {
      files = [{
        url: currentArticle.attachment_url,
        type: currentArticle.attachment_type,
      }];
    }

    return files.filter((file) => file && file.url);
  }

  function toggleAttachmentPreview(index) {
    setOpenAttachmentIndex((prev) => (prev === index ? null : index));
  }

  // Files can be inserted anywhere inside the rich-text content (see
  // AddArticle/EditArticle's "Insert into Content" button), rendered as
  // <a class="article-inline-file"> anchors. Content is rendered via
  // dangerouslySetInnerHTML, so React can't attach click handlers to those
  // anchors directly, and binding a listener per-anchor is fragile -- if the
  // container's innerHTML is ever regenerated the specific anchor nodes get
  // replaced and any listener bound directly to them goes with it. Delegate
  // from the stable container instead, resolving the actual anchor per click.
  useEffect(() => {
    const container = contentRef.current;
    if (!container) return undefined;

    const handleClick = (event) => {
      const anchor = event.target.closest("a.article-inline-file");
      if (!anchor || !container.contains(anchor)) return;

      event.preventDefault();

      const host = anchor.closest("p, div, li") || anchor;
      const existingPreview = host.nextElementSibling;

      if (
        existingPreview &&
        existingPreview.classList.contains("article-inline-file-preview")
      ) {
        existingPreview.remove();
        anchor.classList.remove("is-open");
        return;
      }

      anchor.classList.add("is-open");

      const url = anchor.getAttribute("href") || "";
      const name = anchor.dataset.fileName || url.split("/").pop() || "Attached file";
      const lowerUrl = url.toLowerCase();
      const isImage = /\.(png|jpe?g|gif|webp)$/.test(lowerUrl);
      const isPdf = lowerUrl.endsWith(".pdf");

      const preview = document.createElement("div");
      preview.className = "article-file-preview article-inline-file-preview";

      const header = document.createElement("div");
      header.className = "article-file-preview-header";

      const label = document.createElement("span");
      label.textContent = name;
      header.appendChild(label);

      const closeBtn = document.createElement("button");
      closeBtn.type = "button";
      closeBtn.className = "text-link";
      closeBtn.textContent = "Minimise file preview";
      closeBtn.addEventListener("click", () => {
        preview.remove();
        anchor.classList.remove("is-open");
      });
      header.appendChild(closeBtn);

      preview.appendChild(header);

      if (isImage) {
        const img = document.createElement("img");
        img.src = url;
        img.alt = name;
        img.className = "sop-image";
        img.loading = "lazy";
        preview.appendChild(img);
      } else if (isPdf) {
        const iframe = document.createElement("iframe");
        iframe.src = url;
        iframe.title = name;
        iframe.className = "article-file-preview-frame";
        preview.appendChild(iframe);
      } else {
        const card = document.createElement("div");
        card.className = "article-file-download-card";

        const message = document.createElement("p");
        message.textContent = "This file type can't be previewed here.";
        card.appendChild(message);

        const openLink = document.createElement("a");
        openLink.href = url;
        openLink.target = "_blank";
        openLink.rel = "noopener noreferrer";
        openLink.className = "secondary-btn";
        openLink.textContent = "Open / Download";
        card.appendChild(openLink);

        preview.appendChild(card);
      }

      host.insertAdjacentElement("afterend", preview);
    };

    container.addEventListener("click", handleClick);
    return () => container.removeEventListener("click", handleClick);
  }, [article]);

  useEffect(() => {
    setLoading(true);
    setOpenAttachmentIndex(null);

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

  const attachments = getAttachments(article);

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
        <div className="article-content" ref={contentRef}>
          {renderContent(article.content)}
        </div>

        {attachments.length > 0 && (
          <div className="article-attachment-section">
            <h3>Attachments</h3>

            <ul className="article-attachment-file-list">
              {attachments.map((file, index) => {
                const fileUrl = getFileUrl(file.url);
                const fileName = getAttachmentFileName(file);
                const isImage = isImageFile(file.url, file.type);
                const isPdf = isPdfFile(file.url, file.type);
                const isOpen = openAttachmentIndex === index;

                return (
                  <li key={`${file.url}-${index}`} className="article-attachment-file-item">
                    <button
                      type="button"
                      className="article-attachment-file-link"
                      onClick={() => toggleAttachmentPreview(index)}
                      aria-expanded={isOpen}
                    >
                      <span className="article-attachment-file-icon">
                        {isImage ? "🖼" : "📄"}
                      </span>
                      <span className="article-attachment-file-name">{fileName}</span>
                      <span className="article-attachment-file-caret">
                        {isOpen ? "▲" : "▼"}
                      </span>
                    </button>

                    {isOpen && (
                      <div className="article-file-preview">
                        <div className="article-file-preview-header">
                          <span>{fileName}</span>
                          <button
                            type="button"
                            className="text-link"
                            onClick={() => setOpenAttachmentIndex(null)}
                          >
                            Minimise file preview
                          </button>
                        </div>

                        {isImage && (
                          <div className="sop-image-wrapper">
                            <img
                              src={fileUrl}
                              alt={fileName}
                              className="sop-image"
                              loading="lazy"
                              onError={(e) => {
                                console.error("Attachment image failed to load:", fileUrl);
                                e.currentTarget.style.display = "none";
                              }}
                            />
                          </div>
                        )}

                        {!isImage && isPdf && (
                          <iframe
                            src={fileUrl}
                            title={fileName}
                            className="article-file-preview-frame"
                          />
                        )}

                        {!isImage && !isPdf && (
                          <div className="article-file-download-card">
                            <p>
                              This file type can&apos;t be previewed here.
                            </p>
                            <a
                              href={fileUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="secondary-btn"
                            >
                              Open / Download
                            </a>
                          </div>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
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