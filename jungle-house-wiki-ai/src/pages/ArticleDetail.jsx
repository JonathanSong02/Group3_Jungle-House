import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import PageHeader from "../components/PageHeader";

export default function ArticleDetail() {
  const { id } = useParams();
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

  function renderLineWithLinks(line) {
    const linkMap = {
      "Important Notes of Stocktake":
        "https://junglehouse.notion.site/Important-Notes-of-Stocktake-265379015087802c8f57d8b3056d24a8",
      "Jerry Can Stocktake Guide":
        "https://junglehouse.notion.site/Jerry-Can-Stocktake-Guide-32737901508780a1a2abee94f095a6c7",
      "Furniture Key Labelling":
        "https://junglehouse.notion.site/Furniture-Key-Labelling-2ad37901508780c4ad6acac38c7d3e50/",
      "Credit Card Settlement":
        "https://junglehouse.notion.site/Credit-Card-Settlement-26537901508780c892f3e5c5ff85a478",
      "Shopify POS app Closing":
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
                style={{ color: "#7b8f6a", fontWeight: "600" }}
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

  if (loading) return <p>Loading...</p>;
  if (!article) return <p>Article not found.</p>;

  return (
    <div>
      <PageHeader
        title={article.title}
        subtitle={`Category: ${article.category}`}
      />

      <div className="card-like" style={{ padding: "20px" }}>
        <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit" }}>
          {article.content?.split("\n").map((line, index) => {
            if (line.trim().startsWith("[IMAGE]")) {
              const imgUrl = line.trim().replace("[IMAGE]", "").trim();

              return (
                <div key={index} style={{ margin: "15px 0" }}>
                  <img
                    src={imgUrl}
                    alt="SOP"
                    style={{ maxWidth: "100%", width: "400px", borderRadius: "10px" }}
                  />
                </div>
              );
            }

            const urlRegex = /(https?:\/\/[^\s]+)/g;
            let elements = renderLineWithLinks(line);
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
                    <a
                      key={`${idx}-${i}`}
                      href={part}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "#7b8f6a", fontWeight: "600" }}
                    >
                      {part}
                    </a>
                  );
                } else {
                  finalElements.push(part);
                }
              });
            });

            return (
              <span key={index}>
                {finalElements}
                {"\n"}
              </span>
            );
          })}
        </pre>

        {links.length > 0 && (
          <div style={{ marginTop: "24px" }}>
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