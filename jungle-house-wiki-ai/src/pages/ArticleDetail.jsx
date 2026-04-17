import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import PageHeader from "../components/PageHeader";

export default function ArticleDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [article, setArticle] = useState(null);
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);

    Promise.all([
      fetch(`http://127.0.0.1:5000/api/articles/${id}`).then((res) => res.json()),
      fetch(`http://127.0.0.1:5000/api/article-links/${id}`).then((res) => res.json())
    ])
      .then(([articleData, linksData]) => {
        setArticle(articleData);
        setLinks(Array.isArray(linksData) ? linksData : []);
      })
      .catch((err) => {
        console.error("Failed to load article detail:", err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [id]);

  // Your existing Notion link mapper
  function renderLineWithLinks(line) {
    const linkMap = {
      "Important Notes of Stocktake": "https://junglehouse.notion.site/...",
      "Jerry Can Stocktake Guide": "https://junglehouse.notion.site/...",
      "Furniture Key Labelling": "https://junglehouse.notion.site/...",
      "Credit Card Settlement": "https://junglehouse.notion.site/...",
      "Shopify POS app Closing": "https://junglehouse.notion.site/...",
      "Ice Bin Daily Closing Checklist": "https://junglehouse.notion.site/...",
      "Draining Ice Tong": "https://junglehouse.notion.site/...",
      "Washing Juice Tower": "https://junglehouse.notion.site/...",
      "Shopify POS app Opening": "https://junglehouse.notion.site/...",
      "MBB QR auto Log out": "https://junglehouse.notion.site/...",
      "How to switch on the Digital photo frame?": "https://junglehouse.notion.site/...",
      "Juice Tower Ice Pack": "https://junglehouse.notion.site/...",
      "Charging Juice Tower": "https://junglehouse.notion.site/...",
      "Petty Cash Operation Sop": "https://junglehouse.notion.site/...",
    };

    let elements = [line];

    Object.keys(linkMap).forEach((text) => {
      elements = elements.flatMap((part) => {
        if (typeof part !== "string") return part;
        const split = part.split(text);
        if (split.length === 1) return part;

        const result = [];
        split.forEach((s, i) => {
          result.push(s);
          if (i < split.length - 1) {
            result.push(
              <a
                key={text + i}
                href={linkMap[text]}
                target="_blank"
                rel="noopener noreferrer"
                className="sop-inline-link"
              >
                {text}
              </a>
            );
          }
        });
        return result;
      });
    });

    return elements;
  }

  // Parses URLs that aren't in your Notion map
  function processGenericUrls(elements) {
    const urlRegex = /(https?:\/\/[^\s]+)/g;
    let finalElements = [];

    elements.forEach((el, idx) => {
      if (typeof el !== "string") {
        finalElements.push(el);
        return;
      }

      const parts = el.split(urlRegex);
      parts.forEach((part, i) => {
        if (part.match(urlRegex)) {
          finalElements.push(
            <a key={`url-${idx}-${i}`} href={part} target="_blank" rel="noopener noreferrer" className="sop-inline-link">
              {part}
            </a>
          );
        } else {
          finalElements.push(part);
        }
      });
    });
    return finalElements;
  }

  // 🔥 NEW SMART RENDERER: Applies hierarchy to the text
  const renderContent = (content) => {
    if (!content) return null;
    const lines = content.split("\n");

    return lines.map((line, index) => {
      const trimmedLine = line.trim();
      if (!trimmedLine) return null; // Skip completely empty lines

      // 1. Handle Images
      if (trimmedLine.startsWith("[IMAGE]")) {
        const imgUrl = trimmedLine.replace("[IMAGE]", "").trim();
        return (
          <div key={index} className="sop-image-wrapper">
            <img src={imgUrl} alt="SOP Visual Reference" className="sop-image" loading="lazy" />
          </div>
        );
      }

      // Process links for text lines
      let formattedLine = processGenericUrls(renderLineWithLinks(line));

      // 2. Handle Headers (Lines ending in a colon like "Stocktake:")
      if (trimmedLine.endsWith(":") && trimmedLine.length < 50) {
        return <h3 key={index} className="sop-section-header">{formattedLine}</h3>;
      }

      // 3. Handle Numbered Steps (e.g., "1. Clock in")
      if (/^\d+\./.test(trimmedLine)) {
        return <div key={index} className="sop-step-main">{formattedLine}</div>;
      }

      // 4. Handle Sub-bullets (e.g., "o", "", or lettered "A.")
      if (/^[oA-Z]\./.test(trimmedLine) || trimmedLine.startsWith("o ") || trimmedLine.startsWith(" ")) {
        return <div key={index} className="sop-step-sub">{formattedLine}</div>;
      }

      // 5. Default text
      return <p key={index} className="sop-paragraph">{formattedLine}</p>;
    });
  };

  if (loading) return <div className="page-container"><p>Loading article...</p></div>;
  if (!article) return <div className="page-container"><p>Article not found.</p></div>;

  return (
    <div>
      <button className="back-btn text-link" onClick={() => navigate(-1)} style={{ marginBottom: "16px", cursor: "pointer", background: "none", border: "none", padding: 0 }}>
        &larr; Back to Knowledge Base
      </button>

      <PageHeader
        title={article.title}
        subtitle={article.sub_category ? `${article.category} > ${article.sub_category}` : `Category: ${article.category}`}
      />

      <div className="card-like article-container">
        <div className="article-content">
          {renderContent(article.content)}
        </div>

        {links.length > 0 && (
          <div className="related-links-section">
            <h3>Related Links</h3>
            <ul>
              {links.map((link) => (
                <li key={link.link_id}>
                  <a href={link.url} target="_blank" rel="noopener noreferrer" className="text-link">
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