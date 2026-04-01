import { useState } from 'react';
import PageHeader from '../../components/PageHeader';
import StatusBadge from '../../components/StatusBadge';
import { reviewQueue as initialQueue } from '../../data/mockData';

export default function ReviewManagement() {
  const [queue, setQueue] = useState(initialQueue);

  const updateStatus = (id, nextStatus) => {
    setQueue((prev) =>
      prev.map((item) => (item.id === id ? { ...item, status: nextStatus } : item)),
    );
  };

  return (
    <div>
      <PageHeader
        title="Review Management"
        subtitle="Approve or reject manual answers before publishing them as official knowledge."
      />

      <div className="stack-gap">
        {queue.map((item) => (
          <article key={item.id} className="card-like">
            <div className="row-between wrap-gap">
              <div>
                <h3>{item.question}</h3>
                <p className="muted">{item.answer}</p>
              </div>
              <StatusBadge status={item.status} />
            </div>
            <div className="button-group top-gap">
              <button className="primary-btn" onClick={() => updateStatus(item.id, 'Approved')}>
                Approve
              </button>
              <button className="secondary-btn danger-btn" onClick={() => updateStatus(item.id, 'Rejected')}>
                Reject
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
