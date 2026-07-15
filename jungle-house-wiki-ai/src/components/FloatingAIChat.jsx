import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import './FloatingAIChat.css';

export default function FloatingAIChat() {
  const location = useLocation();
  const { user } = useAuth();

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, open]);

  // The full AI Chat page already gives the complete experience, so avoid
  // showing a redundant shortcut button on top of it.
  if (location.pathname.startsWith('/chat')) {
    return null;
  }

  const handleSend = async (event) => {
    event.preventDefault();

    const trimmedQuestion = question.trim();

    if (!trimmedQuestion || loading) return;

    const userMessage = {
      id: Date.now(),
      sender: 'user',
      text: trimmedQuestion,
    };

    setMessages((prev) => [...prev, userMessage]);
    setQuestion('');
    setError('');
    setLoading(true);

    try {
      const response = await api.post('/chat', {
        question: trimmedQuestion,
        context: {},
        user_id: user?.id || user?.user_id || null,
      });

      const data = response.data || {};

      const replyText =
        data.reply ||
        data.answer ||
        data.message ||
        'No usable answer returned from backend.';

      const options = Array.isArray(data.options) ? data.options : [];

      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          sender: 'ai',
          text: replyText,
          options,
        },
      ]);
    } catch (requestError) {
      console.error('Floating AI chat request failed:', requestError);
      setError('Unable to get AI response right now. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectOption = (option) => {
    const optionText =
      option.answer ||
      option.reply ||
      `Please ask about ${option.title || option.label || 'this topic'} for more details.`;

    setMessages((prev) => [
      ...prev,
      {
        id: Date.now(),
        sender: 'ai',
        text: optionText,
        options: [],
      },
    ]);
  };

  return (
    <div className="floating-ai-chat">
      {open && (
        <div className="floating-ai-panel">
          <div className="floating-ai-header">
            <div>
              <strong>AI Assistant</strong>
              <p className="muted small">Ask me anything from the Wiki.</p>
            </div>

            <button
              type="button"
              className="floating-ai-close-btn"
              onClick={() => setOpen(false)}
              aria-label="Close AI chat"
            >
              ×
            </button>
          </div>

          <div className="floating-ai-messages">
            {messages.length === 0 && (
              <div className="floating-ai-bubble ai">
                Hi, I am your Jungle House AI Assistant. Ask me anything from the Wiki.
              </div>
            )}

            {messages.map((message) => (
              <div key={message.id}>
                <div
                  className={`floating-ai-bubble ${message.sender === 'user' ? 'user' : 'ai'}`}
                >
                  {message.text}
                </div>

                {Array.isArray(message.options) && message.options.length > 0 && (
                  <div className="floating-ai-options">
                    {message.options.map((option, index) => (
                      <button
                        type="button"
                        key={`${message.id}-option-${index}`}
                        className="floating-ai-option-btn"
                        onClick={() => handleSelectOption(option)}
                      >
                        {option.label || option.title || `Option ${index + 1}`}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="floating-ai-bubble ai floating-ai-thinking">
                AI is thinking...
              </div>
            )}

            {error && <div className="floating-ai-error">{error}</div>}

            <div ref={messagesEndRef} />
          </div>

          <form className="floating-ai-input-row" onSubmit={handleSend}>
            <input
              type="text"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Type your question..."
              disabled={loading}
            />

            <button type="submit" className="floating-ai-send-btn" disabled={loading}>
              Send
            </button>
          </form>
        </div>
      )}

      <button
        type="button"
        className="floating-ai-button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label={open ? 'Close AI chat' : 'Open AI chat'}
      >
        AI
      </button>
    </div>
  );
}
