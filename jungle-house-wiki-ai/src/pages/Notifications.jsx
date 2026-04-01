import { useState } from 'react';
import PageHeader from '../components/PageHeader';
import { notifications as initialNotifications } from '../data/mockData';

export default function Notifications() {
  const [items, setItems] = useState(initialNotifications);

  const markAsRead = (id) => {
    setItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, read: true } : item)),
    );
  };

  return (
    <div>
      <PageHeader
        title="Notifications"
        subtitle="System alerts for escalations, reviews, reminders, and announcements."
      />

      <div className="stack-gap">
        {items.map((item) => (
          <article key={item.id} className="card-like row-between wrap-gap">
            <div>
              <p className="eyebrow">{item.read ? 'Read' : 'Unread'}</p>
              <h3>{item.title}</h3>
              <p className="muted">{item.detail}</p>
            </div>
            {!item.read ? (
              <button className="secondary-btn" onClick={() => markAsRead(item.id)}>
                Mark as read
              </button>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}
