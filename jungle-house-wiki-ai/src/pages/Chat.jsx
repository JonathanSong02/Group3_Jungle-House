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

const CHAT_HISTORY_KEY = 'jh_ai_chat_history';
const CHAT_SESSIONS_KEY = 'jh_ai_chat_sessions';
const ACTIVE_CHAT_SESSION_KEY = 'jh_active_chat_session';

function normalizeText(text) {
  return String(text || '')
    .replace(/[’‘`´]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[–—]/g, '-')
    .trim()
    .toLowerCase();
}

function cleanQuestionInput(text) {
  return String(text || '')
    .replace(/[’‘`´]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[–—]/g, '-')
    .trim();
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

function renderResponseMeta(message) {
  if (message.sender !== 'ai') return null;

  const hasConfidence = message.confidence !== undefined && message.confidence !== null;
  const hasSource = Boolean(message.source);
  const hasFallback = Boolean(message.fallback || message.escalation_ready || message.escalation_required);

  if (!hasConfidence && !hasSource && !hasFallback) return null;

  const confidenceValue = Number(message.confidence || 0);
  const confidencePercent = Math.round(confidenceValue * 100);

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '8px',
        marginTop: '8px',
        marginBottom: '6px',
        fontSize: '12px',
      }}
    >
      {hasConfidence ? (
        <span
          style={{
            padding: '4px 8px',
            borderRadius: '999px',
            backgroundColor: '#f1f3f5',
            border: '1px solid #dee2e6',
          }}
        >
          Confidence: {confidencePercent}% {message.confidence_label ? `(${message.confidence_label})` : ''}
        </span>
      ) : null}

      {hasSource ? (
        <span
          style={{
            padding: '4px 8px',
            borderRadius: '999px',
            backgroundColor: '#f8f9fa',
            border: '1px solid #dee2e6',
          }}
        >
          Source: {message.source}
        </span>
      ) : null}

      {hasFallback ? (
        <span
          style={{
            padding: '4px 8px',
            borderRadius: '999px',
            backgroundColor: '#fff5f5',
            border: '1px solid #ffb3b3',
            color: '#b00020',
          }}
        >
          {message.escalation_ready || message.escalation_required ? 'Escalation required' : 'Fallback'}
        </span>
      ) : null}
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
      escalation_required: false,
      confidence: 0,
      confidence_label: 'low',
      source: 'frontend_empty_response',
      fallback: true,
      fallback_message: 'No response returned from backend.',
      message: 'No response returned from backend.',
    };
  }

  const backendContext = data.context || {};
  const unclearCount = Number(backendContext.unclear_count || data.unclear_count || 0) || 0;
  const escalationReady = Boolean(data.escalation_ready || data.escalation_required);
  const confidence = Number(data.confidence ?? data.score ?? 0) || 0;
  const confidenceLabel = data.confidence_label || '';
  const source = data.source || '';
  const fallback = Boolean(data.fallback);
  const fallbackMessage = data.fallback_message || '';
  const backendMessage = data.message || '';

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
      escalation_required: escalationReady,
      confidence,
      confidence_label: confidenceLabel,
      source,
      fallback,
      fallback_message: fallbackMessage,
      message: backendMessage,
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
    escalation_required: escalationReady,
    confidence,
    confidence_label: confidenceLabel,
    source,
    fallback,
    fallback_message: fallbackMessage,
    message: backendMessage,
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

function createNewSession() {
  const now = new Date().toLocaleString();

  return {
    id: Date.now(),
    title: 'New Chat',
    messages: starterMessages,
    created_at: now,
    updated_at: now,
  };
}

function getChatSessionsFromStorage() {
  try {
    const saved = localStorage.getItem(CHAT_SESSIONS_KEY);
    const sessions = saved ? JSON.parse(saved) : [];

    if (Array.isArray(sessions) && sessions.length > 0) {
      return sessions;
    }

    const firstSession = createNewSession();
    localStorage.setItem(CHAT_SESSIONS_KEY, JSON.stringify([firstSession]));
    localStorage.setItem(ACTIVE_CHAT_SESSION_KEY, String(firstSession.id));

    return [firstSession];
  } catch (error) {
    console.error('Unable to read chat sessions:', error);
    return [createNewSession()];
  }
}

function saveChatSessionsToStorage(sessions) {
  try {
    localStorage.setItem(CHAT_SESSIONS_KEY, JSON.stringify(sessions));
  } catch (error) {
    console.error('Unable to save chat sessions:', error);
  }
}

function getActiveSessionIdFromStorage(sessions) {
  try {
    const savedId = localStorage.getItem(ACTIVE_CHAT_SESSION_KEY);

    if (savedId && sessions.some((session) => String(session.id) === String(savedId))) {
      return Number(savedId);
    }

    return sessions[0]?.id || null;
  } catch (error) {
    console.error('Unable to read active chat session:', error);
    return sessions[0]?.id || null;
  }
}

function saveActiveSessionId(sessionId) {
  try {
    localStorage.setItem(ACTIVE_CHAT_SESSION_KEY, String(sessionId));
  } catch (error) {
    console.error('Unable to save active chat session:', error);
  }
}

function makeSessionTitle(questionText) {
  const cleanTitle = String(questionText || '').trim();

  if (!cleanTitle) return 'New Chat';

  if (cleanTitle.length <= 35) {
    return cleanTitle;
  }

  return `${cleanTitle.slice(0, 35)}...`;
}

function getHistoryFromStorage() {
  try {
    const saved = localStorage.getItem(CHAT_HISTORY_KEY);
    return saved ? JSON.parse(saved) : [];
  } catch (error) {
    console.error('Unable to read chat history:', error);
    return [];
  }
}

function saveHistoryToStorage(history) {
  try {
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(history));
  } catch (error) {
    console.error('Unable to save chat history:', error);
  }
}

function getReadableAnswer(message) {
  if (!message) return '';

  if (message.type === 'sop') {
    const steps = Array.isArray(message.steps)
      ? message.steps
          .map((step) => `Step ${step.step_number || ''}: ${removeImagePathsFromText(step.content || '')}`)
          .join('\n')
      : '';

    return [message.reply, message.title, message.purpose, steps]
      .filter(Boolean)
      .join('\n\n');
  }

  return removeImagePathsFromText(message.answer || message.text || message.reply || '');
}

export default function Chat() {
  const initialSessions = getChatSessionsFromStorage();

  const [activeTab, setActiveTab] = useState('ask');
  const [chatSessions, setChatSessions] = useState(initialSessions);
  const [activeSessionId, setActiveSessionId] = useState(() =>
    getActiveSessionIdFromStorage(initialSessions)
  );

  const activeSession =
    chatSessions.find((session) => session.id === activeSessionId) || chatSessions[0];

  const messages = activeSession?.messages || starterMessages;

  const [history, setHistory] = useState(() => getHistoryFromStorage());
  const [historySearch, setHistorySearch] = useState('');
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [confirmModal, setConfirmModal] = useState({
    open: false,
    type: '',
    title: '',
    message: '',
    confirmText: 'OK',
    sessionId: null,
    sessionTitle: '',
  });
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, activeSessionId]);

  const updateCurrentSessionMessages = (nextMessages, titleQuestion = '') => {
    const now = new Date().toLocaleString();

    setChatSessions((prev) => {
      const updatedSessions = prev.map((session) => {
        if (session.id !== activeSessionId) {
          return session;
        }

        const shouldUpdateTitle =
          session.title === 'New Chat' && titleQuestion && titleQuestion.trim();

        return {
          ...session,
          title: shouldUpdateTitle ? makeSessionTitle(titleQuestion) : session.title,
          messages: nextMessages,
          updated_at: now,
        };
      });

      saveChatSessionsToStorage(updatedSessions);
      return updatedSessions;
    });
  };

  const addChatHistory = (userQuestion, aiMessage) => {
    const newRecord = {
      id: Date.now(),
      question: userQuestion,
      answer: getReadableAnswer(aiMessage),
      title: aiMessage.title || '',
      category: aiMessage.category || '',
      source: aiMessage.source || '',
      confidence: aiMessage.confidence ?? 0,
      confidence_label: aiMessage.confidence_label || '',
      fallback: Boolean(aiMessage.fallback),
      escalation_required: Boolean(aiMessage.escalation_ready || aiMessage.escalation_required),
      created_at: new Date().toLocaleString(),
    };

    setHistory((prev) => {
      const updatedHistory = [newRecord, ...prev].slice(0, 100);
      saveHistoryToStorage(updatedHistory);
      return updatedHistory;
    });
  };

  const handleSelectSession = (sessionId) => {
    setActiveSessionId(sessionId);
    saveActiveSessionId(sessionId);
    setActiveTab('ask');
  };

  const handleNewChat = () => {
    const newSession = createNewSession();
    const updatedSessions = [newSession, ...chatSessions];

    setChatSessions(updatedSessions);
    setActiveSessionId(newSession.id);

    saveChatSessionsToStorage(updatedSessions);
    saveActiveSessionId(newSession.id);

    setQuestion('');
    setActiveTab('ask');
  };

  const closeConfirmModal = () => {
    setConfirmModal({
      open: false,
      type: '',
      title: '',
      message: '',
      confirmText: 'OK',
      sessionId: null,
      sessionTitle: '',
    });
  };

  const openDeleteSessionModal = (sessionId, sessionTitle) => {
    setConfirmModal({
      open: true,
      type: 'delete-session',
      title: 'Delete chat?',
      message: `This will delete ${sessionTitle || 'this chat'}.`,
      confirmText: 'Delete',
      sessionId,
      sessionTitle: sessionTitle || '',
    });
  };

  const openClearCurrentChatModal = () => {
    setConfirmModal({
      open: true,
      type: 'clear-current-chat',
      title: 'Clear current chat?',
      message: 'This will remove all messages in the current conversation.',
      confirmText: 'OK',
      sessionId: null,
      sessionTitle: '',
    });
  };

  const openClearHistoryModal = () => {
    setConfirmModal({
      open: true,
      type: 'clear-history',
      title: 'Clear chat history?',
      message: 'This will remove all saved chat history records.',
      confirmText: 'Clear',
      sessionId: null,
      sessionTitle: '',
    });
  };

  const deleteSessionById = (sessionId) => {
    const remainingSessions = chatSessions.filter((session) => session.id !== sessionId);

    if (remainingSessions.length === 0) {
      const newSession = createNewSession();

      setChatSessions([newSession]);
      setActiveSessionId(newSession.id);

      saveChatSessionsToStorage([newSession]);
      saveActiveSessionId(newSession.id);

      return;
    }

    const nextActiveSessionId =
      activeSessionId === sessionId ? remainingSessions[0].id : activeSessionId;

    setChatSessions(remainingSessions);
    setActiveSessionId(nextActiveSessionId);

    saveChatSessionsToStorage(remainingSessions);
    saveActiveSessionId(nextActiveSessionId);
  };

  const handleConfirmModalAction = () => {
    if (confirmModal.type === 'delete-session') {
      deleteSessionById(confirmModal.sessionId);
    }

    if (confirmModal.type === 'clear-current-chat') {
      updateCurrentSessionMessages(starterMessages);
    }

    if (confirmModal.type === 'clear-history') {
      setHistory([]);
      saveHistoryToStorage([]);
    }

    closeConfirmModal();
  };

  const handleDeleteSession = (sessionId, sessionTitle) => {
    openDeleteSessionModal(sessionId, sessionTitle);
  };

  const handleClearCurrentChat = () => {
    openClearCurrentChatModal();
  };

  const handleDeleteHistory = (historyId) => {
    const updatedHistory = history.filter((item) => item.id !== historyId);
    setHistory(updatedHistory);
    saveHistoryToStorage(updatedHistory);
  };

  const handleClearHistory = () => {
    openClearHistoryModal();
  };

  const handleReuseQuestion = (selectedQuestion) => {
    setQuestion(selectedQuestion);
    setActiveTab('ask');
  };

  const handleSend = async () => {
    const trimmedQuestion = cleanQuestionInput(question);
    if (!trimmedQuestion || loading) return;

    const userMessage = {
      id: Date.now(),
      sender: 'user',
      type: 'text',
      text: trimmedQuestion,
    };

    const context = extractLatestSopContext(messages, trimmedQuestion);
    const messagesAfterUserQuestion = [...messages, userMessage];

    updateCurrentSessionMessages(messagesAfterUserQuestion, trimmedQuestion);

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
      const messagesAfterAiResponse = [...messagesAfterUserQuestion, aiMessage];

      console.log('Backend data:', data);
      console.log('AI message:', aiMessage);

      updateCurrentSessionMessages(messagesAfterAiResponse, trimmedQuestion);
      addChatHistory(trimmedQuestion, aiMessage);
    } catch (error) {
      console.error('Chat request failed:', error);

      const errorMessage = {
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
        escalation_required: false,
        confidence: 0,
        confidence_label: 'low',
        source: 'frontend_request_error',
        fallback: true,
        fallback_message:
          error.message ||
          'Failed to connect to backend. Please check whether Flask is running.',
        message:
          error.message ||
          'Failed to connect to backend. Please check whether Flask is running.',
      };

      const messagesAfterError = [...messagesAfterUserQuestion, errorMessage];

      updateCurrentSessionMessages(messagesAfterError, trimmedQuestion);
      addChatHistory(trimmedQuestion, errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const filteredHistory = history.filter((item) => {
    const search = historySearch.toLowerCase();

    return (
      String(item.question || '').toLowerCase().includes(search) ||
      String(item.answer || '').toLowerCase().includes(search) ||
      String(item.category || '').toLowerCase().includes(search) ||
      String(item.source || '').toLowerCase().includes(search)
    );
  });

  const renderMessageContent = (message) => {
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
        {renderResponseMeta(message)}

        {message.sender === 'ai' &&
        message.fallback_message &&
        message.fallback_message !== message.text &&
        message.fallback_message !== message.answer ? (
          <p
            style={{
              whiteSpace: 'pre-wrap',
              marginTop: '8px',
              marginBottom: '8px',
              padding: '8px 10px',
              borderRadius: '10px',
              backgroundColor: message.escalation_ready ? '#fff5f5' : '#fff8e1',
              border: message.escalation_ready
                ? '1px solid #ffb3b3'
                : '1px solid #ffe08a',
            }}
          >
            {message.fallback_message}
          </p>
        ) : null}

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
  };

  const renderRecentsSidebar = () => {
    return (
      <aside className="chat-recents-panel">
        <div className="chat-recents-header">
          <h3>Recents</h3>

          <button
            type="button"
            className="secondary-btn"
            onClick={handleNewChat}
          >
            New
          </button>
        </div>

        <div className="chat-recents-list">
          {chatSessions.map((session) => (
            <div
              key={session.id}
              className={`chat-recent-item ${
                session.id === activeSessionId ? 'active' : ''
              }`}
            >
              <button
                type="button"
                className="chat-recent-title"
                onClick={() => handleSelectSession(session.id)}
                title={session.title}
              >
                {session.title}
              </button>

              <button
                type="button"
                className="chat-recent-delete"
                onClick={() => handleDeleteSession(session.id, session.title)}
                title="Delete chat"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </aside>
    );
  };

  const renderAskQuestion = () => {
    return (
      <div className="ai-chat-shell">
        {renderRecentsSidebar()}

        <section className="card-like chat-panel ai-chat-panel">
          <div className="ai-chat-header">
            <div>
              <h3>{activeSession?.title || 'New Chat'}</h3>
              <p>
                Ask the AI a work-related question using natural language.
              </p>
            </div>

            <button
              type="button"
              className="secondary-btn danger-btn"
              onClick={handleClearCurrentChat}
            >
              Clear Current Chat
            </button>
          </div>

          <div className="chat-messages ai-chat-messages">
            {messages.map((message) => renderMessageContent(message))}

            {loading ? <p className="chat-loading">AI is generating a response...</p> : null}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-input-row ai-chat-input-row">
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
    );
  };

  const renderChatHistory = () => {
    return (
      <section className="card-like">
        <div className="row-between wrap-gap" style={{ marginBottom: '1rem' }}>
          <div>
            <h3>Chat History</h3>
            <p className="muted">
              Review previous question-and-answer sessions and reuse past questions.
            </p>
          </div>

          <button
            type="button"
            className="secondary-btn danger-btn"
            onClick={handleClearHistory}
            disabled={history.length === 0}
          >
            Clear History
          </button>
        </div>

        <div style={{ marginBottom: '1rem' }}>
          <label className="form-label">Search History</label>
          <input
            type="text"
            placeholder="Search previous questions, answers, category, or source..."
            value={historySearch}
            onChange={(event) => setHistorySearch(event.target.value)}
          />
        </div>

        {filteredHistory.length === 0 ? (
          <p className="muted">No chat history found yet.</p>
        ) : (
          <div className="stack-gap">
            {filteredHistory.map((item) => (
              <article key={item.id} className="card-like">
                <div className="row-between wrap-gap">
                  <div>
                    <p className="eyebrow">{item.created_at}</p>
                    <h3>{item.question}</h3>
                    <p className="muted">
                      Category: {item.category || '-'} · Source: {item.source || '-'} · Confidence:{' '}
                      {Math.round(Number(item.confidence || 0) * 100)}%
                    </p>
                  </div>

                  <div className="button-group">
                    <button
                      type="button"
                      className="secondary-btn"
                      onClick={() => handleReuseQuestion(item.question)}
                    >
                      Ask Again
                    </button>

                    <button
                      type="button"
                      className="secondary-btn danger-btn"
                      onClick={() => handleDeleteHistory(item.id)}
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {item.escalation_required ? (
                  <p
                    style={{
                      marginTop: '0.75rem',
                      padding: '0.6rem 0.8rem',
                      borderRadius: '10px',
                      backgroundColor: '#fff5f5',
                      border: '1px solid #ffb3b3',
                      color: '#b00020',
                    }}
                  >
                    This question required escalation or review.
                  </p>
                ) : null}

                <div style={{ marginTop: '1rem' }}>
                  <h4>AI Answer</h4>
                  <p className="muted" style={{ whiteSpace: 'pre-wrap' }}>
                    {item.answer || 'No answer saved.'}
                  </p>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    );
  };

  const renderConfirmModal = () => {
    if (!confirmModal.open) return null;

    const isDangerAction =
      confirmModal.type === 'delete-session' || confirmModal.type === 'clear-history';

    return (
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 3000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '1.25rem',
          background: 'rgba(32, 22, 8, 0.42)',
          backdropFilter: 'blur(2px)',
        }}
        onClick={closeConfirmModal}
      >
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="chat-confirm-title"
          style={{
            width: 'min(100%, 520px)',
            background: '#fffdf8',
            border: '1px solid rgba(226, 205, 167, 0.95)',
            borderRadius: '24px',
            boxShadow: '0 22px 55px rgba(64, 43, 10, 0.2)',
            overflow: 'hidden',
          }}
          onClick={(event) => event.stopPropagation()}
        >
          <div style={{ padding: '1.5rem 1.5rem 1rem' }}>
            <h3
              id="chat-confirm-title"
              style={{
                margin: '0 0 0.65rem',
                color: 'var(--heading)',
                fontSize: '1.35rem',
              }}
            >
              {confirmModal.title}
            </h3>

            <p
              style={{
                margin: 0,
                color: 'var(--text)',
                lineHeight: 1.6,
              }}
            >
              {confirmModal.message}
            </p>
          </div>

          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '0.8rem',
              padding: '1rem 1.5rem 1.4rem',
            }}
          >
            <button
              type="button"
              className="secondary-btn"
              onClick={closeConfirmModal}
            >
              Cancel
            </button>

            <button
              type="button"
              className={isDangerAction ? 'secondary-btn danger-btn' : 'primary-btn'}
              onClick={handleConfirmModalAction}
            >
              {confirmModal.confirmText}
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div>
      <PageHeader
        title="AI Chat"
        subtitle="Ask questions, review history, and display AI answers returned from the backend."
      />

      <section className="card-like" style={{ marginBottom: '1.5rem' }}>
        <h3>AI Chat Overview</h3>
        <p className="muted">
          The AI Chat module allows users to ask natural language questions and receive fast
          information from the system. Chat sessions are saved in Recents, so users can return
          to previous conversations even after leaving the page.
        </p>
      </section>

      <div
        className="tab-row"
        style={{
          display: 'flex',
          gap: '0.75rem',
          marginBottom: '1.5rem',
          flexWrap: 'wrap',
        }}
      >
        <button
          type="button"
          className={activeTab === 'ask' ? 'primary-btn' : 'secondary-btn'}
          onClick={() => setActiveTab('ask')}
        >
          Ask Question
        </button>

        <button
          type="button"
          className={activeTab === 'history' ? 'primary-btn' : 'secondary-btn'}
          onClick={() => setActiveTab('history')}
        >
          Chat History
        </button>
      </div>

      {activeTab === 'ask' ? renderAskQuestion() : null}
      {activeTab === 'history' ? renderChatHistory() : null}

      {renderConfirmModal()}
    </div>
  );
}