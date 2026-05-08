import { useMemo, useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import api from '../services/api';

const categories = ['All', 'PRODUCT', 'SOP', 'SALES'];

export default function KnowledgeBase() {
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchArticles = async () => {
      try {
        setLoading(true);
        setError('');

        const response = await api.get('/articles');
        setArticles(Array.isArray(response.data) ? response.data : []);
      } catch (err) {
        console.error('Fetch articles error:', err);
        setError(
          err.response?.data?.message ||
          err.message ||
          'Failed to load knowledge base.'
        );
      } finally {
        setLoading(false);
      }
    };

    fetchArticles();
  }, []);

  const filteredArticles = useMemo(() => {
    return articles.filter((article) => {
      const articleCategory = String(article.category || '').toUpperCase();

      const categoryMatch =
        selectedCategory === 'All' || articleCategory === selectedCategory;

      const text = `${article.title || ''} ${article.content || ''}`.toLowerCase();
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

      {loading ? <p className="muted">Loading knowledge base...</p> : null}
      {error ? <p className="error-text">{error}</p> : null}

      {!loading && !error && filteredArticles.length === 0 ? (
        <p className="muted">No articles found.</p>
      ) : null}

      <div className="cards-grid">
        {filteredArticles.map((article) => (
          <article key={article.article_id} className="card-like article-card">
            <p className="eyebrow">{article.category}</p>
            <h3>{article.title}</h3>

            <p className="muted">
              {article.content?.slice(0, 80)}...
            </p>

            <Link className="text-link" to={`/knowledge/${article.article_id}`}>
              View article details
            </Link>
          </article>
        ))}
      </div>
    </div>
  );
}