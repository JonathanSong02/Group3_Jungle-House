import { useEffect, useState } from 'react';
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
      fetchEscalations();
    } catch (error) {
      console.error('Submit manual answer error:', error);
      setMessage('Failed to submit manual answer.');
    }
  };

  return (
    <div>
      <PageHeader
        title="Escalation"
        subtitle="Handle weak AI answers through manual follow-up and review status tracking."
      />

      {message && (
        <section className="card-like top-gap-sm">
          <p className="muted">{message}</p>
        </section>
      )}

      {loading ? (
        <section className="card-like top-gap-sm">
          <p className="muted">Loading escalations...</p>
        </section>
      ) : items.length === 0 ? (
        <section className="card-like top-gap-sm">
          <h3>No escalations yet</h3>
          <p className="muted">
            Low-confidence AI questions will appear here for Team Lead or Manager review.
          </p>
        </section>
      ) : (
        <div className="stack-gap">
          {items.map((item) => (
            <article key={item.escalation_id} className="card-like">
              <div className="row-between wrap-gap">
                <div>
                  <p className="muted small">
                    Asked by {item.asked_by_name || 'Unknown Staff'}
                  </p>
                  <h3>{item.question}</h3>
                </div>

                <StatusBadge status={item.status} />
              </div>

              <div className="card-like top-gap-sm">
                <p className="eyebrow">AI Answer</p>
                <p>{item.ai_answer || 'No AI answer recorded.'}</p>
                <p className="muted small">
                  Score: {item.ai_score || 0} | Source: {item.ai_source || 'unknown'}
                </p>
              </div>

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
                  This page is for Team Lead and Manager only.
                </p>

                <button
                  className="primary-btn"
                  onClick={() => submitAnswer(item.escalation_id)}
                  disabled={item.status === 'resolved'}
                >
                  {item.status === 'resolved'
                    ? 'Resolved'
                    : 'Submit Manual Answer'}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}