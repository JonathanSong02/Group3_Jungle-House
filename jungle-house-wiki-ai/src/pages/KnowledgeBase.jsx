import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import { articles } from '../data/mockData';

const categories = ['All', 'Product', 'SOP', 'Sales', 'Training'];

export default function KnowledgeBase() {
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');

  const filteredArticles = useMemo(() => {
    return articles.filter((article) => {
      const categoryMatch =
        selectedCategory === 'All' || article.category === selectedCategory;
      const text = `${article.title} ${article.summary} ${article.body}`.toLowerCase();
      const searchMatch = text.includes(search.toLowerCase());
      return categoryMatch && searchMatch;
    });
  }, [search, selectedCategory]);

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
          <article key={article.id} className="card-like article-card">
            <p className="eyebrow">{article.category}</p>
            <h3>{article.title}</h3>
            <p className="muted">{article.summary}</p>
            <Link className="text-link" to={`/knowledge/${article.id}`}>
              View article details
            </Link>
          </article>
        ))}
      </div>
    </div>
  );
}
