import { useState } from 'react';
import PageHeader from '../components/PageHeader';

const starterMessages = [
  {
    id: 1,
    sender: 'ai',
    text: 'Hello. Ask me anything about product knowledge, SOP, or sales guidance.',
    category: null,
    title: null,
    score: null,
  },
];

export default function Chat() {
  const [messages, setMessages] = useState(starterMessages);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || loading) return;

    const userMessage = {
      id: Date.now(),
      sender: 'user',
      text: trimmedQuestion,
    };

    setMessages((prev) => [...prev, userMessage]);
    setQuestion('');
    setLoading(true);

    try {
      const response = await fetch('http://127.0.0.1:5000/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmedQuestion }),
      });

      if (!response.ok) {
        throw new Error('Backend request failed');
      }

      const data = await response.json();

      const aiMessage = {
        id: Date.now() + 1,
        sender: 'ai',
        text: data.answer || 'No answer returned from backend.',
        category: data.category || null,
        title: data.title || null,
        score: data.score ?? null,
      };

      setMessages((prev) => [...prev, aiMessage]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          sender: 'ai',
          text: 'Unable to connect to AI backend. Please check whether Flask server is running.',
          category: null,
          title: null,
          score: null,
        },
      ]);
    } finally {
      setLoading(false);
    }
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

                {message.sender === 'ai' && (
                  <div className="muted" style={{ marginTop: '8px', fontSize: '0.9rem' }}>
                    {message.category ? <div>Category: {message.category}</div> : null}
                    {message.title ? <div>Title: {message.title}</div> : null}
                    {message.score !== null ? (
                      <div>Score: {Number(message.score).toFixed(3)}</div>
                    ) : null}
                    {!message.category && message.text.includes('Escalate') ? (
                      <div>Escalation notice: AI confidence is low. Please refer to team lead.</div>
                    ) : null}
                  </div>
                )}
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
              {loading ? 'Sending...' : 'Send'}
            </button>
          </div>
        </section>

        <aside className="card-like side-panel">
          <h3>Frontend notes</h3>
          <ul className="simple-list">
            <li>Questions are now sent to the Flask AI backend.</li>
            <li>Loading and connection error states are shown clearly.</li>
            <li>Low-confidence responses can display escalation notice.</li>
            <li>Next stage can store chat history after login.</li>
          </ul>
        </aside>
      </div>
    </div>
  );
}