import { useState } from 'react';
import PageHeader from '../components/PageHeader';

const starterMessages = [
  {
    id: 1,
    sender: 'ai',
    text: 'Hello. Ask me anything about product knowledge, SOP, or sales guidance.',
  },
];

export default function Chat() {
  const [messages, setMessages] = useState(starterMessages);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    if (!question.trim()) return;

    const userMessage = {
      id: Date.now(),
      sender: 'user',
      text: question.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setQuestion('');
    setLoading(true);

    // Replace this simulated response with backend API call later.
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          sender: 'ai',
          text: 'Sample response: connect this page to your backend /chat endpoint later.',
        },
      ]);
      setLoading(false);
    }, 700);
  };

  return (
    <div>
      <PageHeader
        title="AI Chat"
        subtitle="Ask questions, review history, and display AI answers returned from the backend."
      />

      <div className="chat-layout">
        <section className="card-like chat-panel">
          <div className="chat-messages">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`message-bubble ${message.sender === 'user' ? 'user' : 'ai'}`}
              >
                <strong>{message.sender === 'user' ? 'You' : 'AI'}</strong>
                <p>{message.text}</p>
              </div>
            ))}
            {loading ? <p className="muted">AI is generating a response...</p> : null}
          </div>

          <div className="chat-input-row">
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask a work-related question..."
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  handleSend();
                }
              }}
            />
            <button className="primary-btn" onClick={handleSend} disabled={loading}>
              Send
            </button>
          </div>
        </section>

        <aside className="card-like side-panel">
          <h3>Frontend notes</h3>
          <ul className="simple-list">
            <li>Store question in backend later.</li>
            <li>Show loading and error state clearly.</li>
            <li>Display escalation notice when answer is weak.</li>
            <li>Fetch chat history by user after login.</li>
          </ul>
        </aside>
      </div>
    </div>
  );
}
