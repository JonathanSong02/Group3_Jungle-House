import { useMemo, useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import api from '../services/api';

const defaultCategoryOrder = ['SOP', 'PRODUCT', 'SALES', 'FAQ', 'UNCATEGORIZED'];

const categoryDetails = {
  SOP: {
    label: 'SOP',
    title: 'Standard Operating Procedures',
    description: 'Opening, closing, roadshow, backend, and daily operation guides.',
    icon: '📋',
  },
  PRODUCT: {
    label: 'Product',
    title: 'Product Knowledge',
    description: 'Gift guides, product notes, and customer-facing product information.',
    icon: '🍯',
  },
  SALES: {
    label: 'Sales',
    title: 'Sales & Promotions',
    description: 'Promotions, POS guides, sales scripts, and customer handling notes.',
    icon: '🛒',
  },
  FAQ: {
    label: 'FAQ',
    title: 'Frequently Asked Questions',
    description: 'Quick answers for common staff or customer questions.',
    icon: '❓',
  },
  UNCATEGORIZED: {
    label: 'Other',
    title: 'Other Knowledge',
    description: 'Articles that have not been assigned to a main category yet.',
    icon: '📁',
  },
};

function normalizeCategory(category) {
  const value = String(category || '').trim().toUpperCase();
  return value || 'UNCATEGORIZED';
}

function getCategoryInfo(category) {
  const normalized = normalizeCategory(category);
  return (
    categoryDetails[normalized] || {
      label: normalized,
      title: normalized,
      description: 'Company knowledge article.',
      icon: '📁',
    }
  );
}

function cleanPreview(content) {
  const text = String(content || '')
    .replace(/<[^>]*>/g, ' ')
    .replace(/\[IMAGE\]\s*\S+/gi, ' ')
    .replace(/https?:\/\/\S+/gi, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim();

  return text || 'No preview available yet.';
}

function truncateText(text, maxLength = 120) {
  if (!text) return 'No preview available yet.';
  return text.length > maxLength ? `${text.slice(0, maxLength).trim()}...` : text;
}

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

  const categoryOptions = useMemo(() => {
    const foundCategories = Array.from(
      new Set(articles.map((article) => normalizeCategory(article.category)))
    );

    const orderedCategories = [
      ...defaultCategoryOrder.filter((category) =>
        foundCategories.includes(category)
      ),
      ...foundCategories.filter(
        (category) => !defaultCategoryOrder.includes(category)
      ),
    ];

    return ['All', ...orderedCategories];
  }, [articles]);

  const categoryCounts = useMemo(() => {
    return articles.reduce((counts, article) => {
      const category = normalizeCategory(article.category);
      counts[category] = (counts[category] || 0) + 1;
      return counts;
    }, {});
  }, [articles]);

  const filteredArticles = useMemo(() => {
    const keyword = search.trim().toLowerCase();

    return articles.filter((article) => {
      const articleCategory = normalizeCategory(article.category);

      const categoryMatch =
        selectedCategory === 'All' || articleCategory === selectedCategory;

      const searchableText = `${article.title || ''} ${article.content || ''} ${
        article.category || ''
      }`.toLowerCase();

      const searchMatch = !keyword || searchableText.includes(keyword);

      return categoryMatch && searchMatch;
    });
  }, [articles, search, selectedCategory]);

  const groupedArticles = useMemo(() => {
    const groups = filteredArticles.reduce((result, article) => {
      const category = normalizeCategory(article.category);

      if (!result[category]) {
        result[category] = [];
      }

      result[category].push(article);
      return result;
    }, {});

    const groupOrder =
      selectedCategory === 'All'
        ? categoryOptions.filter((category) => category !== 'All')
        : [selectedCategory];

    return groupOrder
      .filter((category) => groups[category]?.length)
      .map((category) => ({
        category,
        articles: groups[category],
      }));
  }, [filteredArticles, categoryOptions, selectedCategory]);

  const clearFilters = () => {
    setSearch('');
    setSelectedCategory('All');
  };

  return (
    <div className="kb-page">
      <PageHeader
        title="Knowledge Base"
        subtitle="Browse approved company knowledge by category or search for a specific article."
      />

      <section className="kb-hero card-like">
        <div>
          <p className="eyebrow">Knowledge Library</p>
          <h2>Find the right guide faster</h2>
          <p>
            Start with a category, then search by article title, keyword, SOP
            name, product name, or sales topic.
          </p>
        </div>

        <div className="kb-hero-stats">
          <div>
            <strong>{articles.length}</strong>
            <span>Total articles</span>
          </div>
          <div>
            <strong>{categoryOptions.length - 1}</strong>
            <span>Categories</span>
          </div>
        </div>
      </section>

      <section className="kb-category-overview">
        {categoryOptions
          .filter((category) => category !== 'All')
          .map((category) => {
            const info = getCategoryInfo(category);
            const count = categoryCounts[category] || 0;

            return (
              <button
                key={category}
                type="button"
                className={`kb-category-card card-like ${
                  selectedCategory === category ? 'active' : ''
                }`}
                onClick={() => setSelectedCategory(category)}
              >
                <span className="kb-category-icon">{info.icon}</span>

                <span className="kb-category-content">
                  <strong>{info.label}</strong>
                  <small>{count} articles</small>
                  <p>{info.description}</p>
                </span>
              </button>
            );
          })}
      </section>

      <div className="kb-toolbar card-like">
        <label className="kb-search-field">
          <span>Search articles</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search article title or content"
          />
        </label>

        <label className="kb-filter-field">
          <span>Filter category</span>
          <select
            value={selectedCategory}
            onChange={(event) => setSelectedCategory(event.target.value)}
          >
            {categoryOptions.map((category) => {
              const info = getCategoryInfo(category);

              return (
                <option key={category} value={category}>
                  {category === 'All' ? 'All categories' : info.label}
                </option>
              );
            })}
          </select>
        </label>
      </div>

      {loading ? (
        <div className="card-like kb-state-card">
          <p className="muted">Loading knowledge base...</p>
        </div>
      ) : null}

      {error ? (
        <div className="card-like kb-state-card danger-soft">
          <p className="error-text">{error}</p>
        </div>
      ) : null}

      {!loading && !error ? (
        <>
          <div className="kb-results-summary">
            <div>
              <strong>{filteredArticles.length}</strong>{' '}
              {filteredArticles.length === 1 ? 'article' : 'articles'} found
              {selectedCategory !== 'All' ? (
                <span> in {getCategoryInfo(selectedCategory).label}</span>
              ) : null}
              {search.trim() ? <span> for “{search.trim()}”</span> : null}
            </div>

            {search || selectedCategory !== 'All' ? (
              <button
                type="button"
                className="secondary-btn narrow-btn"
                onClick={clearFilters}
              >
                Clear filters
              </button>
            ) : null}
          </div>

          {filteredArticles.length === 0 ? (
            <div className="card-like kb-state-card">
              <h3>No articles found</h3>
              <p className="muted">
                Try using a shorter keyword or choose another category.
              </p>
            </div>
          ) : (
            <div className="kb-sections">
              {groupedArticles.map((group) => {
                const info = getCategoryInfo(group.category);

                return (
                  <section key={group.category} className="kb-section">
                    <div className="kb-section-header">
                      <div>
                        <p className="eyebrow">{info.label}</p>
                        <h2>{info.title}</h2>
                        <p>{info.description}</p>
                      </div>

                      <span className="role-pill">
                        {group.articles.length}{' '}
                        {group.articles.length === 1 ? 'article' : 'articles'}
                      </span>
                    </div>

                    <div className="kb-card-grid">
                      {group.articles.map((article) => {
                        const articleCategory = normalizeCategory(
                          article.category
                        );
                        const articleInfo = getCategoryInfo(articleCategory);
                        const preview = truncateText(
                          cleanPreview(article.content),
                          125
                        );

                        return (
                          <article
                            key={article.article_id}
                            className="card-like kb-article-card"
                          >
                            <div className="kb-article-top">
                              <span className="kb-mini-icon">
                                {articleInfo.icon}
                              </span>
                              <span className="kb-article-category">
                                {articleInfo.label}
                              </span>
                            </div>

                            <h3>{article.title}</h3>

                            <p className="muted">{preview}</p>

                            <Link
                              className="text-link kb-article-link"
                              to={`/knowledge/${article.article_id}`}
                            >
                              View article details →
                            </Link>
                          </article>
                        );
                      })}
                    </div>
                  </section>
                );
              })}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}