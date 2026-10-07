import { useCallback, useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useLanguage } from '../../i18n/LanguageContext';
import './styles/QuizManagement.css';

const emptyQuizForm = {
  title: '',
  description: '',
  category: 'Training',
  status: 'active',
  difficulty: 'Medium',
};

const emptyQuestionForm = {
  question_text: '',
  option_a: '',
  option_b: '',
  option_c: '',
  option_d: '',
  correct_option: 'A',
  explanation: '',
  points: 1,
};

const aiSourceCategories = ['All', 'SOP', 'PRODUCT', 'SALES', 'Training', 'Notice'];

const emptyAiForm = {
  title: '',
  sourceCategory: 'All',
  articleId: '',
  questionCount: 5,
  difficulty: 'Medium',
};

const aiQuestionCounts = [3, 5, 10];
const aiDifficulties = ['Easy', 'Medium', 'Hard'];

const blankAiQuestion = () => ({
  question: '',
  options: ['', '', '', ''],
  correctAnswerIndex: 0,
  explanation: '',
  sourceTitle: '',
});

const optionLetters = ['A', 'B', 'C', 'D'];

const SERVER_MESSAGE_KEYS = {
  'Failed to generate quiz questions from this article. Please try again or refine article content.': 'qm.err.generateFailed',
  'AI model is not configured. Please configure it in AI Model Settings.': 'qm.srv.notConfigured',
  'No verified Knowledge Base content is available for quiz generation.': 'qm.srv.noContent',
  'AI provider service is not available on this server. Please contact an administrator.': 'qm.srv.unavailable',
  'The selected article could not be found.': 'qm.srv.articleMissing',
};


function Icon({ name, size = 20 }) {
  const props = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.9,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
  };

  if (name === 'sparkles') {
    return (
      <svg {...props}>
        <path d="m12 3 1.4 3.6L17 8l-3.6 1.4L12 13l-1.4-3.6L7 8l3.6-1.4L12 3Z" />
        <path d="m19 14 .8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8L19 14Z" />
        <path d="m5 13 1 2.5L8.5 16 6 17l-1 2.5L4 17l-2.5-1L4 15.5 5 13Z" />
      </svg>
    );
  }

  if (name === 'quiz') {
    return (
      <svg {...props}>
        <rect x="4" y="3" width="16" height="18" rx="3" />
        <path d="M8 8h8M8 12h5M8 16h3" />
      </svg>
    );
  }

  if (name === 'plus') {
    return (
      <svg {...props}>
        <path d="M12 5v14M5 12h14" />
      </svg>
    );
  }

  if (name === 'search') {
    return (
      <svg {...props}>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5" />
      </svg>
    );
  }

  if (name === 'edit') {
    return (
      <svg {...props}>
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L8 18l-4 1 1-4Z" />
      </svg>
    );
  }

  if (name === 'trash') {
    return (
      <svg {...props}>
        <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" />
      </svg>
    );
  }

  if (name === 'arrow') {
    return (
      <svg {...props}>
        <path d="M5 12h14M13 6l6 6-6 6" />
      </svg>
    );
  }

  if (name === 'check') {
    return (
      <svg {...props}>
        <path d="m5 12 4 4L19 6" />
      </svg>
    );
  }

  return (
    <svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12h8" />
    </svg>
  );
}

export default function QuizManagement() {
  const { user } = useAuth();
  const { t, tOr } = useLanguage();
  const catLabel = (category) => tOr(`cat.${category}`, category);
  const localizeDescription = (text) => {
    const match = String(text || '').match(/^AI generated quiz based on the latest verified (.*) content\.$/);
    if (match) return t('quiz.autoDesc', { category: catLabel(match[1]) });
    const plain = String(text || '').match(/^Quiz generated from the latest verified (.*) content\.$/);
    return plain ? t('quiz.autoDescTemplate', { category: catLabel(plain[1]) }) : text;
  };
  const titleLabel = (title) => (title === 'AI Generated Quiz' ? t('qm.defaultAiTitle') : title);

  const [activeTab, setActiveTab] = useState('manage');
  const [searchTerm, setSearchTerm] = useState('');

  const [quizzes, setQuizzes] = useState([]);
  const [selectedQuizId, setSelectedQuizId] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [quizForm, setQuizForm] = useState(emptyQuizForm);
  const [questionForm, setQuestionForm] = useState(emptyQuestionForm);
  const [editingQuizId, setEditingQuizId] = useState(null);
  const [editingQuestionId, setEditingQuestionId] = useState(null);
  const [questionEditorOpen, setQuestionEditorOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [questionLoading, setQuestionLoading] = useState(false);
  const [message, setMessage] = useState('');

  const [aiForm, setAiForm] = useState(emptyAiForm);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiSaving, setAiSaving] = useState(false);
  const [aiError, setAiError] = useState('');
  const [aiPreview, setAiPreview] = useState(null);
  const [aiArticles, setAiArticles] = useState([]);

  const [successModal, setSuccessModal] = useState({
    show: false,
    title: '',
    text: '',
  });

  const selectedQuiz = quizzes.find((quiz) => quiz.quiz_id === selectedQuizId);

  const filteredQuizzes = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();

    if (!keyword) return quizzes;

    return quizzes.filter((quiz) => {
      const title = String(quiz.title || '').toLowerCase();
      const category = String(quiz.category || '').toLowerCase();
      const status = String(quiz.status || '').toLowerCase();
      const difficulty = String(quiz.difficulty || '').toLowerCase();

      return (
        title.includes(keyword) ||
        category.includes(keyword) ||
        status.includes(keyword) ||
        difficulty.includes(keyword)
      );
    });
  }, [quizzes, searchTerm]);

  const quizStats = useMemo(() => {
    const active = quizzes.filter((quiz) => quiz.status === 'active').length;
    const draft = quizzes.filter((quiz) => quiz.status !== 'active').length;
    const questionTotal = quizzes.reduce(
      (sum, quiz) => sum + Number(quiz.question_count || 0),
      0
    );

    return {
      total: quizzes.length,
      active,
      draft,
      questionTotal,
    };
  }, [quizzes]);

  const showSuccessModal = (title, text) => {
    setSuccessModal({ show: true, title, text });
  };

  const closeSuccessModal = () => {
    setSuccessModal({ show: false, title: '', text: '' });
  };

  const fetchQuizzes = useCallback(async () => {
    try {
      setLoading(true);

      const response = await api.get('/admin/quizzes');
      const data = Array.isArray(response.data) ? response.data : [];

      setQuizzes(data);

      setSelectedQuizId((currentId) => {
        if (currentId && data.some((quiz) => quiz.quiz_id === currentId)) {
          return currentId;
        }

        return data.length > 0 ? data[0].quiz_id : null;
      });
    } catch (error) {
      console.error('Fetch admin quizzes error:', error.response?.data || error);
      setMessage(
        error.response?.data?.error ||
          error.response?.data?.message ||
          t('qm.err.loadQuizzes')
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchQuestions = async (quizId) => {
    if (!quizId) {
      setQuestions([]);
      return;
    }

    try {
      setQuestionLoading(true);

      const response = await api.get(`/admin/quizzes/${quizId}/questions`);
      const data = Array.isArray(response.data) ? response.data : [];

      setQuestions(data);
    } catch (error) {
      console.error('Fetch quiz questions error:', error.response?.data || error);
      setMessage(
        error.response?.data?.error ||
          error.response?.data?.message ||
          t('qm.err.loadQuestions')
      );
    } finally {
      setQuestionLoading(false);
    }
  };

  useEffect(() => {
    fetchQuizzes();
  }, [fetchQuizzes]);

  useEffect(() => {
    if (activeTab !== 'ai-generate' || aiArticles.length > 0) return;

    api
      .get('/admin/quizzes/source-articles')
      .then((response) =>
        setAiArticles(Array.isArray(response.data) ? response.data : [])
      )
      .catch((error) => {
        console.error('Load quiz source articles error:', error.response?.data || error);
      });
  }, [activeTab, aiArticles.length]);

  useEffect(() => {
    if (selectedQuizId && activeTab === 'manage') {
      fetchQuestions(selectedQuizId);
    }
  }, [selectedQuizId, activeTab]);

  const handleQuizChange = (event) => {
    const { name, value } = event.target;
    setQuizForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleQuestionChange = (event) => {
    const { name, value } = event.target;
    setQuestionForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSelectQuiz = (quizId) => {
    setSelectedQuizId(quizId);
    setEditingQuestionId(null);
    setQuestionForm(emptyQuestionForm);
    setQuestionEditorOpen(false);
    setActiveTab('manage');
  };

  const clearQuizForm = () => {
    setQuizForm(emptyQuizForm);
    setEditingQuizId(null);
  };

  const startCreateQuiz = () => {
    clearQuizForm();
    setMessage('');
    setActiveTab('create');
  };

  const resetQuestionForm = () => {
    setQuestionForm(emptyQuestionForm);
    setEditingQuestionId(null);
    setQuestionEditorOpen(false);
  };

  const submitQuiz = async (event) => {
    event.preventDefault();

    if (!quizForm.title.trim()) {
      setMessage(t('qm.err.enterTitle'));
      return;
    }

    try {
      setMessage('');

      const payload = {
        ...quizForm,
        created_by: user?.id || user?.user_id || null,
      };

      if (editingQuizId) {
        await api.put(`/admin/quizzes/${editingQuizId}`, payload);
        showSuccessModal(t('qm.ok.updatedTitle'), t('qm.ok.changesSaved'));
        setSelectedQuizId(editingQuizId);
      } else {
        const response = await api.post('/admin/quizzes', payload);
        showSuccessModal(t('qm.ok.createdTitle'), t('qm.ok.createdText'));

        if (response.data?.quiz_id) {
          setSelectedQuizId(response.data.quiz_id);
        }
      }

      clearQuizForm();
      await fetchQuizzes();
      setActiveTab('manage');
    } catch (error) {
      console.error('Submit quiz error:', error.response?.data || error);
      setMessage(
        error.response?.data?.error ||
          error.response?.data?.message ||
          t('qm.err.saveQuiz')
      );
    }
  };

  const editQuiz = (quiz) => {
    setEditingQuizId(quiz.quiz_id);
    setQuizForm({
      title: quiz.title || '',
      description: quiz.description || '',
      category: quiz.category || 'Training',
      status: quiz.status || 'active',
      difficulty: quiz.difficulty || 'Medium',
    });
    setActiveTab('create');
  };

  const deleteQuiz = async (quizId) => {
    const confirmDelete = window.confirm(t('qm.confirm.deleteQuiz'));

    if (!confirmDelete) return;

    try {
      setMessage('');

      await api.delete(`/admin/quizzes/${quizId}`);

      if (selectedQuizId === quizId) {
        setSelectedQuizId(null);
        setQuestions([]);
      }

      setMessage(t('qm.ok.deleted'));
      await fetchQuizzes();
    } catch (error) {
      console.error('Delete quiz error:', error.response?.data || error);
      setMessage(
        error.response?.data?.error ||
          error.response?.data?.message ||
          t('qm.err.deleteQuiz')
      );
    }
  };

  const submitQuestion = async (event) => {
    event.preventDefault();

    if (!selectedQuizId) {
      setMessage(t('qm.err.selectFirst'));
      return;
    }

    if (
      !questionForm.question_text.trim() ||
      !questionForm.option_a.trim() ||
      !questionForm.option_b.trim() ||
      !questionForm.option_c.trim() ||
      !questionForm.option_d.trim()
    ) {
      setMessage(t('qm.err.completeQuestion'));
      return;
    }

    try {
      setMessage('');

      if (editingQuestionId) {
        await api.put(`/admin/questions/${editingQuestionId}`, questionForm);
        showSuccessModal(t('qm.ok.questionUpdated'), t('qm.ok.changesSaved'));
      } else {
        await api.post(
          `/admin/quizzes/${selectedQuizId}/questions`,
          questionForm
        );
        showSuccessModal(t('qm.ok.questionAdded'), t('qm.ok.questionAddedText'));
      }

      resetQuestionForm();
      await Promise.all([
        fetchQuestions(selectedQuizId),
        fetchQuizzes(),
      ]);
    } catch (error) {
      console.error('Submit question error:', error.response?.data || error);
      setMessage(
        error.response?.data?.error ||
          error.response?.data?.message ||
          t('qm.err.saveQuestion')
      );
    }
  };

  const editQuestion = (question) => {
    setEditingQuestionId(question.question_id || question.id);
    setQuestionForm({
      question_text: question.question_text || question.question || '',
      option_a: question.option_a || '',
      option_b: question.option_b || '',
      option_c: question.option_c || '',
      option_d: question.option_d || '',
      correct_option: question.correct_option || 'A',
      explanation: question.explanation || '',
      points: question.points || 1,
    });
    setQuestionEditorOpen(true);
  };

  const deleteQuestion = async (questionId) => {
    if (!window.confirm(t('qm.confirm.deleteQuestion'))) return;

    try {
      setMessage('');

      await api.delete(`/admin/questions/${questionId}`);

      setMessage(t('qm.ok.questionDeleted'));
      await Promise.all([
        fetchQuestions(selectedQuizId),
        fetchQuizzes(),
      ]);
    } catch (error) {
      console.error('Delete question error:', error.response?.data || error);
      setMessage(
        error.response?.data?.error ||
          error.response?.data?.message ||
          t('qm.err.deleteQuestion')
      );
    }
  };

  const handleAiFormChange = (event) => {
    const { name, value } = event.target;
    setAiForm((prev) => ({ ...prev, [name]: value }));
  };

  const generateAiQuiz = async (event) => {
    event.preventDefault();

    setAiError('');
    setAiPreview(null);

    try {
      setAiLoading(true);

      const chosenArticle = aiArticles.find(
        (article) => String(article.article_id) === String(aiForm.articleId)
      );

      const response = await api.post(
        '/admin/quizzes/ai-generate',
        {
          title:
            aiForm.title.trim() ||
            (chosenArticle ? t('qm.titleSuffix', { title: chosenArticle.title }) : t('qm.defaultAiTitle')),
          sourceCategory: aiForm.sourceCategory,
          articleId: aiForm.articleId ? Number(aiForm.articleId) : null,
          count: Number(aiForm.questionCount) || 5,
          difficulty: aiForm.difficulty,
          status: 'inactive',
        },
        { timeout: 150000 }
      );

      setAiPreview(response.data?.quiz || null);
    } catch (error) {
      console.error('AI generate quiz error:', error.response?.data || error);

      let fallbackMessage = t('qm.err.generateFailed');

      if (error.code === 'ECONNABORTED' || !error.response) {
        fallbackMessage = t('qm.err.aiFailed');
      }

      const serverMessage = error.response?.data?.message;
      setAiError(
        serverMessage
          ? (SERVER_MESSAGE_KEYS[serverMessage] ? t(SERVER_MESSAGE_KEYS[serverMessage]) : serverMessage)
          : fallbackMessage
      );
    } finally {
      setAiLoading(false);
    }
  };

  const updateAiQuestion = (index, changes) => {
    setAiPreview((prev) =>
      prev
        ? {
            ...prev,
            questions: prev.questions.map((item, i) =>
              i === index ? { ...item, ...changes } : item
            ),
          }
        : prev
    );
  };

  const updateAiOption = (index, optionIndex, value) => {
    setAiPreview((prev) =>
      prev
        ? {
            ...prev,
            questions: prev.questions.map((item, i) =>
              i === index
                ? {
                    ...item,
                    options: item.options.map((option, o) =>
                      o === optionIndex ? value : option
                    ),
                  }
                : item
            ),
          }
        : prev
    );
  };

  const addAiPreviewQuestion = () => {
    setAiPreview((prev) =>
      prev ? { ...prev, questions: [...prev.questions, blankAiQuestion()] } : prev
    );
  };

  const removeAiPreviewQuestion = (index) => {
    setAiPreview((prev) => {
      if (!prev) return prev;

      return {
        ...prev,
        questions: prev.questions.filter((_, i) => i !== index),
      };
    });
  };

  const cancelAiPreview = () => {
    setAiPreview(null);
    setAiError('');
  };

  // One request saves the quiz and every question in a single DB transaction.
  const saveAiGeneratedQuiz = async (publish) => {
    if (!aiPreview || aiPreview.questions.length === 0) {
      setAiError(t('quiz.edit.noQuestions'));
      return;
    }

    const incomplete = aiPreview.questions.some(
      (question) =>
        !question.question.trim() ||
        question.options.length !== 4 ||
        question.options.some((option) => !String(option).trim())
    );

    if (incomplete) {
      setAiError(t('quiz.edit.incomplete'));
      return;
    }

    try {
      setAiSaving(true);
      setAiError('');

      const quizResponse = await api.post('/admin/quizzes', {
        title: aiPreview.title,
        description: aiPreview.description,
        category: aiPreview.category,
        status: publish ? 'active' : 'inactive',
        difficulty: aiPreview.difficulty,
        source_article_id: aiPreview.sourceArticleId || null,
        created_by: user?.id || user?.user_id || null,
        questions: aiPreview.questions.map((question) => ({
          question_text: question.question.trim(),
          option_a: question.options[0].trim(),
          option_b: question.options[1].trim(),
          option_c: question.options[2].trim(),
          option_d: question.options[3].trim(),
          correct_option: optionLetters[question.correctAnswerIndex] || 'A',
          explanation: (question.explanation || '').trim(),
        })),
      });

      const newQuizId = quizResponse.data?.quiz_id;

      showSuccessModal(
        publish ? t('quiz.status.published') : t('quiz.status.draft'),
        publish ? t('quiz.edit.published') : t('quiz.edit.savedDraft')
      );

      setAiPreview(null);
      setAiForm(emptyAiForm);

      if (newQuizId) {
        setSelectedQuizId(newQuizId);
      }

      await fetchQuizzes();
      setActiveTab('manage');
    } catch (error) {
      console.error(
        'Save AI generated quiz error:',
        error.response?.data || error
      );
      setAiError(
        error.response?.data?.message ||
          error.response?.data?.error ||
          t('qm.err.saveAi')
      );
    } finally {
      setAiSaving(false);
    }
  };

  return (
    <div className="qm-page">
      <div className="qm-heading-row">
        <PageHeader
          title={t('qm.title')}
          subtitle={t('qm.subtitle')}
        />

        <div className="qm-heading-actions">
          <button
            type="button"
            className="qm-btn qm-btn-ai"
            onClick={() => {
              setAiError('');
              setActiveTab('ai-generate');
            }}
          >
            <Icon name="sparkles" />
            {t('qm.aiGenerate')}
          </button>

          <button
            type="button"
            className="qm-btn qm-btn-primary"
            onClick={startCreateQuiz}
          >
            <Icon name="plus" />
            {t('qm.newQuiz')}
          </button>
        </div>
      </div>

      <section className="qm-stats">
        <button
          type="button"
          className="qm-stat qm-stat-blue"
          onClick={() => setActiveTab('manage')}
        >
          <span>{t('qm.totalQuizzes')}</span>
          <strong>{quizStats.total}</strong>
        </button>

        <button
          type="button"
          className="qm-stat qm-stat-green"
          onClick={() => setActiveTab('manage')}
        >
          <span>{t('quiz.status.published')}</span>
          <strong>{quizStats.active}</strong>
        </button>

        <button
          type="button"
          className="qm-stat qm-stat-amber"
          onClick={() => setActiveTab('manage')}
        >
          <span>{t('quiz.status.draft')}</span>
          <strong>{quizStats.draft}</strong>
        </button>

        <div className="qm-stat qm-stat-violet">
          <span>{t('qm.questionsStat')}</span>
          <strong>{quizStats.questionTotal}</strong>
        </div>
      </section>

      {message ? <div className="qm-feedback">{message}</div> : null}

      <section className="qm-workspace">
        <div className="qm-nav">
          <button
            type="button"
            className={activeTab === 'manage' ? 'active' : ''}
            onClick={() => setActiveTab('manage')}
          >
            <Icon name="quiz" size={18} />
            {t('qm.tab.quizzes')}
          </button>

          <button
            type="button"
            className={activeTab === 'create' ? 'active' : ''}
            onClick={startCreateQuiz}
          >
            <Icon name="plus" size={18} />
            {editingQuizId ? t('qm.tab.edit') : t('qm.tab.create')}
          </button>

          <button
            type="button"
            className={`qm-nav-ai ${activeTab === 'ai-generate' ? 'active' : ''}`}
            onClick={() => setActiveTab('ai-generate')}
          >
            <Icon name="sparkles" size={18} />
            {t('qm.tab.ai')}
          </button>
        </div>

        {activeTab === 'manage' ? (
          <div className="qm-manage">
            <aside className="qm-library">
              <div className="qm-section-head">
                <div>
                  <span className="qm-kicker">{t('qm.library')}</span>
                  <h2>{t('qm.tab.quizzes')}</h2>
                </div>

                <span className="qm-count-badge">{filteredQuizzes.length}</span>
              </div>

              <div className="qm-search">
                <Icon name="search" size={17} />
                <input
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder={t('quiz.mgmt.searchPlaceholder')}
                />
              </div>

              {loading ? (
                <div className="qm-empty">{t('qm.loading')}</div>
              ) : filteredQuizzes.length === 0 ? (
                <div className="qm-empty">
                  <strong>{t('qm.noQuizzes')}</strong>
                  <button
                    type="button"
                    className="qm-btn qm-btn-primary"
                    onClick={startCreateQuiz}
                  >
                    {t('qm.createQuiz')}
                  </button>
                </div>
              ) : (
                <div className="qm-quiz-list">
                  {filteredQuizzes.map((quiz, index) => (
                    <article
                      key={quiz.quiz_id}
                      className={`qm-quiz-card qm-color-${index % 5} ${
                        selectedQuizId === quiz.quiz_id ? 'selected' : ''
                      }`}
                      onClick={() => handleSelectQuiz(quiz.quiz_id)}
                    >
                      <div className="qm-quiz-card-top">
                        <div className="qm-quiz-icon">
                          <Icon name="quiz" />
                        </div>

                        <span
                          className={`qm-status ${
                            quiz.status === 'active' ? 'active' : 'draft'
                          }`}
                        >
                          {quiz.status === 'active'
                            ? t('quiz.status.published')
                            : t('quiz.status.draft')}
                        </span>
                      </div>

                      <h3>{titleLabel(quiz.title)}</h3>

                      <div className="qm-quiz-meta">
                        <span>{catLabel(quiz.category || 'Training')}</span>
                        <span className={`qm-diff qm-diff-${String(quiz.difficulty || 'Medium').toLowerCase()}`}>
                          {tOr(`quiz.difficulty.${quiz.difficulty || 'Medium'}`, quiz.difficulty)}
                        </span>
                        <span>{t('qm.nQuestions', { n: quiz.question_count || 0 })}</span>
                      </div>

                      <div className="qm-card-actions">
                        <button
                          type="button"
                          className="qm-mini-action"
                          onClick={(event) => {
                            event.stopPropagation();
                            editQuiz(quiz);
                          }}
                          aria-label={t('qm.editAria', { title: quiz.title })}
                        >
                          <Icon name="edit" size={16} />
                        </button>

                        <button
                          type="button"
                          className="qm-mini-action danger"
                          onClick={(event) => {
                            event.stopPropagation();
                            deleteQuiz(quiz.quiz_id);
                          }}
                          aria-label={t('qm.deleteAria', { title: quiz.title })}
                        >
                          <Icon name="trash" size={16} />
                        </button>

                        <span className="qm-open-link">
                          {t('qm.open')} <Icon name="arrow" size={15} />
                        </span>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </aside>

            <main className="qm-detail">
              {!selectedQuiz ? (
                <div className="qm-empty qm-empty-large">
                  <div className="qm-empty-icon">
                    <Icon name="quiz" size={28} />
                  </div>
                  <strong>{t('qm.selectQuiz')}</strong>
                  <span>{t('qm.selectQuizHint')}</span>
                </div>
              ) : (
                <>
                  <div className="qm-detail-hero">
                    <div>
                      <div className="qm-detail-tags">
                        <span className="qm-pill qm-pill-blue">
                          {catLabel(selectedQuiz.category || 'Training')}
                        </span>
                        <span
                          className={`qm-pill ${
                            selectedQuiz.status === 'active'
                              ? 'qm-pill-green'
                              : 'qm-pill-amber'
                          }`}
                        >
                          {selectedQuiz.status === 'active'
                            ? t('quiz.status.published')
                            : t('quiz.status.draft')}
                        </span>
                      </div>

                      <h2>{titleLabel(selectedQuiz.title)}</h2>

                      {selectedQuiz.description ? (
                        <p>{localizeDescription(selectedQuiz.description)}</p>
                      ) : null}
                    </div>

                    <button
                      type="button"
                      className="qm-btn qm-btn-primary"
                      onClick={() => {
                        setEditingQuestionId(null);
                        setQuestionForm(emptyQuestionForm);
                        setQuestionEditorOpen(true);
                      }}
                    >
                      <Icon name="plus" size={17} />
                      {t('qm.addQuestionBtn')}
                    </button>
                  </div>

                  <div className="qm-mini-stats">
                    <div>
                      <span>{t('qm.questionsStat')}</span>
                      <strong>{selectedQuiz.question_count || questions.length || 0}</strong>
                    </div>
                    <div>
                      <span>{t('qm.stat.category')}</span>
                      <strong>{catLabel(selectedQuiz.category || 'Training')}</strong>
                    </div>
                    <div>
                      <span>{t('qm.stat.status')}</span>
                      <strong>
                        {selectedQuiz.status === 'active'
                          ? t('quiz.status.published')
                          : t('quiz.status.draft')}
                      </strong>
                    </div>
                  </div>

                  {questionEditorOpen ? (
                    <form className="qm-question-editor" onSubmit={submitQuestion}>
                      <div className="qm-section-head">
                        <div>
                          <span className="qm-kicker">
                            {editingQuestionId ? t('qm.editor.editing') : t('qm.editor.new')}
                          </span>
                          <h3>
                            {editingQuestionId ? t('qm.editor.editQuestion') : t('qm.editor.addQuestion')}
                          </h3>
                        </div>

                        <button
                          type="button"
                          className="qm-icon-close"
                          onClick={resetQuestionForm}
                          aria-label={t('qm.editor.closeAria')}
                        >
                          ×
                        </button>
                      </div>

                      <label className="qm-field qm-field-full">
                        <span>{t('quiz.edit.question')}</span>
                        <textarea
                          rows="3"
                          name="question_text"
                          value={questionForm.question_text}
                          onChange={handleQuestionChange}
                          placeholder={t('qm.editor.enterQuestion')}
                        />
                      </label>

                      <div className="qm-option-grid">
                        {optionLetters.map((letter) => (
                          <label key={letter} className="qm-field">
                            <span>{t('quiz.edit.option', { letter })}</span>
                            <input
                              name={`option_${letter.toLowerCase()}`}
                              value={
                                questionForm[`option_${letter.toLowerCase()}`]
                              }
                              onChange={handleQuestionChange}
                              placeholder={t('quiz.edit.option', { letter })}
                            />
                          </label>
                        ))}
                      </div>

                      <div className="qm-editor-bottom-grid">
                        <label className="qm-field">
                          <span>{t('qm.editor.correct')}</span>
                          <select
                            name="correct_option"
                            value={questionForm.correct_option}
                            onChange={handleQuestionChange}
                          >
                            {optionLetters.map((letter) => (
                              <option key={letter} value={letter}>
                                {letter}
                              </option>
                            ))}
                          </select>
                        </label>

                        <label className="qm-field">
                          <span>{t('qm.editor.points')}</span>
                          <input
                            type="number"
                            min="1"
                            name="points"
                            value={questionForm.points}
                            onChange={handleQuestionChange}
                          />
                        </label>
                      </div>

                      <label className="qm-field qm-field-full">
                        <span>{t('quiz.edit.explanation')}</span>
                        <textarea
                          rows="2"
                          name="explanation"
                          value={questionForm.explanation}
                          onChange={handleQuestionChange}
                          placeholder={t('qm.editor.optional')}
                        />
                      </label>

                      <div className="qm-form-actions">
                        <button
                          type="button"
                          className="qm-btn qm-btn-soft"
                          onClick={resetQuestionForm}
                        >
                          {t('qm.editor.cancel')}
                        </button>

                        <button
                          type="submit"
                          className="qm-btn qm-btn-primary"
                        >
                          {editingQuestionId ? t('qm.editor.saveChanges') : t('qm.editor.addQuestion')}
                        </button>
                      </div>
                    </form>
                  ) : null}

                  <div className="qm-question-section">
                    <div className="qm-section-head">
                      <div>
                        <span className="qm-kicker">{t('qm.bank')}</span>
                        <h3>{t('qm.nQuestionsHeading', { n: questions.length })}</h3>
                      </div>
                    </div>

                    {questionLoading ? (
                      <div className="qm-empty">{t('qm.loadingQuestions')}</div>
                    ) : questions.length === 0 ? (
                      <div className="qm-empty qm-empty-soft">
                        <strong>{t('qm.noQuestionsYet')}</strong>
                        <button
                          type="button"
                          className="qm-btn qm-btn-primary"
                          onClick={() => setQuestionEditorOpen(true)}
                        >
                          {t('qm.editor.addQuestion')}
                        </button>
                      </div>
                    ) : (
                      <div className="qm-question-list">
                        {questions.map((question, index) => (
                          <article
                            key={question.question_id || question.id}
                            className="qm-question-card"
                          >
                            <div className="qm-question-number">
                              {String(index + 1).padStart(2, '0')}
                            </div>

                            <div className="qm-question-copy">
                              <h4>
                                {question.question_text || question.question}
                              </h4>

                              <div className="qm-question-meta">
                                <span className="qm-pill qm-pill-green">
                                  {t('qm.answerLetter', { letter: question.correct_option })}
                                </span>
                                <span>{t('qm.pt', { n: question.points || 1 })}</span>
                              </div>
                            </div>

                            <div className="qm-question-actions">
                              <button
                                type="button"
                                className="qm-mini-action"
                                onClick={() => editQuestion(question)}
                                aria-label={t('qm.editQuestionAria')}
                              >
                                <Icon name="edit" size={16} />
                              </button>

                              <button
                                type="button"
                                className="qm-mini-action danger"
                                onClick={() =>
                                  deleteQuestion(
                                    question.question_id || question.id
                                  )
                                }
                                aria-label={t('qm.deleteQuestionAria')}
                              >
                                <Icon name="trash" size={16} />
                              </button>
                            </div>
                          </article>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              )}
            </main>
          </div>
        ) : null}

        {activeTab === 'create' ? (
          <div className="qm-create-layout">
            <section className="qm-create-card">
              <div className="qm-section-head">
                <div>
                  <span className="qm-kicker">
                    {editingQuizId ? t('qm.tab.edit') : t('qm.form.newQuiz')}
                  </span>
                  <h2>
                    {editingQuizId ? t('qm.form.update') : t('qm.form.create')}
                  </h2>
                </div>

                <div className="qm-create-icon">
                  <Icon name="quiz" size={24} />
                </div>
              </div>

              <form className="qm-form" onSubmit={submitQuiz}>
                <label className="qm-field qm-field-full">
                  <span>{t('qm.form.title')}</span>
                  <input
                    name="title"
                    value={quizForm.title}
                    onChange={handleQuizChange}
                    placeholder={t('qm.form.titlePh')}
                  />
                </label>

                <label className="qm-field qm-field-full">
                  <span>{t('qm.form.description')}</span>
                  <textarea
                    rows="3"
                    name="description"
                    value={quizForm.description}
                    onChange={handleQuizChange}
                    placeholder={t('qm.form.descriptionPh')}
                  />
                </label>

                <div className="qm-form-grid">
                  <label className="qm-field">
                    <span>{t('qm.form.category')}</span>
                    <input
                      name="category"
                      value={quizForm.category}
                      onChange={handleQuizChange}
                      placeholder="Training"
                    />
                  </label>

                  <label className="qm-field">
                    <span>{t('qm.form.status')}</span>
                    <select
                      name="status"
                      value={quizForm.status}
                      onChange={handleQuizChange}
                    >
                      <option value="active">{t('quiz.status.published')}</option>
                      <option value="inactive">{t('quiz.status.draft')}</option>
                    </select>
                  </label>
                </div>

                <label className="qm-field">
                  <span>{t('quiz.gen.difficulty')}</span>
                  <select
                    name="difficulty"
                    value={quizForm.difficulty}
                    onChange={handleQuizChange}
                  >
                    {aiDifficulties.map((level) => (
                      <option key={level} value={level}>
                        {t(`quiz.difficulty.${level}`)}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="qm-form-actions">
                  {editingQuizId ? (
                    <button
                      type="button"
                      className="qm-btn qm-btn-soft"
                      onClick={startCreateQuiz}
                    >
                      {t('qm.editor.cancel')}
                    </button>
                  ) : null}

                  <button
                    type="submit"
                    className="qm-btn qm-btn-primary"
                  >
                    {editingQuizId ? t('qm.editor.saveChanges') : t('qm.form.createBtn')}
                  </button>
                </div>
              </form>
            </section>

            <aside className="qm-create-side">
              <div className="qm-side-orb qm-side-orb-blue">
                <Icon name="quiz" size={26} />
              </div>
              <h3>{t('qm.manual')}</h3>
              <p>{t('qm.manualHint')}</p>

              <button
                type="button"
                className="qm-side-ai"
                onClick={() => setActiveTab('ai-generate')}
              >
                <span className="qm-side-orb qm-side-orb-violet">
                  <Icon name="sparkles" size={20} />
                </span>
                <span>
                  <strong>{t('qm.useAi')}</strong>
                  <small>{t('qm.useAiHint')}</small>
                </span>
                <Icon name="arrow" size={18} />
              </button>
            </aside>
          </div>
        ) : null}

        {activeTab === 'ai-generate' ? (
          <div className="qm-ai-layout">
            <section className="qm-ai-builder">
              <div className="qm-ai-head">
                <div className="qm-ai-icon">
                  <Icon name="sparkles" size={25} />
                </div>

                <div>
                  <span>{t('qm.ai.kicker')}</span>
                  <h2>{t('qm.ai.heading')}</h2>
                </div>
              </div>

              <form className="qm-ai-form" onSubmit={generateAiQuiz}>
                <label className="qm-field qm-field-full">
                  <span>{t('qm.ai.quizTitle')}</span>
                  <input
                    name="title"
                    value={aiForm.title}
                    onChange={handleAiFormChange}
                    placeholder={t('qm.ai.titlePh')}
                  />
                </label>

                <label className="qm-field qm-field-full">
                  <span>{t('quiz.gen.article')}</span>
                  <select
                    name="articleId"
                    value={aiForm.articleId}
                    onChange={handleAiFormChange}
                  >
                    <option value="">{t('quiz.gen.allKnowledge')}</option>
                    {aiArticles.map((article) => (
                      <option key={article.article_id} value={article.article_id}>
                        {article.title}
                      </option>
                    ))}
                  </select>
                </label>

                {!aiForm.articleId ? (
                  <label className="qm-field qm-field-full">
                    <span>{t('qm.ai.category')}</span>
                    <select
                      name="sourceCategory"
                      value={aiForm.sourceCategory}
                      onChange={handleAiFormChange}
                    >
                      {aiSourceCategories.map((category) => (
                        <option key={category} value={category}>
                          {category === 'All' ? t('qm.ai.allKnowledge') : catLabel(category)}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}

                <div className="qm-field qm-field-full">
                  <span>{t('quiz.gen.count')}</span>
                  <div className="qm-chip-row" role="radiogroup">
                    {aiQuestionCounts.map((count) => (
                      <button
                        key={count}
                        type="button"
                        role="radio"
                        aria-checked={Number(aiForm.questionCount) === count}
                        className={`qm-chip ${
                          Number(aiForm.questionCount) === count ? 'active' : ''
                        }`}
                        onClick={() =>
                          setAiForm((prev) => ({ ...prev, questionCount: count }))
                        }
                      >
                        {count}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="qm-field qm-field-full">
                  <span>{t('quiz.gen.difficulty')}</span>
                  <div className="qm-chip-row" role="radiogroup">
                    {aiDifficulties.map((level) => (
                      <button
                        key={level}
                        type="button"
                        role="radio"
                        aria-checked={aiForm.difficulty === level}
                        className={`qm-chip qm-chip-${level.toLowerCase()} ${
                          aiForm.difficulty === level ? 'active' : ''
                        }`}
                        onClick={() =>
                          setAiForm((prev) => ({ ...prev, difficulty: level }))
                        }
                      >
                        {t(`quiz.difficulty.${level}`)}
                      </button>
                    ))}
                  </div>
                  <small className="qm-chip-hint">
                    {t(`quiz.gen.hint.${aiForm.difficulty}`)}
                  </small>
                </div>

                <button
                  className="qm-btn qm-btn-ai qm-generate-btn"
                  type="submit"
                  disabled={aiLoading}
                >
                  <Icon name="sparkles" />
                  {aiLoading ? t('quiz.gen.generating') : t('quiz.gen.generate')}
                </button>
              </form>

              {aiError ? <div className="qm-ai-error">{aiError}</div> : null}
            </section>

            <section className="qm-ai-preview">
              {aiLoading ? (
                <div className="qm-ai-skeleton" role="status" aria-live="polite">
                  <strong>{t('quiz.gen.generating')}</strong>
                  {Array.from({ length: Math.min(Number(aiForm.questionCount) || 3, 3) }).map(
                    (_, index) => (
                      <div key={index} className="qm-skel-card">
                        <span className="qm-skel-line wide" />
                        <span className="qm-skel-line" />
                        <span className="qm-skel-line" />
                        <span className="qm-skel-line short" />
                      </div>
                    )
                  )}
                </div>
              ) : !aiPreview ? (
                <div className="qm-ai-empty">
                  <div className="qm-ai-empty-orb">
                    <Icon name="sparkles" size={30} />
                  </div>
                  <strong>{t('qm.ai.previewTitle')}</strong>
                  <span>{t('qm.ai.previewHint')}</span>
                </div>
              ) : (
                <>
                  <div className="qm-ai-preview-head">
                    <div>
                      <div className="qm-detail-tags">
                        <span className="qm-pill qm-pill-violet">
                          {aiPreview.generationMethod === 'ai_provider'
                            ? t('qm.ai.generated')
                            : t('qm.ai.template')}
                        </span>
                        <span className="qm-pill qm-pill-blue">
                          {aiPreview.sourceArticleTitle || catLabel(aiPreview.category)}
                        </span>
                        <span className={`qm-pill qm-diff qm-diff-${String(aiPreview.difficulty || 'Medium').toLowerCase()}`}>
                          {tOr(`quiz.difficulty.${aiPreview.difficulty}`, aiPreview.difficulty)}
                        </span>
                        <span className="qm-pill qm-pill-amber">{t('quiz.status.draft')}</span>
                      </div>

                      <input
                        className="qm-ai-title-input"
                        value={aiPreview.title}
                        onChange={(event) =>
                          setAiPreview((prev) => ({ ...prev, title: event.target.value }))
                        }
                        aria-label={t('qm.ai.titleAria')}
                      />
                      <p>
                        {aiPreview.questions.length} {t('quiz.questions')}
                      </p>
                    </div>

                    <div className="qm-ai-preview-actions">
                      <button
                        type="button"
                        className="qm-btn qm-btn-soft"
                        onClick={cancelAiPreview}
                        disabled={aiSaving}
                      >
                        {t('quiz.edit.discard')}
                      </button>

                      <button
                        type="button"
                        className="qm-btn qm-btn-soft"
                        onClick={() => saveAiGeneratedQuiz(false)}
                        disabled={aiSaving || aiPreview.questions.length === 0}
                      >
                        {t('quiz.edit.saveDraft')}
                      </button>

                      <button
                        type="button"
                        className="qm-btn qm-btn-primary"
                        onClick={() => saveAiGeneratedQuiz(true)}
                        disabled={aiSaving || aiPreview.questions.length === 0}
                      >
                        {aiSaving ? '...' : t('quiz.edit.publish')}
                      </button>
                    </div>
                  </div>

                  <div className="qm-ai-question-list">
                    {aiPreview.questions.map((question, index) => (
                      <article key={index} className="qm-ai-question qm-ai-edit">
                        <div className="qm-ai-question-head">
                          <span>Q{index + 1}</span>
                          <button
                            type="button"
                            className="qm-mini-action danger"
                            onClick={() => removeAiPreviewQuestion(index)}
                            disabled={aiSaving}
                            aria-label={t('quiz.edit.delete')}
                          >
                            <Icon name="trash" size={15} />
                          </button>
                        </div>

                        <label className="qm-field qm-field-full">
                          <span>{t('quiz.edit.question')}</span>
                          <textarea
                            rows="2"
                            value={question.question}
                            onChange={(event) =>
                              updateAiQuestion(index, { question: event.target.value })
                            }
                          />
                        </label>

                        <div className="qm-ai-edit-options" role="radiogroup" aria-label={t('quiz.edit.correct')}>
                          {question.options.map((option, optionIndex) => (
                            <div
                              key={optionIndex}
                              className={`qm-ai-edit-option ${
                                optionIndex === question.correctAnswerIndex ? 'correct' : ''
                              }`}
                            >
                              <input
                                type="radio"
                                name={`correct-${index}`}
                                checked={optionIndex === question.correctAnswerIndex}
                                onChange={() =>
                                  updateAiQuestion(index, { correctAnswerIndex: optionIndex })
                                }
                                aria-label={`${t('quiz.edit.correct')}: ${optionLetters[optionIndex]}`}
                              />
                              <span className="qm-ai-edit-letter">{optionLetters[optionIndex]}</span>
                              <input
                                className="qm-ai-edit-input"
                                value={option}
                                onChange={(event) =>
                                  updateAiOption(index, optionIndex, event.target.value)
                                }
                                aria-label={t('quiz.edit.option', { letter: optionLetters[optionIndex] })}
                                placeholder={t('quiz.edit.option', { letter: optionLetters[optionIndex] })}
                              />
                            </div>
                          ))}
                        </div>

                        <label className="qm-field qm-field-full">
                          <span>{t('quiz.edit.explanation')}</span>
                          <textarea
                            rows="2"
                            value={question.explanation}
                            onChange={(event) =>
                              updateAiQuestion(index, { explanation: event.target.value })
                            }
                          />
                        </label>
                      </article>
                    ))}

                    <button
                      type="button"
                      className="qm-btn qm-btn-soft qm-add-question"
                      onClick={addAiPreviewQuestion}
                      disabled={aiSaving}
                    >
                      <Icon name="plus" size={16} />
                      {t('quiz.edit.addQuestion')}
                    </button>
                  </div>
                </>
              )}
            </section>
          </div>
        ) : null}
      </section>

      {successModal.show ? (
        <div className="qm-modal-overlay">
          <div className="qm-modal">
            <div className="qm-modal-check">
              <Icon name="check" size={27} />
            </div>

            <h2>{successModal.title}</h2>
            <p>{successModal.text}</p>

            <button
              type="button"
              className="qm-btn qm-btn-primary"
              onClick={closeSuccessModal}
            >
              {t('qm.done')}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
