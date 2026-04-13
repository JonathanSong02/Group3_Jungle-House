import { useMemo, useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import PageHeader from '../components/PageHeader';

const categories = ['All', 'PRODUCT', 'SOP', 'SALES'];

export default function KnowledgeBase() {
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [articles, setArticles] = useState([]);

  // ✅ FETCH DATA
  useEffect(() => {
    fetch('http://127.0.0.1:5000/articles')
      .then((res) => res.json())
      .then((data) => setArticles(data))
      .catch((err) => console.error(err));
  }, []);

  // ✅ FILTER (🔥 IMPORTANT PART FIXED)
  // ✅ FILTER (🔥 FIXED VERSION)
const filteredArticles = useMemo(() => {
  return articles.filter((article) => {

    // 🔥 ONLY SHOW MAIN Opening SOP (hide Kiosk/Aeon/Spring)
    if (article.title === "Opening SOP" && article.sub_category) return false;

    const categoryMatch =
      selectedCategory === 'All' || article.category === selectedCategory;

    const text = `${article.title} ${article.content}`.toLowerCase();
    const searchMatch = text.includes(search.toLowerCase());

    return categoryMatch && searchMatch;
  });
}, [articles, search, selectedCategory]);

  return (
    <div>
      <PageHeader
        title="Knowledge Base"
        subtitle="Browse approved company knowledge by category or search for a specific article."
      />

      <div className="toolbar card-like">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search article title or content"
        />

        <select
          value={selectedCategory}
          onChange={(event) => setSelectedCategory(event.target.value)}
        >
          {categories.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </select>
      </div>

      <div className="cards-grid">
        {filteredArticles.map((article) => (
          <article key={article.article_id} className="card-like article-card">

            <p className="eyebrow">{article.category}</p>

            <h3>{article.title}</h3>

            {/* SHORT CONTENT */}
            <p className="muted">
              {article.content?.slice(0, 80)}...
            </p>

            {/* 🔥 ROUTING FIX */}
            <Link
              className="text-link"
              to={
                article.title === "Opening SOP"
                  ? "/sop-selection"
                  : `/knowledge/${article.article_id}`
              }
            >
              View article details
            </Link>

          </article>
        ))}
      </div>
    </div>
  );
}