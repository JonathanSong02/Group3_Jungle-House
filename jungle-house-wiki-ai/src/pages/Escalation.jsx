import { useState } from 'react';
import PageHeader from '../components/PageHeader';
import StatusBadge from '../components/StatusBadge';
import { escalations as initialEscalations } from '../data/mockData';

export default function Escalation() {
  const [items, setItems] = useState(initialEscalations);

  const updateAnswer = (id, value) => {
    setItems((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, submittedAnswer: value } : item,
      ),
    );
  };

  const submitAnswer = (id) => {
    setItems((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, status: 'Reviewing' } : item,
      ),
    );
  };

  return (
    <div>
      <PageHeader
        title="Escalation"
        subtitle="Handle weak AI answers through manual follow-up and review status tracking."
      />

      <div className="stack-gap">
        {items.map((item) => (
          <article key={item.id} className="card-like">
            <div className="row-between wrap-gap">
              <div>
                <p className="muted small">Asked by {item.askedBy}</p>
                <h3>{item.question}</h3>
              </div>
              <StatusBadge status={item.status} />
            </div>

            <textarea
              rows="4"
              value={item.submittedAnswer}
              onChange={(event) => updateAnswer(item.id, event.target.value)}
              placeholder="Write a manual answer for this escalated question"
            />

            <div className="row-between wrap-gap top-gap">
              <p className="muted small">This page is for Team Lead and Manager only.</p>
              <button className="primary-btn" onClick={() => submitAnswer(item.id)}>
                Submit Manual Answer
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
