import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import './FloatingAIChat.css';

// Backend answers sometimes embed raw "Image: /static/..." path lines as
// plain text. The full /chat page renders those as real <img> tags, but
// this lightweight widget is text-only, so strip them instead of showing
// the raw path (which reads as broken/garbled to the user).
function stripImageLines(text) {
  return String(text || '')
    .split('\n')
    .filter((line) => !/^\s*Image:\s*\S+/i.test(line))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

// When the backend returns a structured step-by-step SOP (data.steps), build
// a clean "Step N: ..." list ourselves instead of showing the raw
// reply/answer blob, which duplicates the title/intro text and mixes in the
// same "Image: ..." noise.
function buildFloatingChatText(data, fallbackText = 'No usable answer returned from backend.') {
  const hasSteps = Array.isArray(data?.steps) && data.steps.length > 0;

  if (hasSteps) {
    const title = data.title || data.label || '';
    const stepsText = data.steps
      .map((step) => {
        const stepNumber = step.step_number || step.step || '';
        const content = String(step.content || step.answer || '').trim();
        return `Step ${stepNumber}: ${content}`;
      })
      .join('\n');

    return title ? `${title}\n\n${stepsText}` : stepsText;
  }

  const rawText = data?.reply || data?.answer || data?.message || fallbackText;

  return stripImageLines(rawText);
}

// Some Knowledge Base articles are authored in the rich HTML editor (real
// <h1>/<ul>/<img> tags with absolute image URLs already baked in), rather
// than the legacy plain-text "[IMAGE]"/numbered-step format. Detect that so
// it can be rendered as real HTML instead of showing literal escaped tags.
const HTML_CONTENT_PATTERN = /<\/?[a-z][\s\S]*>/i;

function isHtmlContent(text) {
  return HTML_CONTENT_PATTERN.test(String(text || ''));
}

// Same sanitize-before-render approach already used in ArticleDetail.jsx:
// strip dangerous tags/attributes before handing the HTML to
// dangerouslySetInnerHTML.
function sanitizeChatHtml(html) {
  if (typeof document === 'undefined') return String(html || '');

  const parser = new DOMParser();
  const parsedDocument = parser.parseFromString(`<div>${String(html || '')}</div>`, 'text/html');
  const wrapper = parsedDocument.body.firstChild;

  if (!wrapper) return '';

  wrapper
    .querySelectorAll('script, iframe, object, embed, form, input, button')
    .forEach((element) => element.remove());

  wrapper.querySelectorAll('*').forEach((element) => {
    Array.from(element.attributes).forEach((attribute) => {
      const attributeName = attribute.name.toLowerCase();
      const attributeValue = attribute.value.toLowerCase();

      if (
        attributeName.startsWith('on') ||
        attributeName === 'style' ||
        attributeValue.includes('javascript:')
      ) {
        element.removeAttribute(attribute.name);
      }
    });
  });

  return wrapper.innerHTML;
}

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
      const options = Array.isArray(data.options) ? data.options : [];

      // The backend wraps every short "keyword" question in a "please
      // select one" prompt, even when it only found a single confident
      // match. With just one option there's no real choice to make, so
      // skip the extra click and show the SOP steps immediately.
      const shouldAutoSelect = options.length === 1;

      const replyText = shouldAutoSelect
        ? buildFloatingChatText(options[0])
        : buildFloatingChatText(data);

      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          sender: 'ai',
          text: replyText,
          options: shouldAutoSelect ? [] : options,
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
    const optionText = buildFloatingChatText(
      option,
      `Please ask about ${option.title || option.label || 'this topic'} for more details.`
    );

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
                  {message.sender === 'ai' && isHtmlContent(message.text) ? (
                    <div
                      className="floating-ai-html-content"
                      dangerouslySetInnerHTML={{ __html: sanitizeChatHtml(message.text) }}
                    />
                  ) : (
                    message.text
                  )}
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
