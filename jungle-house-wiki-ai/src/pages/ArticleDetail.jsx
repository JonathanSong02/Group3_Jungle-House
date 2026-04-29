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

  fetch(`http://127.0.0.1:5000/api/articles/${id}`)
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

      return fetch(`http://127.0.0.1:5000/api/article-links/${id}`);
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

  // Your existing Notion link mapper
  function renderLineWithLinks(line) {
    const linkMap = {
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
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
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
      "Jerry Can Stocktake Guide":
        "https://junglehouse.notion.site/Jerry-Can-Stocktake-Guide-32737901508780a1a2abee94f095a6c7",
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
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",

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