import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import './styles/ReviewManagement.css';

const TABS = [
  { key: 'pending', label: 'Pending' },
  { key: 'approved', label: 'Approved' },
  { key: 'published', label: 'Published' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'all', label: 'All' },
];

export default function ReviewManagement() {
  const { user } = useAuth();

  const [activeTab, setActiveTab] = useState('pending');
  const [reviews, setReviews] = useState([]);
  const [searchText, setSearchText] = useState('');
  const [reviewerComment, setReviewerComment] = useState({});
  const [expandedReviewId, setExpandedReviewId] = useState(null);

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
      setError(err.response?.data?.message || 'Unable to load review queue.');
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

    return reviews.filter((item) => {
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
    });
  }, [reviews, activeTab, searchText]);

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

      if (action === 'approve') setSuccess('Answer approved.');
      if (action === 'reject') setSuccess('Answer rejected.');
      if (action === 'publish') setSuccess('Knowledge published.');

      setExpandedReviewId(null);
      await fetchReviews();
    } catch (err) {
      console.error('REVIEW ACTION ERROR:', err);
      setError(err.response?.data?.message || `Unable to ${action} answer.`);
    } finally {
      setActionLoadingId(null);
    }
  };

  const formatDate = (value) => {
    if (!value) return '-';

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);

    return date.toLocaleDateString(undefined, {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  };

  const statusLabel = (status) => {
    if (status === 'pending') return 'Pending';
    if (status === 'approved') return 'Approved';
    if (status === 'published') return 'Published';
    if (status === 'rejected') return 'Rejected';
    return status || 'Unknown';
  };

  const toggleExpanded = (reviewId) => {
    setExpandedReviewId((current) =>
      current === reviewId ? null : reviewId
    );
  };

  return (
    <div className="rm-page">
      <PageHeader
        title="Review Management"
        subtitle="Review and publish staff answers."
      />

      <section className="rm-summary-grid" aria-label="Review overview">
        <button
          type="button"
          className={`rm-summary-card ${activeTab === 'pending' ? 'active' : ''}`}
          onClick={() => setActiveTab('pending')}
        >
          <span>Pending</span>
          <strong>{counts.pending}</strong>
        </button>

        <button
          type="button"
          className={`rm-summary-card ${activeTab === 'approved' ? 'active' : ''}`}
          onClick={() => setActiveTab('approved')}
        >
          <span>Approved</span>
          <strong>{counts.approved}</strong>
        </button>

        <button
          type="button"
          className={`rm-summary-card ${activeTab === 'published' ? 'active' : ''}`}
          onClick={() => setActiveTab('published')}
        >
          <span>Published</span>
          <strong>{counts.published}</strong>
        </button>

        <button
          type="button"
          className={`rm-summary-card ${activeTab === 'rejected' ? 'active' : ''}`}
          onClick={() => setActiveTab('rejected')}
        >
          <span>Rejected</span>
          <strong>{counts.rejected}</strong>
        </button>
      </section>

      <section className="rm-workspace">
        <div className="rm-workspace-head">
          <div className="rm-tabs">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                className={activeTab === tab.key ? 'active' : ''}
                onClick={() => setActiveTab(tab.key)}
              >
                {tab.label}
                <span>{counts[tab.key]}</span>
              </button>
            ))}
          </div>

          <div className="rm-tools">
            <input
              type="search"
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="Search reviews"
              aria-label="Search reviews"
            />

            <button
              type="button"
              className="rm-btn secondary"
              onClick={fetchReviews}
              disabled={loading}
            >
              {loading ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>
        </div>

        {error ? <div className="rm-feedback error">{error}</div> : null}
        {success ? <div className="rm-feedback success">{success}</div> : null}

        {loading && reviews.length === 0 ? (
          <div className="rm-empty-state">
            <strong>Loading reviews...</strong>
          </div>
        ) : filteredReviews.length === 0 ? (
          <div className="rm-empty-state">
            <strong>No reviews found</strong>
            <span>Try another tab or search.</span>
          </div>
        ) : (
          <div className="rm-table-wrap">
            <table className="rm-table">
              <thead>
                <tr>
                  <th>Question</th>
                  <th>Submitted By</th>
                  <th>Status</th>
                  <th>Date</th>
                  <th className="rm-action-col">Action</th>
                </tr>
              </thead>

              <tbody>
                {filteredReviews.map((item) => {
                  const isExpanded = expandedReviewId === item.review_id;
                  const isPending = item.status === 'pending';
                  const isApproved = item.status === 'approved';
                  const isProcessing = actionLoadingId === item.review_id;

                  return (
                    <>
                      <tr key={`row-${item.review_id}`}>
                        <td>
                          <div className="rm-question-cell">
                            <strong>{item.question}</strong>
                            <span>{item.answer || 'No answer provided'}</span>
                          </div>
                        </td>

                        <td>
                          <span className="rm-submitter">
                            {item.submitted_by_name || 'Unknown'}
                          </span>
                        </td>

                        <td>
                          <span className={`rm-status ${item.status || 'unknown'}`}>
                            <i />
                            {statusLabel(item.status)}
                          </span>
                        </td>

                        <td>
                          <span className="rm-date">
                            {formatDate(item.created_at)}
                          </span>
                        </td>

                        <td>
                          <button
                            type="button"
                            className="rm-btn secondary"
                            onClick={() => toggleExpanded(item.review_id)}
                          >
                            {isExpanded ? 'Close' : 'Review'}
                          </button>
                        </td>
                      </tr>

                      {isExpanded ? (
                        <tr key={`detail-${item.review_id}`} className="rm-detail-row">
                          <td colSpan="5">
                            <div className="rm-detail-panel">
                              <div className="rm-detail-section">
                                <span className="rm-detail-label">Question</span>
                                <p>{item.question}</p>
                              </div>

                              <div className="rm-detail-section">
                                <span className="rm-detail-label">Answer</span>
                                <p>{item.answer || 'No answer provided.'}</p>
                              </div>

                              {item.reviewer_comment ? (
                                <div className="rm-detail-section">
                                  <span className="rm-detail-label">
                                    Reviewer Comment
                                  </span>
                                  <p>{item.reviewer_comment}</p>
                                </div>
                              ) : null}

                              {isPending ? (
                                <div className="rm-comment-box">
                                  <label htmlFor={`review-comment-${item.review_id}`}>
                                    Comment
                                  </label>

                                  <textarea
                                    id={`review-comment-${item.review_id}`}
                                    rows="3"
                                    placeholder="Optional reviewer comment"
                                    value={reviewerComment[item.review_id] || ''}
                                    onChange={(event) =>
                                      setReviewerComment((prev) => ({
                                        ...prev,
                                        [item.review_id]: event.target.value,
                                      }))
                                    }
                                  />
                                </div>
                              ) : null}

                              <div className="rm-detail-actions">
                                {isPending ? (
                                  <>
                                    <button
                                      type="button"
                                      className="rm-btn primary"
                                      disabled={isProcessing}
                                      onClick={() =>
                                        handleReviewAction(
                                          item.review_id,
                                          'approve'
                                        )
                                      }
                                    >
                                      {isProcessing ? 'Working...' : 'Approve'}
                                    </button>

                                    <button
                                      type="button"
                                      className="rm-btn danger"
                                      disabled={isProcessing}
                                      onClick={() =>
                                        handleReviewAction(
                                          item.review_id,
                                          'reject'
                                        )
                                      }
                                    >
                                      {isProcessing ? 'Working...' : 'Reject'}
                                    </button>
                                  </>
                                ) : null}

                                {isApproved ? (
                                  <button
                                    type="button"
                                    className="rm-btn primary"
                                    disabled={isProcessing}
                                    onClick={() =>
                                      handleReviewAction(
                                        item.review_id,
                                        'publish'
                                      )
                                    }
                                  >
                                    {isProcessing ? 'Publishing...' : 'Publish'}
                                  </button>
                                ) : null}
                              </div>
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
