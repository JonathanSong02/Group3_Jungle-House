import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

export default function SOPSelection() {
  const [articles, setArticles] = useState([]);

  useEffect(() => {
    fetch("http://127.0.0.1:5000/articles")
      .then(res => res.json())
      .then(data => {
        // filter ONLY Opening SOP
        const filtered = data.filter(
          item => item.title === "Opening SOP"
        );
        setArticles(filtered);
      });
  }, []);

  return (
    <div>
      <h2>Opening SOP Selection</h2>

      {articles.map((item) => (
        <div key={item.article_id} style={{ margin: "10px 0" }}>
          <Link to={`/knowledge/${item.article_id}`}>
            {item.sub_category}
          </Link>
        </div>
      ))}
    </div>
  );
}