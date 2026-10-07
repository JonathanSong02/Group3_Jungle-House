import { Fragment, useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useLanguage } from '../../i18n/LanguageContext';
import './styles/ReviewManagement.css';

const TABS = ['pending', 'approved', 'published', 'rejected', 'all'];

const REVIEWS_PER_PAGE = 10;

export default function ReviewManagement() {
  const { user } = useAuth();
  const { t, tOr, locale } = useLanguage();

  const [activeTab, setActiveTab] = useState('pending');
  const [reviews, setReviews] = useState([]);
  const [searchText, setSearchText] = useState('');
  const [reviewerComment, setReviewerComment] = useState({});
  const [expandedReviewId, setExpandedReviewId] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);

  const [loading, setLoading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const fetchReviews = async () => {
    try {
      setLoading(true);
      setError('');
      setSuccess('');

      const response = await api.get('/reviews');
      setReviews(Array.isArray(response.data) ? response.data : []);
    } catch (err) {
      console.error('REVIEW MANAGEMENT ERROR:', err);
      setError(err.response?.data?.message || t('rev.err.load'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReviews();
  }, []);

  const counts = useMemo(
    () => ({
      pending: reviews.filter((item) => item.status === 'pending').length,
      approved: reviews.filter((item) => item.status === 'approved').length,
      published: reviews.filter((item) => item.status === 'published').length,
      rejected: reviews.filter((item) => item.status === 'rejected').length,
      all: reviews.length,
    }),
    [reviews]
  );

  const filteredReviews = useMemo(() => {
    const search = searchText.trim().toLowerCase();

    return reviews
      .filter((item) => {
        const matchesTab = activeTab === 'all' || item.status === activeTab;

        if (!matchesTab) return false;
        if (!search) return true;

        return [
          item.question,
          item.answer,
          item.submitted_by_name,
          item.reviewer_comment,
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(search));
      })
      .sort((a, b) => {
        const aTime = new Date(a.created_at || 0).getTime();
        const bTime = new Date(b.created_at || 0).getTime();

        if (Number.isFinite(aTime) && Number.isFinite(bTime) && aTime !== bTime) {
          return bTime - aTime;
        }

        return Number(b.review_id || 0) - Number(a.review_id || 0);
      });
  }, [reviews, activeTab, searchText]);

  const totalPages = Math.max(1, Math.ceil(filteredReviews.length / REVIEWS_PER_PAGE));

  const paginatedReviews = useMemo(() => {
    const startIndex = (currentPage - 1) * REVIEWS_PER_PAGE;
    return filteredReviews.slice(startIndex, startIndex + REVIEWS_PER_PAGE);
  }, [filteredReviews, currentPage]);

  useEffect(() => {
    setCurrentPage(1);
    setExpandedReviewId(null);
  }, [activeTab, searchText]);

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  const pageNumbers = useMemo(() => {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, index) => index + 1);
    }

    const pages = new Set([1, totalPages, currentPage - 1, currentPage, currentPage + 1]);
    return [...pages]
      .filter((page) => page >= 1 && page <= totalPages)
      .sort((a, b) => a - b);
  }, [currentPage, totalPages]);


  const handleReviewAction = async (reviewId, action) => {
    try {
      setActionLoadingId(reviewId);
      setError('');
      setSuccess('');

      const payload = {
        reviewed_by: user?.id || user?.user_id || null,
        reviewer_comment: reviewerComment[reviewId] || '',
      };

      await api.put(`/reviews/${reviewId}/${action}`, payload);

      if (action === 'approve') setSuccess(t('rev.ok.approve'));
      if (action === 'reject') setSuccess(t('rev.ok.reject'));
      if (action === 'publish') setSuccess(t('rev.ok.publish'));

      setExpandedReviewId(null);
      await fetchReviews();
    } catch (err) {
      console.error('REVIEW ACTION ERROR:', err);
      setError(err.response?.data?.message || t(`rev.err.${action}`));
    } finally {
      setActionLoadingId(null);
    }
  };

  const formatDate = (value) => {
    if (!value) return '-';

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);

    return date.toLocaleDateString(locale, {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  };

  const statusLabel = (status) => {
    return tOr(`status.${status}`, status || t('rev.unknown'));
  };

  const toggleExpanded = (reviewId) => {
    setExpandedReviewId((current) =>
      current === reviewId ? null : reviewId
    );
  };

  return (
    <div className="rm2-page">
      <PageHeader
        title={t('rev.title')}
        subtitle={t('rev.subtitle')}
      />

      <section className="rm2-overview" aria-label={t('rev.overviewAria')}>
        <button
          type="button"
          className={`rm2-stat attention ${activeTab === 'pending' ? 'selected' : ''}`}
          onClick={() => setActiveTab('pending')}
        >
          <span className="rm2-stat-icon pending" aria-hidden="true">!</span>
          <span className="rm2-stat-copy">
            <small>{t('rev.needsReview')}</small>
            <strong>{loading && reviews.length === 0 ? '—' : counts.pending}</strong>
          </span>
          {counts.pending > 0 ? <span className="rm2-attention-dot" aria-hidden="true" /> : null}
        </button>

        <button
          type="button"
          className={`rm2-stat ${activeTab === 'approved' ? 'selected' : ''}`}
          onClick={() => setActiveTab('approved')}
        >
          <span className="rm2-stat-icon approved" aria-hidden="true">✓</span>
          <span className="rm2-stat-copy">
            <small>{t('rev.tab.approved')}</small>
            <strong>{loading && reviews.length === 0 ? '—' : counts.approved}</strong>
          </span>
        </button>

        <button
          type="button"
          className={`rm2-stat ${activeTab === 'published' ? 'selected' : ''}`}
          onClick={() => setActiveTab('published')}
        >
          <span className="rm2-stat-icon published" aria-hidden="true">↗</span>
          <span className="rm2-stat-copy">
            <small>{t('rev.tab.published')}</small>
            <strong>{loading && reviews.length === 0 ? '—' : counts.published}</strong>
          </span>
        </button>

        <button
          type="button"
          className={`rm2-stat ${activeTab === 'rejected' ? 'selected' : ''}`}
          onClick={() => setActiveTab('rejected')}
        >
          <span className="rm2-stat-icon rejected" aria-hidden="true">×</span>
          <span className="rm2-stat-copy">
            <small>{t('rev.tab.rejected')}</small>
            <strong>{loading && reviews.length === 0 ? '—' : counts.rejected}</strong>
          </span>
        </button>
      </section>

      <section className="rm2-shell">
        <div className="rm2-shell-top">
          <nav className="rm2-tabs" aria-label={t('rev.filtersAria')}>
            {TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                className={activeTab === tab ? 'active' : ''}
                onClick={() => {
                  setActiveTab(tab);
                  setError('');
                  setSuccess('');
                }}
              >
                {t(`rev.tab.${tab}`)}
                <span>{counts[tab]}</span>
              </button>
            ))}
          </nav>

          <div className="rm2-tools">
            <label className="rm2-search">
              <span aria-hidden="true">⌕</span>
              <input
                type="search"
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
                placeholder={t('rev.search')}
                aria-label={t('rev.searchAria')}
              />
            </label>

            <button
              type="button"
              className="rm2-refresh"
              onClick={fetchReviews}
              disabled={loading}
            >
              {loading ? t('rev.refreshing') : t('rev.refresh')}
            </button>
          </div>
        </div>

        {error ? <div className="rm2-feedback error" role="alert">{error}</div> : null}
        {success ? <div className="rm2-feedback success" role="status">{success}</div> : null}

        <div className="rm2-section-head">
          <div>
            <div className="rm2-title-line">
              <h2>
                {t(`rev.h.${activeTab}`)}
              </h2>
              <span className={`rm2-count ${activeTab === 'pending' && counts.pending > 0 ? 'attention' : ''}`}>
                {counts[activeTab]}
              </span>
            </div>

            <p>
              {t(`rev.d.${activeTab}`)}
            </p>
          </div>

          {filteredReviews.length > 0 ? (
            <span className="rm2-result-range">
              {t('rev.range', {
                from: ((currentPage - 1) * REVIEWS_PER_PAGE) + 1,
                to: Math.min(currentPage * REVIEWS_PER_PAGE, filteredReviews.length),
                total: filteredReviews.length,
              })}
            </span>
          ) : null}
        </div>

        {loading && reviews.length === 0 ? (
          <div className="rm2-loading" aria-label={t('rev.loadingAria')}>
            <span /><span /><span />
          </div>
        ) : filteredReviews.length === 0 ? (
          <div className="rm2-empty">
            <span className="rm2-empty-icon" aria-hidden="true">✓</span>
            <strong>{t('rev.noReviews')}</strong>
            <p>
              {searchText
                ? t('rev.noMatch')
                : activeTab === 'pending'
                  ? t('rev.noPending')
                  : t('rev.noRecords')}
            </p>
          </div>
        ) : activeTab === 'pending' ? (
          <div className="rm2-review-grid">
            {paginatedReviews.map((item) => {
              const isExpanded = expandedReviewId === item.review_id;
              const isProcessing = actionLoadingId === item.review_id;

              return (
                <article
                  className={`rm2-review-card ${isExpanded ? 'expanded' : ''}`}
                  key={`pending-${item.review_id}`}
                >
                  <div className="rm2-card-top">
                    <span className="rm2-status pending">
                      <i aria-hidden="true" />
                      {t('rev.tab.pending')}
                    </span>
                    <span className="rm2-date">{formatDate(item.created_at)}</span>
                  </div>

                  <div className="rm2-card-question">
                    <span>{t('rev.question')}</span>
                    <h3>{item.question}</h3>
                  </div>

                  <div className="rm2-card-answer">
                    <span>{t('rev.staffAnswer')}</span>
                    <p>{item.answer || t('rev.noAnswer')}</p>
                  </div>

                  <div className="rm2-card-footer">
                    <div className="rm2-submitter">
                      <span className="rm2-avatar" aria-hidden="true">
                        {String(item.submitted_by_name || 'U')
                          .split(' ')
                          .filter(Boolean)
                          .slice(0, 2)
                          .map((part) => part[0]?.toUpperCase())
                          .join('')}
                      </span>
                      <div>
                        <small>{t('rev.submittedBy')}</small>
                        <strong>{item.submitted_by_name || t('rev.unknown')}</strong>
                      </div>
                    </div>

                    <button
                      type="button"
                      className="rm2-details-btn"
                      onClick={() => toggleExpanded(item.review_id)}
                    >
                      {isExpanded ? t('rev.closeDetails') : t('rev.reviewAnswer')}
                      <span aria-hidden="true">{isExpanded ? '↑' : '→'}</span>
                    </button>
                  </div>

                  {isExpanded ? (
                    <div className="rm2-review-panel">
                      <label className="rm2-comment-field" htmlFor={`review-comment-${item.review_id}`}>
                        <span>{t('rev.comment')} <small>{t('rev.optional')}</small></span>
                        <textarea
                          id={`review-comment-${item.review_id}`}
                          rows="3"
                          placeholder={t('rev.commentPh')}
                          value={reviewerComment[item.review_id] || ''}
                          onChange={(event) =>
                            setReviewerComment((prev) => ({
                              ...prev,
                              [item.review_id]: event.target.value,
                            }))
                          }
                        />
                      </label>

                      <div className="rm2-review-actions">
                        <button
                          type="button"
                          className="rm2-btn reject"
                          disabled={isProcessing}
                          onClick={() => handleReviewAction(item.review_id, 'reject')}
                        >
                          {isProcessing ? t('rev.working') : t('rev.reject')}
                        </button>
                        <button
                          type="button"
                          className="rm2-btn approve"
                          disabled={isProcessing}
                          onClick={() => handleReviewAction(item.review_id, 'approve')}
                        >
                          {isProcessing ? t('rev.working') : t('rev.approveAnswer')}
                        </button>
                      </div>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        ) : (
          <div className="rm2-table-wrap">
            <table className="rm2-table">
              <thead>
                <tr>
                  <th>{t('rev.question')}</th>
                  <th>{t('rev.col.submittedBy')}</th>
                  <th>{t('rev.col.status')}</th>
                  <th>{t('rev.col.date')}</th>
                  <th className="rm2-action-col">{t('rev.col.action')}</th>
                </tr>
              </thead>

              <tbody>
                {paginatedReviews.map((item) => {
                  const isExpanded = expandedReviewId === item.review_id;
                  const isApproved = item.status === 'approved';
                  const isProcessing = actionLoadingId === item.review_id;

                  return (
                    <Fragment key={`review-${item.review_id}`}>
                      <tr>
                        <td>
                          <div className="rm2-question-cell">
                            <strong>{item.question}</strong>
                            <span>{item.answer || t('rev.noAnswer')}</span>
                          </div>
                        </td>

                        <td>
                          <span className="rm2-submitter-name">
                            {item.submitted_by_name || t('rev.unknown')}
                          </span>
                        </td>

                        <td>
                          <span className={`rm2-status ${item.status || 'unknown'}`}>
                            <i aria-hidden="true" />
                            {statusLabel(item.status)}
                          </span>
                        </td>

                        <td>
                          <span className="rm2-date">{formatDate(item.created_at)}</span>
                        </td>

                        <td className="rm2-action-col">
                          <button
                            type="button"
                            className="rm2-details-btn compact"
                            onClick={() => toggleExpanded(item.review_id)}
                          >
                            {isExpanded ? t('rev.close') : t('rev.view')}
                          </button>
                        </td>
                      </tr>

                      {isExpanded ? (
                        <tr key={`detail-${item.review_id}`} className="rm2-detail-row">
                          <td colSpan="5">
                            <div className="rm2-detail-panel">
                              <div className="rm2-detail-grid">
                                <div>
                                  <span className="rm2-detail-label">{t('rev.question')}</span>
                                  <p>{item.question}</p>
                                </div>
                                <div>
                                  <span className="rm2-detail-label">{t('rev.answer')}</span>
                                  <p>{item.answer || t('rev.noAnswer')}</p>
                                </div>
                              </div>

                              {item.reviewer_comment ? (
                                <div className="rm2-existing-comment">
                                  <span className="rm2-detail-label">{t('rev.comment')}</span>
                                  <p>{item.reviewer_comment}</p>
                                </div>
                              ) : null}

                              {isApproved ? (
                                <div className="rm2-detail-actions">
                                  <button
                                    type="button"
                                    className="rm2-btn publish"
                                    disabled={isProcessing}
                                    onClick={() => handleReviewAction(item.review_id, 'publish')}
                                  >
                                    {isProcessing ? t('rev.publishing') : t('rev.publish')}
                                  </button>
                                </div>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {filteredReviews.length > REVIEWS_PER_PAGE ? (
          <nav className="rm2-pagination" aria-label={t('rev.pagesAria')}>
            <button
              type="button"
              className="rm2-page-arrow"
              onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
              disabled={currentPage === 1}
              aria-label={t('rev.prevPage')}
            >
              ‹
            </button>

            <div className="rm2-page-numbers">
              {pageNumbers.map((page, index) => {
                const previousPage = pageNumbers[index - 1];
                const showGap = index > 0 && page - previousPage > 1;

                return (
                  <Fragment key={`page-${page}`}>
                    {showGap ? <span className="rm2-page-gap">…</span> : null}
                    <button
                      type="button"
                      className={currentPage === page ? 'active' : ''}
                      onClick={() => setCurrentPage(page)}
                      aria-current={currentPage === page ? 'page' : undefined}
                    >
                      {page}
                    </button>
                  </Fragment>
                );
              })}
            </div>

            <button
              type="button"
              className="rm2-page-arrow"
              onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
              disabled={currentPage === totalPages}
              aria-label={t('rev.nextPage')}
            >
              ›
            </button>
          </nav>
        ) : null}
      </section>
    </div>
  );
}
