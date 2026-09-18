import { useMemo, useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import '../styles/KnowledgeBase.css';

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

// Staff-only presentation. The existing fetch, filter, article route and manager
// view below remain unchanged. Cards are sourced exclusively from /articles.
const STAFF_PAGE_SIZE = 6;

function StaffKnowledgeView({
  articles,
  categoryOptions,
  categoryCounts,
  filteredArticles,
  loading,
  error,
  search,
  setSearch,
  selectedCategory,
  setSelectedCategory,
  clearFilters,
}) {
  // Fixed-size numbered pagination: every page replaces the six cards above it.
  // Search/category changes automatically show page 1; admin rendering is untouched.
  const filterKey = `${selectedCategory}\u0000${search}`;
  const [pagination, setPagination] = useState({ key: '', page: 1 });
  const resultsRef = useRef(null);
  const pageCount = Math.max(1, Math.ceil(filteredArticles.length / STAFF_PAGE_SIZE));
  const currentPage = pagination.key === filterKey
    ? Math.min(Math.max(1, pagination.page), pageCount)
    : 1;
  const startIndex = (currentPage - 1) * STAFF_PAGE_SIZE;
  const visibleArticles = filteredArticles.slice(startIndex, startIndex + STAFF_PAGE_SIZE);
  const hasFilters = Boolean(search.trim()) || selectedCategory !== 'All';

  const goToPage = (requestedPage) => {
    const nextPage = Math.min(Math.max(1, requestedPage), pageCount);
    if (nextPage === currentPage) return;
    setPagination({ key: filterKey, page: nextPage });
    // Works whether the scroll owner is the staff content panel or the document.
    requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ block: 'start', behavior: 'auto' }));
  };

  // Keep compact, mobile-friendly pagination even when there are many articles.
  const pageNumbers = Array.from({ length: pageCount }, (_, index) => index + 1)
    .filter((page) => page === 1 || page === pageCount || Math.abs(page - currentPage) <= 1);
  const pageItems = [];
  pageNumbers.forEach((page, index) => {
    if (index > 0 && page - pageNumbers[index - 1] > 1) {
      pageItems.push(`gap-${page}`);
    }
    pageItems.push(page);
  });

  // This is a shortcut to real articles, not an invented popularity ranking.
  // Take one item from each available category before filling remaining spots.
  const quickGuides = useMemo(() => {
    const usable = articles.filter((article) => article.article_id != null);
    const seenCategories = new Set();
    const diverse = usable.filter((article) => {
      const category = normalizeCategory(article.category);
      if (seenCategories.has(category)) return false;
      seenCategories.add(category);
      return true;
    });
    return [...diverse, ...usable.filter((article) => !diverse.includes(article))].slice(0, 3);
  }, [articles]);

  const openCategory = (category) => {
    setSelectedCategory((current) => current === category ? 'All' : category);
  };

  const renderArticle = (article, isShortcut = false) => {
    const info = getCategoryInfo(article.category);
    const preview = truncateText(cleanPreview(article.content), isShortcut ? 56 : 78);
    return (
      <article key={article.article_id} className="card-like kb-article-card">
        <div className="kb-article-top">
          <span className="kb-mini-icon" aria-hidden="true">{info.icon}</span>
          <span className="kb-article-category">{info.label}</span>
        </div>
        <h3>{article.title || 'Untitled article'}</h3>
        {!isShortcut && <p className="muted">{preview}</p>}
        <Link className="text-link kb-article-link" to={`/knowledge/${article.article_id}`}>
          Open guide <span aria-hidden="true">→</span>
        </Link>
      </article>
    );
  };

  return (
    <div className="kb-page kb-compact-page">
      <PageHeader title="Knowledge Base" subtitle="" />

      <section className="kb-hero card-like" aria-label="Knowledge Base cover">
        <div>
          <p className="eyebrow">Jungle House · Knowledge</p>
          <h2>Find. Learn. Grow.</h2>
        </div>
        {/* The illustrated document and leaf on the right come from the
            theme-aware CSS installed in Step 8B.1; no external image URL. */}
      </section>

      {!loading && !error && categoryOptions.length > 1 && (
        <section className="kb-category-overview" aria-label="Browse categories">
          {categoryOptions.filter((category) => category !== 'All').map((category) => {
            const info = getCategoryInfo(category);
            return (
              <button
                key={category}
                type="button"
                className={`kb-category-card card-like ${selectedCategory === category ? 'active' : ''}`}
                onClick={() => openCategory(category)}
                aria-pressed={selectedCategory === category}
              >
                <span className="kb-category-icon" aria-hidden="true">{info.icon}</span>
                <span className="kb-category-content">
                  <strong>{info.label}</strong>
                  <small>{categoryCounts[category] || 0} guides</small>
                </span>
              </button>
            );
          })}
        </section>
      )}

      <div className="kb-toolbar card-like">
        <label className="kb-search-field">
          <span>Search</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search knowledge..."
            aria-label="Search knowledge articles"
          />
        </label>
        <label className="kb-filter-field">
          <span>Category</span>
          <select
            value={selectedCategory}
            onChange={(event) => setSelectedCategory(event.target.value)}
          >
            {categoryOptions.map((category) => (
              <option key={category} value={category}>
                {category === 'All' ? 'All categories' : getCategoryInfo(category).label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && (
        <div className="kb-state-card" aria-live="polite">
          <span className="kb-loading-spinner" aria-hidden="true" />
          <strong>Loading guides…</strong>
        </div>
      )}
      {error && (
        <div className="kb-state-card kb-state-error" role="alert">
          <strong>Unable to load knowledge base</strong>
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && (
        <>
          {!hasFilters && currentPage === 1 && quickGuides.length > 0 && (
            <section className="kb-section" aria-label="Quick access">
              <div className="kb-section-header">
                <div><h2>Quick access</h2></div>
              </div>
              <div
                className="kb-card-grid"
                style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 250px), 1fr))' }}
              >
                {quickGuides.map((article) => renderArticle(article, true))}
              </div>
            </section>
          )}

          <section className="kb-section" aria-label="Article results">
            <div className="kb-section-header" ref={resultsRef}>
              <div>
                <h2>{selectedCategory === 'All' ? 'All guides' : getCategoryInfo(selectedCategory).title}</h2>
              </div>
              <span className="role-pill" aria-live="polite">{filteredArticles.length} guides</span>
            </div>
            {hasFilters && (
              <div className="kb-results-summary">
                <button type="button" className="secondary-btn narrow-btn" onClick={clearFilters}>
                  Clear filters
                </button>
              </div>
            )}
            {filteredArticles.length === 0 ? (
              <div className="kb-state-card">
                <h3>No guides found</h3>
                <p>Try another search or category.</p>
                {hasFilters && <button type="button" className="secondary-btn" onClick={clearFilters}>Show all guides</button>}
              </div>
            ) : (
              <>
                <div className="kb-card-grid">
                  {visibleArticles.map((article) => renderArticle(article))}
                </div>
                <nav className="kb-pagination" aria-label="Knowledge Base pages">
                  <p className="kb-pagination-summary" aria-live="polite">
                    {startIndex + 1}–{Math.min(startIndex + STAFF_PAGE_SIZE, filteredArticles.length)} of {filteredArticles.length}
                  </p>
                  {pageCount > 1 && (
                    <div className="kb-pagination-controls">
                      <button type="button" onClick={() => goToPage(currentPage - 1)}
                        disabled={currentPage === 1} aria-label="Previous page">‹ <span>Prev</span></button>
                      {pageItems.map((item) => typeof item === 'string' ? (
                        <span className="kb-pagination-ellipsis" aria-hidden="true" key={item}>…</span>
                      ) : (
                        <button type="button" key={item} onClick={() => goToPage(item)}
                          className={item === currentPage ? 'active' : ''}
                          aria-current={item === currentPage ? 'page' : undefined}
                          aria-label={`Page ${item}`}>{item}</button>
                      ))}
                      <button type="button" onClick={() => goToPage(currentPage + 1)}
                        disabled={currentPage === pageCount} aria-label="Next page"><span>Next</span> ›</button>
                    </div>
                  )}
                </nav>
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}

export default function KnowledgeBase() {
  const { user } = useAuth();
  const staffMode = String(user?.role || '').trim().toLowerCase() === 'staff';
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

  // Staff see the compact workspace; every other role keeps the original JSX.
  if (staffMode) {
    return (
      <StaffKnowledgeView
        articles={articles}
        categoryOptions={categoryOptions}
        categoryCounts={categoryCounts}
        filteredArticles={filteredArticles}
        loading={loading}
        error={error}
        search={search}
        setSearch={setSearch}
        selectedCategory={selectedCategory}
        setSelectedCategory={setSelectedCategory}
        clearFilters={clearFilters}
      />
    );
  }

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
            aria-label="Search knowledge articles"
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
        <div className="kb-state-card" aria-live="polite">
          <span className="kb-loading-spinner" aria-hidden="true" />
          <strong>Loading knowledge base</strong>
          <p>Preparing approved Jungle House articles...</p>
        </div>
      ) : null}

      {error ? (
        <div className="kb-state-card kb-state-error" role="alert">
          <strong>Unable to load knowledge base</strong>
          <p>{error}</p>
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
            <div className="kb-state-card">
              <span className="kb-empty-icon" aria-hidden="true">⌕</span>
              <h3>No articles found</h3>
              <p>
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