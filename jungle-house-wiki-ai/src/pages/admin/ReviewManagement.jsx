import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import StatusBadge from '../../components/StatusBadge';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';

export default function ReviewManagement() {
  const { user } = useAuth();

  const [activeTab, setActiveTab] = useState('pending');
  const [reviews, setReviews] = useState([]);

  const [searchText, setSearchText] = useState('');
  const [reviewerComment, setReviewerComment] = useState({});

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
      setReviews(response.data || []);
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

  const statusMap = {
    pending: 'Pending',
    approved: 'Approved',
    rejected: 'Rejected',
    published: 'Published',
  };

  const filteredReviews = useMemo(() => {
    return reviews.filter((item) => {
      const matchesTab = activeTab === 'all' || item.status === activeTab;
      const search = searchText.toLowerCase();

      const matchesSearch =
        String(item.question || '').toLowerCase().includes(search) ||
        String(item.answer || '').toLowerCase().includes(search) ||
        String(item.submitted_by_name || '').toLowerCase().includes(search);

      return matchesTab && matchesSearch;
    });
  }, [reviews, activeTab, searchText]);

  const counts = {
    pending: reviews.filter((item) => item.status === 'pending').length,
    approved: reviews.filter((item) => item.status === 'approved').length,
    rejected: reviews.filter((item) => item.status === 'rejected').length,
    published: reviews.filter((item) => item.status === 'published').length,
  };

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

      setSuccess(`Answer ${action}ed successfully.`);
      await fetchReviews();
    } catch (err) {
      console.error('REVIEW ACTION ERROR:', err);
      setError(err.response?.data?.message || `Unable to ${action} answer.`);
    } finally {
      setActionLoadingId(null);
    }
  };

  const renderSummaryCards = () => {
    return (
      <div className="three-column-grid" style={{ marginBottom: '1.5rem' }}>
        <section className="card-like">
          <p className="muted" style={{ marginBottom: '0.3rem' }}>
            Pending Review
          </p>
          <h2 style={{ margin: 0 }}>{counts.pending}</h2>
        </section>

        <section className="card-like">
          <p className="muted" style={{ marginBottom: '0.3rem' }}>
            Approved
          </p>
          <h2 style={{ margin: 0 }}>{counts.approved}</h2>
        </section>

        <section className="card-like">
          <p className="muted" style={{ marginBottom: '0.3rem' }}>
            Published Knowledge
          </p>
          <h2 style={{ margin: 0 }}>{counts.published}</h2>
        </section>
      </div>
    );
  };

  const renderToolbar = () => {
    return (
      <section className="card-like" style={{ marginBottom: '1.5rem' }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            gap: '1rem',
            alignItems: 'end',
          }}
        >
          <div>
            <label className="form-label">Search Review Queue</label>
            <input
              type="text"
              placeholder="Search question, answer, or submitter..."
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
            />
          </div>

          <button
            type="button"
            className="secondary-btn"
            onClick={fetchReviews}
            disabled={loading}
          >
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </section>
    );
  };

  const renderReviewCard = (item) => {
    const isPending = item.status === 'pending';
    const isApproved = item.status === 'approved';
    const isProcessing = actionLoadingId === item.review_id;

    return (
      <article key={item.review_id} className="card-like">
        <div className="row-between wrap-gap">
          <div>
            <p className="eyebrow">Review ID #{item.review_id}</p>
            <h3>{item.question}</h3>
            <p className="muted">
              Submitted by: {item.submitted_by_name || 'Unknown'} · Created: {item.created_at || '-'}
            </p>
          </div>

          <StatusBadge status={statusMap[item.status] || item.status} />
        </div>

        <div style={{ marginTop: '1rem' }}>
          <h4>Manual Answer</h4>
          <p className="muted">{item.answer}</p>
        </div>

        {item.reviewer_comment ? (
          <div style={{ marginTop: '1rem' }}>
            <h4>Reviewer Comment</h4>
            <p className="muted">{item.reviewer_comment}</p>
          </div>
        ) : null}

        {isPending ? (
          <div style={{ marginTop: '1rem' }}>
            <label className="form-label">Reviewer Comment</label>
            <textarea
              rows="3"
              placeholder="Optional comment before approving or rejecting..."
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

        <div className="button-group top-gap">
          {isPending ? (
            <>
              <button
                className="primary-btn"
                onClick={() => handleReviewAction(item.review_id, 'approve')}
                disabled={isProcessing}
              >
                {isProcessing ? 'Processing...' : 'Approve'}
              </button>

              <button
                className="secondary-btn danger-btn"
                onClick={() => handleReviewAction(item.review_id, 'reject')}
                disabled={isProcessing}
              >
                {isProcessing ? 'Processing...' : 'Reject'}
              </button>
            </>
          ) : null}

          {isApproved ? (
            <button
              className="primary-btn"
              onClick={() => handleReviewAction(item.review_id, 'publish')}
              disabled={isProcessing}
            >
              {isProcessing ? 'Publishing...' : 'Publish Approved Knowledge'}
            </button>
          ) : null}
        </div>
      </article>
    );
  };

  return (
    <div>
      <PageHeader
        title="Review Management"
        subtitle="Approve or reject manual answers before publishing them as official knowledge."
      />

      <section className="card-like" style={{ marginBottom: '1.5rem' }}>
        <h3>Review Management Overview</h3>
        <p className="muted">
          This module handles the quality control process for manual answers and knowledge
          contributions. It ensures only reliable and manager-approved content becomes official
          knowledge in the system.
        </p>
      </section>

      {renderSummaryCards()}

      {error ? <p className="error-text">{error}</p> : null}
      {success ? <p style={{ color: '#2f6b3d' }}>{success}</p> : null}

      <div
        className="tab-row"
        style={{
          display: 'flex',
          gap: '0.75rem',
          marginBottom: '1.5rem',
          flexWrap: 'wrap',
        }}
      >
        <button
          type="button"
          className={activeTab === 'pending' ? 'primary-btn' : 'secondary-btn'}
          onClick={() => setActiveTab('pending')}
        >
          Review Manual Answers
        </button>

        <button
          type="button"
          className={activeTab === 'approved' ? 'primary-btn' : 'secondary-btn'}
          onClick={() => setActiveTab('approved')}
        >
          Approve / Reject Answers
        </button>

        <button
          type="button"
          className={activeTab === 'published' ? 'primary-btn' : 'secondary-btn'}
          onClick={() => setActiveTab('published')}
        >
          Published Knowledge
        </button>

        <button
          type="button"
          className={activeTab === 'all' ? 'primary-btn' : 'secondary-btn'}
          onClick={() => setActiveTab('all')}
        >
          All Reviews
        </button>
      </div>

      {renderToolbar()}

      {loading && reviews.length === 0 ? (
        <section className="card-like">
          <p className="muted">Loading review queue...</p>
        </section>
      ) : filteredReviews.length === 0 ? (
        <section className="card-like">
          <p className="muted">No review items found.</p>
        </section>
      ) : (
        <div className="stack-gap">
          {filteredReviews.map((item) => renderReviewCard(item))}
        </div>
      )}
    </div>
  );
}