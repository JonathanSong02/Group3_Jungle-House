import { useMemo, useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import '../styles/KnowledgeBase.css';

const defaultCategoryOrder = ['SOP', 'PRODUCT', 'SALES', 'FAQ', 'UNCATEGORIZED'];

const categoryIcons = {
  SOP: '📋',
  PRODUCT: '🍯',
  SALES: '🛒',
  FAQ: '❓',
  UNCATEGORIZED: '📁',
};

function normalizeCategory(category) {
  const value = String(category || '').trim().toUpperCase();
  return value || 'UNCATEGORIZED';
}

// Known categories are translated; unknown (database-defined) ones keep their stored name.
function getCategoryInfo(category, tOr) {
  const normalized = normalizeCategory(category);
  const known = Object.prototype.hasOwnProperty.call(categoryIcons, normalized);
  return {
    label: tOr(`kb.cat.${normalized}`, normalized),
    title: tOr(`kb.cat.${normalized}.title`, normalized),
    description: known ? tOr(`kb.cat.${normalized}.desc`, '') : '',
    icon: known ? categoryIcons[normalized] : '📁',
  };
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

  return text;
}

function truncateText(text, maxLength = 120) {
  if (!text) return '';
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
  const { t, tOr } = useLanguage();
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
    const info = getCategoryInfo(article.category, tOr);
    const preview = truncateText(cleanPreview(article.content), isShortcut ? 56 : 78) || t('kb.noPreview');
    return (
      <article key={article.article_id} className="card-like kb-article-card">
        <div className="kb-article-top">
          <span className="kb-mini-icon" aria-hidden="true">{info.icon}</span>
          <span className="kb-article-category">{info.label}</span>
        </div>
        <h3>{article.title || t('kb.untitled')}</h3>
        {!isShortcut && <p className="muted">{preview}</p>}
        <Link className="text-link kb-article-link" to={`/knowledge/${article.article_id}`}>
          {t('kb.readArticle')} <span aria-hidden="true">→</span>
        </Link>
      </article>
    );
  };

  return (
    <div className="kb-page kb-compact-page">
      <PageHeader title={t('kb.title')} subtitle="" />

      <section className="kb-hero card-like" aria-label={t('kb.title')}>
        <div>
          <p className="eyebrow">{t('kb.eyebrowStaff')}</p>
          <h2>{t('kb.cover')}</h2>
        </div>
        {/* The illustrated document and leaf on the right come from the
            theme-aware CSS installed in Step 8B.1; no external image URL. */}
      </section>

      {!loading && !error && categoryOptions.length > 1 && (
        <section className="kb-category-overview" aria-label={t('kb.browseCategories')}>
          {categoryOptions.filter((category) => category !== 'All').map((category) => {
            const info = getCategoryInfo(category, tOr);
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
                  <small>{t('kb.guides', { n: categoryCounts[category] || 0 })}</small>
                </span>
              </button>
            );
          })}
        </section>
      )}

      <div className="kb-toolbar card-like">
        <label className="kb-search-field">
          <span>{t('kb.search')}</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t('kb.searchPlaceholder')}
            aria-label={t('kb.searchLabel')}
          />
        </label>
        <label className="kb-filter-field">
          <span>{t('kb.category')}</span>
          <select
            value={selectedCategory}
            onChange={(event) => setSelectedCategory(event.target.value)}
          >
            {categoryOptions.map((category) => (
              <option key={category} value={category}>
                {category === 'All' ? t('kb.allTopics') : getCategoryInfo(category, tOr).label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && (
        <div className="kb-state-card" aria-live="polite">
          <span className="kb-loading-spinner" aria-hidden="true" />
          <strong>{t('kb.loadingGuides')}</strong>
        </div>
      )}
      {error && (
        <div className="kb-state-card kb-state-error" role="alert">
          <strong>{t('kb.loadFailed')}</strong>
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && (
        <>
          {!hasFilters && currentPage === 1 && quickGuides.length > 0 && (
            <section className="kb-section" aria-label={t('kb.quickAccess')}>
              <div className="kb-section-header">
                <div><h2>{t('kb.quickAccess')}</h2></div>
              </div>
              <div
                className="kb-card-grid"
                style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 250px), 1fr))' }}
              >
                {quickGuides.map((article) => renderArticle(article, true))}
              </div>
            </section>
          )}

          <section className="kb-section" aria-label={t('kb.articleResults')}>
            <div className="kb-section-header" ref={resultsRef}>
              <div>
                <h2>{selectedCategory === 'All' ? t('kb.allGuides') : getCategoryInfo(selectedCategory, tOr).title}</h2>
              </div>
              <span className="role-pill" aria-live="polite">{t('kb.guides', { n: filteredArticles.length })}</span>
            </div>
            {hasFilters && (
              <div className="kb-results-summary">
                <button type="button" className="secondary-btn narrow-btn" onClick={clearFilters}>
                  {t('kb.clearFilters')}
                </button>
              </div>
            )}
            {filteredArticles.length === 0 ? (
              <div className="kb-state-card">
                <h3>{t('kb.noGuides')}</h3>
                <p>{t('kb.noGuidesNote')}</p>
                {hasFilters && <button type="button" className="secondary-btn" onClick={clearFilters}>{t('kb.showAll')}</button>}
              </div>
            ) : (
              <>
                <div className="kb-card-grid">
                  {visibleArticles.map((article) => renderArticle(article))}
                </div>
                <nav className="kb-pagination" aria-label={t('kb.pages')}>
                  <p className="kb-pagination-summary" aria-live="polite">
                    {startIndex + 1}–{Math.min(startIndex + STAFF_PAGE_SIZE, filteredArticles.length)} {t('kb.of')} {filteredArticles.length}
                  </p>
                  {pageCount > 1 && (
                    <div className="kb-pagination-controls">
                      <button type="button" onClick={() => goToPage(currentPage - 1)}
                        disabled={currentPage === 1} aria-label={t('kb.previousPage')}>‹ <span>{t('kb.prev')}</span></button>
                      {pageItems.map((item) => typeof item === 'string' ? (
                        <span className="kb-pagination-ellipsis" aria-hidden="true" key={item}>…</span>
                      ) : (
                        <button type="button" key={item} onClick={() => goToPage(item)}
                          className={item === currentPage ? 'active' : ''}
                          aria-current={item === currentPage ? 'page' : undefined}
                          aria-label={t('kb.page', { n: item })}>{item}</button>
                      ))}
                      <button type="button" onClick={() => goToPage(currentPage + 1)}
                        disabled={currentPage === pageCount} aria-label={t('kb.nextPageLabel')}><span>{t('kb.nextPage')}</span> ›</button>
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
  const { t, tOr } = useLanguage();
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
            t('kb.loadFailedFallback')
        );
      } finally {
        setLoading(false);
      }
    };

    fetchArticles();
    // t is only used for error text; a language change must not refetch articles.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        title={t('kb.title')}
        subtitle={t('kb.subtitle')}
      />

      <section className="kb-hero card-like">
        <div>
          <p className="eyebrow">{t('kb.eyebrowLibrary')}</p>
          <h2>{t('kb.heroTitle')}</h2>
          <p>{t('kb.heroText')}</p>
        </div>

        <div className="kb-hero-stats">
          <div>
            <strong>{articles.length}</strong>
            <span>{t('kb.totalArticles')}</span>
          </div>
          <div>
            <strong>{categoryOptions.length - 1}</strong>
            <span>{t('kb.categories')}</span>
          </div>
        </div>
      </section>

      <section className="kb-category-overview">
        {categoryOptions
          .filter((category) => category !== 'All')
          .map((category) => {
            const info = getCategoryInfo(category, tOr);
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
                  <small>{t('kb.articlesCount', { n: count })}</small>
                  <p>{info.description}</p>
                </span>
              </button>
            );
          })}
      </section>

      <div className="kb-toolbar card-like">
        <label className="kb-search-field">
          <span>{t('kb.searchArticles')}</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t('kb.searchPlaceholder')}
            aria-label={t('kb.searchLabel')}
          />
        </label>

        <label className="kb-filter-field">
          <span>{t('kb.filterCategory')}</span>
          <select
            value={selectedCategory}
            onChange={(event) => setSelectedCategory(event.target.value)}
          >
            {categoryOptions.map((category) => {
              const info = getCategoryInfo(category, tOr);

              return (
                <option key={category} value={category}>
                  {category === 'All' ? t('kb.allTopics') : info.label}
                </option>
              );
            })}
          </select>
        </label>
      </div>

      {loading ? (
        <div className="kb-state-card" aria-live="polite">
          <span className="kb-loading-spinner" aria-hidden="true" />
          <strong>{t('kb.loadingTitle')}</strong>
          <p>{t('kb.loadingNote')}</p>
        </div>
      ) : null}

      {error ? (
        <div className="kb-state-card kb-state-error" role="alert">
          <strong>{t('kb.loadFailed')}</strong>
          <p>{error}</p>
        </div>
      ) : null}

      {!loading && !error ? (
        <>
          <div className="kb-results-summary">
            <div>
              <strong>{filteredArticles.length}</strong>{' '}
              {filteredArticles.length === 1 ? t('kb.articleOne') : t('kb.articleMany')} {t('kb.found')}
              {selectedCategory !== 'All' ? (
                <span> {t('kb.in')} {getCategoryInfo(selectedCategory, tOr).label}</span>
              ) : null}
              {search.trim() ? <span> {t('kb.for')} “{search.trim()}”</span> : null}
            </div>

            {search || selectedCategory !== 'All' ? (
              <button
                type="button"
                className="secondary-btn narrow-btn"
                onClick={clearFilters}
              >
                {t('kb.clearFilters')}
              </button>
            ) : null}
          </div>

          {filteredArticles.length === 0 ? (
            <div className="kb-state-card">
              <span className="kb-empty-icon" aria-hidden="true">⌕</span>
              <h3>{t('kb.noArticles')}</h3>
              <p>{t('kb.noArticlesNote')}</p>
            </div>
          ) : (
            <div className="kb-sections">
              {groupedArticles.map((group) => {
                const info = getCategoryInfo(group.category, tOr);

                return (
                  <section key={group.category} className="kb-section">
                    <div className="kb-section-header">
                      <div>
                        <p className="eyebrow">{info.label}</p>
                        <h2>{info.title}</h2>
                        <p>{info.description}</p>
                      </div>

                      <span className="role-pill">
                        {t('kb.articlesCount', { n: group.articles.length })}
                      </span>
                    </div>

                    <div className="kb-card-grid">
                      {group.articles.map((article) => {
                        const articleCategory = normalizeCategory(
                          article.category
                        );
                        const articleInfo = getCategoryInfo(articleCategory, tOr);
                        const preview = truncateText(
                          cleanPreview(article.content),
                          125
                        ) || t('kb.noPreview');

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
                              {t('kb.viewDetails')} →
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