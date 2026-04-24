import { useEffect, useRef, useState } from 'react';
import PageHeader from '../components/PageHeader';

const starterMessages = [
  {
    id: 1,
    sender: 'ai',
    type: 'text',
    text: 'Hello. Ask me anything about product knowledge, SOP, or sales guidance.',
    context: {
      unclear_count: 0,
    },
  },
];

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000').replace(/\/$/, '');
const CHAT_ENDPOINT = `${API_BASE_URL}/chat`;

function normalizeText(text) {
  return String(text || '').trim().toLowerCase();
}

function containsAny(text, phrases) {
  const q = normalizeText(text);
  return phrases.some((p) => q.includes(p));
}

const NEW_TOPIC_KEYWORDS = [
  'opening',
  'closing',
  'kiosk opening',
  'kiosk closing',
  'roadshow opening',
  'roadshow closing',
  'kiosk',
  'roadshow',
  'aeon',
  'backend',
  'warehouse',
  'ice bin',
  'shopify',
  'pos',
  'printer',
  'receipt printer',
  'booth',
  'dustbin',
  'opening notes',
  'shopify pos app opening',
  'shopify pos app closing',
  'closing spring warehouse',
  'backend opening checklist',
  'receipt printer preparation for opening',
  'ice bin daily closing checklist',
  'kuching booth closing dustbin check list',
  'sorry actually',
  'sorry i mean',
  'actually i want',
  'actually i mean',
  'no i mean',
  'change to',
  'switch to',
  'not kiosk',
  'not roadshow',
  'not this one',
  'wrong',
];

const FOLLOW_UP_KEYWORDS = [
  'step',
  'show all',
  'all step',
  'all steps',
  'full sop',
  'picture',
  'pictures',
  'photo',
  'photos',
  'image',
  'images',
  'next',
  'next step',
  'what next',
  'after this',
  'what should i do next',
  'continue',
  'then what',
  'section',
  'stocktake',
  'settlement',
  'device',
  'devices',
  'terminal',
  'terminal machine',
  'chiller',
  'display closing',
  'daily record',
  'daily record sheet',
  'additional',
];

function isNewTopicQuestion(question) {
  return containsAny(question, NEW_TOPIC_KEYWORDS);
}

function isFollowUpQuestion(question) {
  if (containsAny(question, FOLLOW_UP_KEYWORDS)) return true;
  return /^\d+$/.test(normalizeText(question));
}

function getUnclearCountFromMessage(message) {
  const directValue = Number(message?.unclear_count || 0);
  const contextValue = Number(message?.context?.unclear_count || 0);

  if (Number.isFinite(contextValue) && contextValue > 0) {
    return contextValue;
  }

  if (Number.isFinite(directValue) && directValue > 0) {
    return directValue;
  }

  return 0;
}

function buildImageUrl(imageUrl) {
  if (!imageUrl) return '';

  const cleanUrl = String(imageUrl).trim();

  if (cleanUrl.startsWith('http://') || cleanUrl.startsWith('https://')) {
    return cleanUrl;
  }

  if (cleanUrl.startsWith('/static/')) {
    return `${API_BASE_URL}${cleanUrl}`;
  }

  if (cleanUrl.startsWith('static/')) {
    return `${API_BASE_URL}/${cleanUrl}`;
  }

  if (cleanUrl.startsWith('/sop_images/')) {
    return `${API_BASE_URL}/static${cleanUrl}`;
  }

  if (cleanUrl.startsWith('sop_images/')) {
    return `${API_BASE_URL}/static/${cleanUrl}`;
  }

  if (cleanUrl.startsWith('/')) {
    return `${API_BASE_URL}${cleanUrl}`;
  }

  return `${API_BASE_URL}/static/${cleanUrl}`;
}

function extractImagePathsFromText(text) {
  const value = String(text || '');

  const matches = value.match(
    /(?:\/?static\/)?sop_images\/[^\s,|;)"']+\.(?:jpg|jpeg|png|webp|gif)/gi
  );

  if (!matches) return [];

  return [...new Set(matches)].map((path) => {
    let cleanPath = String(path).trim();

    cleanPath = cleanPath.replace(/^\/?static\//i, '');

    if (!cleanPath.startsWith('/')) {
      cleanPath = `/${cleanPath}`;
    }

    return cleanPath;
  });
}

function removeImagePathsFromText(text) {
  return String(text || '')
    .replace(/(?:\/?static\/)?sop_images\/[^\s,|;)"']+\.(?:jpg|jpeg|png|webp|gif)/gi, '')
    .replace(/\|+/g, '')
    .replace(/[ \t]+$/gm, '')
    .trim();
}

function getStepImages(step) {
  const images = [];

  if (Array.isArray(step?.images)) {
    images.push(...step.images);
  }

  if (Array.isArray(step?.image_urls)) {
    images.push(...step.image_urls);
  }

  if (step?.image_url) {
    images.push(step.image_url);
  }

  if (step?.image) {
    images.push(step.image);
  }

  images.push(...extractImagePathsFromText(step?.content));

  return [...new Set(images.filter(Boolean))];
}

function renderImages(imageUrls, labelPrefix = 'Image') {
  if (!Array.isArray(imageUrls) || imageUrls.length === 0) return null;

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '10px',
        marginTop: '10px',
      }}
    >
      {imageUrls.map((imageUrl, imageIndex) => {
        const finalImageUrl = buildImageUrl(imageUrl);

        return (
          <img
            key={`${finalImageUrl}-${imageIndex}`}
            src={finalImageUrl}
            alt={`${labelPrefix} ${imageIndex + 1}`}
            style={{
              width: '100%',
              maxWidth: '260px',
              borderRadius: '10px',
              border: '1px solid #ccc',
              display: 'block',
            }}
            onError={() => {
              console.log('Image failed to load:', finalImageUrl);
            }}
          />
        );
      })}
    </div>
  );
}

function buildAiMessage(data) {
  if (!data) {
    return {
      id: Date.now() + 1,
      sender: 'ai',
      type: 'text',
      text: 'No response returned from backend.',
      context: {
        unclear_count: 0,
      },
      unclear_count: 0,
      escalation_ready: false,
    };
  }

  const backendContext = data.context || {};
  const unclearCount = Number(backendContext.unclear_count || data.unclear_count || 0) || 0;
  const escalationReady = Boolean(data.escalation_ready);

  if (data.type === 'sop' && Array.isArray(data.steps) && data.steps.length > 0) {
    const lastStepNumber =
      data.steps.length > 0
        ? Number(data.steps[data.steps.length - 1]?.step_number || 0)
        : null;

    return {
      id: Date.now() + 1,
      sender: 'ai',
      type: 'sop',
      reply: data.reply || '',
      title: data.title || 'SOP Response',
      category: data.category || backendContext.category || '',
      purpose: data.purpose || '',
      section: data.section || backendContext.section || '',
      steps: data.steps || [],
      notes: data.notes || [],
      answer: data.answer || '',
      context: backendContext,
      unclear_count: unclearCount,
      escalation_ready: escalationReady,
      last_step_number: lastStepNumber,
    };
  }

  return {
    id: Date.now() + 1,
    sender: 'ai',
    type: 'text',
    text:
      data.reply ||
      data.answer ||
      data.response ||
      data.message ||
      'No usable answer returned from backend.',
    answer: data.answer || data.reply || '',
    title: data.title || backendContext.title || '',
    category: data.category || backendContext.category || '',
    section: data.section || backendContext.section || '',
    notes: data.notes || [],
    steps: Array.isArray(data.steps) ? data.steps : [],
    context: backendContext,
    unclear_count: unclearCount,
    escalation_ready: escalationReady,
    last_step_number: data.last_step_number || backendContext.last_step_number || null,
  };
}

function extractLatestSopContext(messages, question) {
  const questionIsNewTopic = isNewTopicQuestion(question);
  const questionIsFollowUp = isFollowUpQuestion(question);

  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i];
    if (msg.sender !== 'ai') continue;

    const unclearCount = getUnclearCountFromMessage(msg);

    if (msg.type === 'sop' && msg.title) {
      const lastStep =
        Array.isArray(msg.steps) && msg.steps.length > 0
          ? Number(msg.steps[msg.steps.length - 1]?.step_number || 0)
          : msg.last_step_number || null;

      if (questionIsNewTopic && !questionIsFollowUp) {
        return {
          title: '',
          category: '',
          section: '',
          steps: [],
          unclear_count: 0,
          last_step_number: null,
        };
      }

      return {
        title: msg.title,
        category: msg.category || msg.context?.category || '',
        section: msg.section || msg.context?.section || '',
        steps: Array.isArray(msg.steps) ? msg.steps : [],
        unclear_count: unclearCount,
        last_step_number: lastStep,
      };
    }

    if (msg.type === 'text' && msg.title) {
      if (questionIsNewTopic && !questionIsFollowUp) {
        return {
          title: '',
          category: '',
          section: '',
          steps: [],
          unclear_count: 0,
          last_step_number: null,
        };
      }

      return {
        title: msg.title,
        category: msg.category || msg.context?.category || '',
        section: msg.section || msg.context?.section || '',
        steps: Array.isArray(msg.steps) ? msg.steps : [],
        unclear_count: unclearCount,
        last_step_number: msg.last_step_number || null,
      };
    }

    if (msg.type === 'text' && unclearCount > 0) {
      return {
        title: '',
        category: msg.category || msg.context?.category || '',
        section: '',
        steps: [],
        unclear_count: unclearCount,
        last_step_number: null,
      };
    }
  }

  return {
    title: '',
    category: '',
    section: '',
    steps: [],
    unclear_count: 0,
    last_step_number: null,
  };
}

export default function Chat() {
  const [messages, setMessages] = useState(starterMessages);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = async () => {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || loading) return;

    const userMessage = {
      id: Date.now(),
      sender: 'user',
      type: 'text',
      text: trimmedQuestion,
    };

    const context = extractLatestSopContext(messages, trimmedQuestion);

    setMessages((prev) => [...prev, userMessage]);
    setQuestion('');
    setLoading(true);

    try {
      const response = await fetch(CHAT_ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: trimmedQuestion,
          context,
        }),
      });

      const contentType = response.headers.get('content-type') || '';
      let data;

      if (contentType.includes('application/json')) {
        data = await response.json();
      } else {
        const rawText = await response.text();
        data = { answer: rawText, type: 'text' };
      }

      if (!response.ok) {
        throw new Error(
          data?.answer ||
            data?.reply ||
            data?.error ||
            data?.message ||
            `Backend request failed with status ${response.status}.`
        );
      }

      const aiMessage = buildAiMessage(data);

      console.log('Backend data:', data);
      console.log('AI message:', aiMessage);

      setMessages((prev) => [...prev, aiMessage]);
    } catch (error) {
      console.error('Chat request failed:', error);

      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          sender: 'ai',
          type: 'text',
          text:
            error.message ||
            'Failed to connect to backend. Please check whether Flask is running.',
          context: {
            unclear_count: 0,
          },
          unclear_count: 0,
          escalation_ready: false,
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
            {messages.map((message) => {
              const textImages = [
                ...extractImagePathsFromText(message.text),
                ...extractImagePathsFromText(message.answer),
              ];

              return (
                <div
                  key={message.id}
                  className={`message-bubble ${message.sender === 'user' ? 'user' : 'ai'}`}
                >
                  <strong>{message.sender === 'user' ? 'You' : 'AI'}</strong>

                  {message.type === 'text' ? (
                    <div style={{ marginTop: '8px' }}>
                      <p
                        style={{
                          whiteSpace: 'pre-wrap',
                          marginBottom: message.answer ? '10px' : 0,
                        }}
                      >
                        {removeImagePathsFromText(message.text)}
                      </p>

                      {message.answer && message.answer !== message.text ? (
                        <div
                          style={{
                            marginTop: '8px',
                            padding: '10px 12px',
                            borderRadius: '10px',
                            backgroundColor: message.escalation_ready ? '#fff5f5' : '#f8f9fa',
                            border: message.escalation_ready
                              ? '1px solid #ffb3b3'
                              : '1px solid #e1e1e1',
                          }}
                        >
                          {message.title ? (
                            <h4 style={{ marginBottom: '8px' }}>{message.title}</h4>
                          ) : null}

                          <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
                            {removeImagePathsFromText(message.answer)}
                          </p>

                          {renderImages(textImages, 'Answer image')}
                        </div>
                      ) : (
                        renderImages(textImages, 'Message image')
                      )}

                      {Array.isArray(message.steps) && message.steps.length > 0 ? (
                        <div style={{ marginTop: '12px' }}>
                          {message.steps.map((step, index) => {
                            const stepImages = getStepImages(step);

                            return (
                              <div
                                key={`${step.step_number || index}-${index}`}
                                style={{
                                  border: '1px solid #ddd',
                                  borderRadius: '12px',
                                  padding: '12px',
                                  marginBottom: '14px',
                                  backgroundColor: '#fff',
                                }}
                              >
                                <h4 style={{ marginBottom: '8px' }}>
                                  Step {step.step_number || index + 1}
                                </h4>

                                {step.section ? (
                                  <p
                                    style={{
                                      marginBottom: '8px',
                                      fontWeight: '600',
                                      color: '#7a5c00',
                                    }}
                                  >
                                    Section: {step.section}
                                  </p>
                                ) : null}

                                <p style={{ whiteSpace: 'pre-wrap', marginBottom: '10px' }}>
                                  {removeImagePathsFromText(step.content)}
                                </p>

                                {renderImages(
                                  stepImages,
                                  `Step ${step.step_number || index + 1} image`
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <div style={{ marginTop: '10px' }}>
                      {message.reply ? (
                        <p style={{ whiteSpace: 'pre-wrap', marginBottom: '12px' }}>
                          {removeImagePathsFromText(message.reply)}
                        </p>
                      ) : null}

                      <h3 style={{ marginBottom: '8px' }}>{message.title}</h3>

                      {message.purpose ? (
                        <p style={{ marginBottom: '12px' }}>
                          <strong>Purpose:</strong> {message.purpose}
                        </p>
                      ) : null}

                      {message.steps?.map((step, index) => {
                        const stepImages = getStepImages(step);

                        return (
                          <div
                            key={`${step.step_number || index}-${index}`}
                            style={{
                              border: '1px solid #ddd',
                              borderRadius: '12px',
                              padding: '12px',
                              marginBottom: '14px',
                              backgroundColor: '#fff',
                            }}
                          >
                            <h4 style={{ marginBottom: '8px' }}>
                              Step {step.step_number || index + 1}
                            </h4>

                            {step.section ? (
                              <p
                                style={{
                                  marginBottom: '8px',
                                  fontWeight: '600',
                                  color: '#7a5c00',
                                }}
                              >
                                Section: {step.section}
                              </p>
                            ) : null}

                            <p style={{ whiteSpace: 'pre-wrap', marginBottom: '10px' }}>
                              {removeImagePathsFromText(step.content)}
                            </p>

                            {renderImages(
                              stepImages,
                              `Step ${step.step_number || index + 1} image`
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}

            {loading ? <p className="muted">AI is generating a response...</p> : null}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-input-row">
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask a work-related question..."
              disabled={loading}
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
      </div>
    </div>
  );
}