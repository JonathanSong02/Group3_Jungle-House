import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../components/PageHeader';
import StatusBadge from '../components/StatusBadge';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function Escalation() {
  const { user } = useAuth();

  const [items, setItems] = useState([]);
  const [answers, setAnswers] = useState({});
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [activeTab, setActiveTab] = useState('pending');
  const [deletingId, setDeletingId] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const fetchEscalations = async () => {
    try {
      setLoading(true);
      const response = await api.get('/escalations');
      const data = Array.isArray(response.data) ? response.data : [];

      setItems(data);

      const answerMap = {};
      data.forEach((item) => {
        answerMap[item.escalation_id] = item.manual_answer || '';
      });
      setAnswers(answerMap);
    } catch (error) {
      console.error('Fetch escalations error:', error);
      setMessage('Failed to load escalations.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEscalations();
  }, []);

  const pendingItems = useMemo(() => {
    return items.filter(
      (item) => item.status === 'pending' || item.status === 'reviewing'
    );
  }, [items]);

  const resolvedItems = useMemo(() => {
    return items.filter((item) => item.status === 'resolved');
  }, [items]);

  const filteredItems = activeTab === 'pending' ? pendingItems : resolvedItems;

  const updateAnswer = (id, value) => {
    setAnswers((prev) => ({
      ...prev,
      [id]: value,
    }));
  };

  const submitAnswer = async (id) => {
    const manualAnswer = answers[id];

    if (!manualAnswer || !manualAnswer.trim()) {
      setMessage('Please write a manual answer before submitting.');
      return;
    }

    try {
      setMessage('');

      await api.put(`/escalations/${id}/answer`, {
        manual_answer: manualAnswer.trim(),
        handled_by: user?.user_id || null,
      });

      setMessage('Manual answer submitted successfully.');
      setActiveTab('resolved');
      fetchEscalations();
    } catch (error) {
      console.error('Submit manual answer error:', error);
      setMessage('Failed to submit manual answer.');
    }
  };

  const openDeleteModal = (item) => {
    setDeleteTarget(item);
  };

  const closeDeleteModal = () => {
    if (deletingId) return;
    setDeleteTarget(null);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;

    const id = deleteTarget.escalation_id;

    try {
      setMessage('');
      setDeletingId(id);

      console.log('Deleting escalation ID:', id);

      const response = await api.delete(`/escalations/${id}`);

      console.log('Delete response:', response.data);

      setItems((prev) =>
        prev.filter((item) => item.escalation_id !== id)
      );

      setAnswers((prev) => {
        const updatedAnswers = { ...prev };
        delete updatedAnswers[id];
        return updatedAnswers;
      });

      setMessage(response.data?.message || 'Escalation deleted successfully.');
      setDeleteTarget(null);

      fetchEscalations();
    } catch (error) {
      console.error('Delete escalation error:', error);

      setMessage(
        error.response?.data?.message ||
        error.response?.data?.error ||
        'Failed to delete escalation.'
      );
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Escalation"
        subtitle="Handle weak AI answers through manual follow-up and review status tracking."
      />

      <section className="card-like top-gap-sm">
        <div className="row-between wrap-gap">
          <div>
            <h3>Escalation Review</h3>
            <p className="muted">
              Pending questions need manual answers. Resolved questions have already been answered.
            </p>
          </div>

          <div className="row-gap">
            <button
              type="button"
              className={activeTab === 'pending' ? 'primary-btn' : 'secondary-btn'}
              onClick={() => setActiveTab('pending')}
            >
              Pending ({pendingItems.length})
            </button>

            <button
              type="button"
              className={activeTab === 'resolved' ? 'primary-btn' : 'secondary-btn'}
              onClick={() => setActiveTab('resolved')}
            >
              Resolved ({resolvedItems.length})
            </button>
          </div>
        </div>
      </section>

      {message && (
        <section className="card-like top-gap-sm">
          <p className="muted">{message}</p>
        </section>
      )}

      {loading ? (
        <section className="card-like top-gap-sm">
          <p className="muted">Loading escalations...</p>
        </section>
      ) : filteredItems.length === 0 ? (
        <section className="card-like top-gap-sm">
          <h3>
            {activeTab === 'pending'
              ? 'No pending escalations'
              : 'No resolved escalations'}
          </h3>
          <p className="muted">
            {activeTab === 'pending'
              ? 'Low-confidence AI questions will appear here for Team Lead or Manager review.'
              : 'Resolved escalation questions will appear here after a manual answer is submitted.'}
          </p>
        </section>
      ) : (
        <div className="stack-gap top-gap-sm">
          {filteredItems.map((item) => (
            <article key={item.escalation_id} className="card-like">
              <div className="row-between wrap-gap">
                <div>
                  <p className="muted small">
                    Asked by {item.asked_by_name || 'Unknown Staff'}
                  </p>
                  <h3>{item.question}</h3>
                </div>

                <div className="row-gap">
                  <StatusBadge status={item.status} />

                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={() => openDeleteModal(item)}
                  >
                    Delete
                  </button>
                </div>
              </div>

              <div className="card-like top-gap-sm">
                <p className="eyebrow">AI Answer</p>
                <p>{item.ai_answer || 'No AI answer recorded.'}</p>
                <p className="muted small">
                  Score: {item.ai_score || 0} | Source: {item.ai_source || 'unknown'}
                </p>
              </div>

              {activeTab === 'pending' ? (
                <>
                  <textarea
                    rows="4"
                    value={answers[item.escalation_id] || ''}
                    onChange={(event) =>
                      updateAnswer(item.escalation_id, event.target.value)
                    }
                    placeholder="Write a manual answer for this escalated question"
                  />

                  <div className="row-between wrap-gap top-gap">
                    <p className="muted small">
                      After submitting, this question will move to the resolved tab.
                    </p>

                    <button
                      className="primary-btn"
                      onClick={() => submitAnswer(item.escalation_id)}
                    >
                      Submit Manual Answer
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="card-like top-gap-sm">
                    <p className="eyebrow">Manual Answer</p>
                    <p>{item.manual_answer || 'No manual answer recorded.'}</p>
                  </div>

                  <p className="muted small top-gap">
                    Resolved at: {item.resolved_at || 'Not recorded'}
                  </p>
                </>
              )}
            </article>
          ))}
        </div>
      )}

      {deleteTarget && (
        <div className="delete-modal-overlay">
          <div className="delete-modal-card">
            <button
              type="button"
              className="delete-modal-close"
              onClick={closeDeleteModal}
              disabled={!!deletingId}
            >
              ×
            </button>

            <div className="delete-modal-icon-wrap">
              <div className="delete-modal-icon">
                <svg
                  width="42"
                  height="42"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M3 6h18" />
                  <path d="M8 6V4h8v2" />
                  <path d="M19 6l-1 14H6L5 6" />
                  <path d="M10 11v6" />
                  <path d="M14 11v6" />
                </svg>
              </div>
            </div>

            <div className="delete-modal-content">
              <h2>Delete this escalation?</h2>
              <p>
                This will permanently remove the selected escalation question from the system.
              </p>

              <div className="delete-modal-question">
                <strong>Question:</strong>{' '}
                {deleteTarget.question || 'Untitled question'}
              </div>

              <div className="delete-modal-actions">
                <button
                  type="button"
                  className="delete-cancel-btn"
                  onClick={closeDeleteModal}
                  disabled={!!deletingId}
                >
                  Cancel
                </button>

                <button
                  type="button"
                  className="delete-confirm-btn"
                  onClick={confirmDelete}
                  disabled={!!deletingId}
                >
                  {deletingId === deleteTarget.escalation_id
                    ? 'Deleting...'
                    : 'Delete'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}