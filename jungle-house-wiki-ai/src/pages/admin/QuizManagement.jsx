import { useCallback, useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import './styles/QuizManagement.css';

const emptyQuizForm = {
  title: '',
  description: '',
  category: 'Training',
  status: 'active',
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
  questionCount: 5,
  difficulty: 'intermediate',
  status: 'active',
};

const optionLetters = ['A', 'B', 'C', 'D'];

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

      return (
        title.includes(keyword) ||
        category.includes(keyword) ||
        status.includes(keyword)
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
          'Failed to load quizzes.'
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
          'Failed to load quiz questions.'
      );
    } finally {
      setQuestionLoading(false);
    }
  };

  useEffect(() => {
    fetchQuizzes();
  }, [fetchQuizzes]);

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
      setMessage('Enter a quiz title.');
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
        showSuccessModal('Quiz updated', 'Your changes are saved.');
        setSelectedQuizId(editingQuizId);
      } else {
        const response = await api.post('/admin/quizzes', payload);
        showSuccessModal('Quiz created', 'Your quiz is ready to edit.');

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
          'Failed to save quiz.'
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
    });
    setActiveTab('create');
  };

  const deleteQuiz = async (quizId) => {
    const confirmDelete = window.confirm(
      'Delete this quiz and all of its questions and results?'
    );

    if (!confirmDelete) return;

    try {
      setMessage('');

      await api.delete(`/admin/quizzes/${quizId}`);

      if (selectedQuizId === quizId) {
        setSelectedQuizId(null);
        setQuestions([]);
      }

      setMessage('Quiz deleted.');
      await fetchQuizzes();
    } catch (error) {
      console.error('Delete quiz error:', error.response?.data || error);
      setMessage(
        error.response?.data?.error ||
          error.response?.data?.message ||
          'Failed to delete quiz.'
      );
    }
  };

  const submitQuestion = async (event) => {
    event.preventDefault();

    if (!selectedQuizId) {
      setMessage('Select a quiz first.');
      return;
    }

    if (
      !questionForm.question_text.trim() ||
      !questionForm.option_a.trim() ||
      !questionForm.option_b.trim() ||
      !questionForm.option_c.trim() ||
      !questionForm.option_d.trim()
    ) {
      setMessage('Complete the question and all four options.');
      return;
    }

    try {
      setMessage('');

      if (editingQuestionId) {
        await api.put(`/admin/questions/${editingQuestionId}`, questionForm);
        showSuccessModal('Question updated', 'Your changes are saved.');
      } else {
        await api.post(
          `/admin/quizzes/${selectedQuizId}/questions`,
          questionForm
        );
        showSuccessModal('Question added', 'The question is now in this quiz.');
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
          'Failed to save question.'
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
    if (!window.confirm('Delete this question?')) return;

    try {
      setMessage('');

      await api.delete(`/admin/questions/${questionId}`);

      setMessage('Question deleted.');
      await Promise.all([
        fetchQuestions(selectedQuizId),
        fetchQuizzes(),
      ]);
    } catch (error) {
      console.error('Delete question error:', error.response?.data || error);
      setMessage(
        error.response?.data?.error ||
          error.response?.data?.message ||
          'Failed to delete question.'
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

      const response = await api.post(
        '/admin/quizzes/ai-generate',
        {
          title: aiForm.title.trim() || 'AI Generated Quiz',
          sourceCategory: aiForm.sourceCategory,
          questionCount: Number(aiForm.questionCount) || 5,
          difficulty: aiForm.difficulty,
          status: aiForm.status,
        },
        { timeout: 150000 }
      );

      setAiPreview(response.data?.quiz || null);
    } catch (error) {
      console.error('AI generate quiz error:', error.response?.data || error);

      let fallbackMessage = 'Quiz generation failed. Please try again.';

      if (error.code === 'ECONNABORTED' || !error.response) {
        fallbackMessage =
          'AI request failed. Try again or create the quiz manually.';
      }

      setAiError(error.response?.data?.message || fallbackMessage);
    } finally {
      setAiLoading(false);
    }
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

  const saveAiGeneratedQuiz = async () => {
    if (!aiPreview || aiPreview.questions.length === 0) {
      setAiError('No questions left to save.');
      return;
    }

    try {
      setAiSaving(true);
      setAiError('');

      const quizResponse = await api.post('/admin/quizzes', {
        title: aiPreview.title,
        description: aiPreview.description,
        category: aiPreview.category,
        status: aiPreview.status,
        created_by: user?.id || user?.user_id || null,
      });

      const newQuizId = quizResponse.data?.quiz_id;

      for (const question of aiPreview.questions) {
        await api.post(`/admin/quizzes/${newQuizId}/questions`, {
          question_text: question.question,
          option_a: question.options[0],
          option_b: question.options[1],
          option_c: question.options[2],
          option_d: question.options[3],
          correct_option: optionLetters[question.correctAnswerIndex] || 'A',
          explanation: question.explanation,
          points: 1,
        });
      }

      showSuccessModal('AI quiz saved', 'The quiz is ready to manage.');

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
        error.response?.data?.error ||
          error.response?.data?.message ||
          'Failed to save the AI generated quiz.'
      );
    } finally {
      setAiSaving(false);
    }
  };

  return (
    <div className="qm-page">
      <div className="qm-heading-row">
        <PageHeader
          title="Quiz Management"
          subtitle="Build and manage training quizzes."
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
            AI Generate
          </button>

          <button
            type="button"
            className="qm-btn qm-btn-primary"
            onClick={startCreateQuiz}
          >
            <Icon name="plus" />
            New Quiz
          </button>
        </div>
      </div>

      <section className="qm-stats">
        <button
          type="button"
          className="qm-stat qm-stat-blue"
          onClick={() => setActiveTab('manage')}
        >
          <span>Total Quizzes</span>
          <strong>{quizStats.total}</strong>
        </button>

        <button
          type="button"
          className="qm-stat qm-stat-green"
          onClick={() => setActiveTab('manage')}
        >
          <span>Active</span>
          <strong>{quizStats.active}</strong>
        </button>

        <button
          type="button"
          className="qm-stat qm-stat-amber"
          onClick={() => setActiveTab('manage')}
        >
          <span>Draft</span>
          <strong>{quizStats.draft}</strong>
        </button>

        <div className="qm-stat qm-stat-violet">
          <span>Questions</span>
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
            Quizzes
          </button>

          <button
            type="button"
            className={activeTab === 'create' ? 'active' : ''}
            onClick={startCreateQuiz}
          >
            <Icon name="plus" size={18} />
            {editingQuizId ? 'Edit Quiz' : 'Create'}
          </button>

          <button
            type="button"
            className={`qm-nav-ai ${activeTab === 'ai-generate' ? 'active' : ''}`}
            onClick={() => setActiveTab('ai-generate')}
          >
            <Icon name="sparkles" size={18} />
            AI Builder
          </button>
        </div>

        {activeTab === 'manage' ? (
          <div className="qm-manage">
            <aside className="qm-library">
              <div className="qm-section-head">
                <div>
                  <span className="qm-kicker">Library</span>
                  <h2>Quizzes</h2>
                </div>

                <span className="qm-count-badge">{filteredQuizzes.length}</span>
              </div>

              <div className="qm-search">
                <Icon name="search" size={17} />
                <input
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="Search quizzes"
                />
              </div>

              {loading ? (
                <div className="qm-empty">Loading...</div>
              ) : filteredQuizzes.length === 0 ? (
                <div className="qm-empty">
                  <strong>No quizzes found</strong>
                  <button
                    type="button"
                    className="qm-btn qm-btn-primary"
                    onClick={startCreateQuiz}
                  >
                    Create Quiz
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
                          {quiz.status === 'active' ? 'Active' : 'Draft'}
                        </span>
                      </div>

                      <h3>{quiz.title}</h3>

                      <div className="qm-quiz-meta">
                        <span>{quiz.category || 'Training'}</span>
                        <span>{quiz.question_count || 0} questions</span>
                      </div>

                      <div className="qm-card-actions">
                        <button
                          type="button"
                          className="qm-mini-action"
                          onClick={(event) => {
                            event.stopPropagation();
                            editQuiz(quiz);
                          }}
                          aria-label={`Edit ${quiz.title}`}
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
                          aria-label={`Delete ${quiz.title}`}
                        >
                          <Icon name="trash" size={16} />
                        </button>

                        <span className="qm-open-link">
                          Open <Icon name="arrow" size={15} />
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
                  <strong>Select a quiz</strong>
                  <span>Choose one from the library.</span>
                </div>
              ) : (
                <>
                  <div className="qm-detail-hero">
                    <div>
                      <div className="qm-detail-tags">
                        <span className="qm-pill qm-pill-blue">
                          {selectedQuiz.category || 'Training'}
                        </span>
                        <span
                          className={`qm-pill ${
                            selectedQuiz.status === 'active'
                              ? 'qm-pill-green'
                              : 'qm-pill-amber'
                          }`}
                        >
                          {selectedQuiz.status === 'active' ? 'Active' : 'Draft'}
                        </span>
                      </div>

                      <h2>{selectedQuiz.title}</h2>

                      {selectedQuiz.description ? (
                        <p>{selectedQuiz.description}</p>
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
                      Question
                    </button>
                  </div>

                  <div className="qm-mini-stats">
                    <div>
                      <span>Questions</span>
                      <strong>{selectedQuiz.question_count || questions.length || 0}</strong>
                    </div>
                    <div>
                      <span>Category</span>
                      <strong>{selectedQuiz.category || 'Training'}</strong>
                    </div>
                    <div>
                      <span>Status</span>
                      <strong>{selectedQuiz.status || 'active'}</strong>
                    </div>
                  </div>

                  {questionEditorOpen ? (
                    <form className="qm-question-editor" onSubmit={submitQuestion}>
                      <div className="qm-section-head">
                        <div>
                          <span className="qm-kicker">
                            {editingQuestionId ? 'Editing' : 'New'}
                          </span>
                          <h3>
                            {editingQuestionId ? 'Edit Question' : 'Add Question'}
                          </h3>
                        </div>

                        <button
                          type="button"
                          className="qm-icon-close"
                          onClick={resetQuestionForm}
                          aria-label="Close question editor"
                        >
                          ×
                        </button>
                      </div>

                      <label className="qm-field qm-field-full">
                        <span>Question</span>
                        <textarea
                          rows="3"
                          name="question_text"
                          value={questionForm.question_text}
                          onChange={handleQuestionChange}
                          placeholder="Enter question"
                        />
                      </label>

                      <div className="qm-option-grid">
                        {optionLetters.map((letter) => (
                          <label key={letter} className="qm-field">
                            <span>Option {letter}</span>
                            <input
                              name={`option_${letter.toLowerCase()}`}
                              value={
                                questionForm[`option_${letter.toLowerCase()}`]
                              }
                              onChange={handleQuestionChange}
                              placeholder={`Option ${letter}`}
                            />
                          </label>
                        ))}
                      </div>

                      <div className="qm-editor-bottom-grid">
                        <label className="qm-field">
                          <span>Correct</span>
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
                          <span>Points</span>
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
                        <span>Explanation</span>
                        <textarea
                          rows="2"
                          name="explanation"
                          value={questionForm.explanation}
                          onChange={handleQuestionChange}
                          placeholder="Optional"
                        />
                      </label>

                      <div className="qm-form-actions">
                        <button
                          type="button"
                          className="qm-btn qm-btn-soft"
                          onClick={resetQuestionForm}
                        >
                          Cancel
                        </button>

                        <button
                          type="submit"
                          className="qm-btn qm-btn-primary"
                        >
                          {editingQuestionId ? 'Save Changes' : 'Add Question'}
                        </button>
                      </div>
                    </form>
                  ) : null}

                  <div className="qm-question-section">
                    <div className="qm-section-head">
                      <div>
                        <span className="qm-kicker">Question Bank</span>
                        <h3>{questions.length} Questions</h3>
                      </div>
                    </div>

                    {questionLoading ? (
                      <div className="qm-empty">Loading questions...</div>
                    ) : questions.length === 0 ? (
                      <div className="qm-empty qm-empty-soft">
                        <strong>No questions yet</strong>
                        <button
                          type="button"
                          className="qm-btn qm-btn-primary"
                          onClick={() => setQuestionEditorOpen(true)}
                        >
                          Add Question
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
                                  Answer {question.correct_option}
                                </span>
                                <span>{question.points || 1} pt</span>
                              </div>
                            </div>

                            <div className="qm-question-actions">
                              <button
                                type="button"
                                className="qm-mini-action"
                                onClick={() => editQuestion(question)}
                                aria-label="Edit question"
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
                                aria-label="Delete question"
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
                    {editingQuizId ? 'Edit Quiz' : 'New Quiz'}
                  </span>
                  <h2>
                    {editingQuizId ? 'Update quiz' : 'Create quiz'}
                  </h2>
                </div>

                <div className="qm-create-icon">
                  <Icon name="quiz" size={24} />
                </div>
              </div>

              <form className="qm-form" onSubmit={submitQuiz}>
                <label className="qm-field qm-field-full">
                  <span>Title</span>
                  <input
                    name="title"
                    value={quizForm.title}
                    onChange={handleQuizChange}
                    placeholder="Quiz title"
                  />
                </label>

                <label className="qm-field qm-field-full">
                  <span>Description</span>
                  <textarea
                    rows="3"
                    name="description"
                    value={quizForm.description}
                    onChange={handleQuizChange}
                    placeholder="Short description"
                  />
                </label>

                <div className="qm-form-grid">
                  <label className="qm-field">
                    <span>Category</span>
                    <input
                      name="category"
                      value={quizForm.category}
                      onChange={handleQuizChange}
                      placeholder="Training"
                    />
                  </label>

                  <label className="qm-field">
                    <span>Status</span>
                    <select
                      name="status"
                      value={quizForm.status}
                      onChange={handleQuizChange}
                    >
                      <option value="active">Active</option>
                      <option value="inactive">Draft</option>
                    </select>
                  </label>
                </div>

                <div className="qm-form-actions">
                  {editingQuizId ? (
                    <button
                      type="button"
                      className="qm-btn qm-btn-soft"
                      onClick={startCreateQuiz}
                    >
                      Cancel
                    </button>
                  ) : null}

                  <button
                    type="submit"
                    className="qm-btn qm-btn-primary"
                  >
                    {editingQuizId ? 'Save Changes' : 'Create Quiz'}
                  </button>
                </div>
              </form>
            </section>

            <aside className="qm-create-side">
              <div className="qm-side-orb qm-side-orb-blue">
                <Icon name="quiz" size={26} />
              </div>
              <h3>Manual Builder</h3>
              <p>Create a quiz, then add questions from the quiz workspace.</p>

              <button
                type="button"
                className="qm-side-ai"
                onClick={() => setActiveTab('ai-generate')}
              >
                <span className="qm-side-orb qm-side-orb-violet">
                  <Icon name="sparkles" size={20} />
                </span>
                <span>
                  <strong>Use AI instead</strong>
                  <small>Generate from Knowledge Base</small>
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
                  <span>AI Quiz Builder</span>
                  <h2>Generate from knowledge</h2>
                </div>
              </div>

              <form className="qm-ai-form" onSubmit={generateAiQuiz}>
                <label className="qm-field qm-field-full">
                  <span>Quiz Title</span>
                  <input
                    name="title"
                    value={aiForm.title}
                    onChange={handleAiFormChange}
                    placeholder="Opening SOP Quiz"
                  />
                </label>

                <div className="qm-form-grid">
                  <label className="qm-field">
                    <span>Source</span>
                    <select
                      name="sourceCategory"
                      value={aiForm.sourceCategory}
                      onChange={handleAiFormChange}
                    >
                      {aiSourceCategories.map((category) => (
                        <option key={category} value={category}>
                          {category === 'All' ? 'All Knowledge' : category}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="qm-field">
                    <span>Questions</span>
                    <select
                      name="questionCount"
                      value={aiForm.questionCount}
                      onChange={handleAiFormChange}
                    >
                      <option value={5}>5</option>
                      <option value={10}>10</option>
                      <option value={15}>15</option>
                      <option value={20}>20</option>
                    </select>
                  </label>

                  <label className="qm-field">
                    <span>Difficulty</span>
                    <select
                      name="difficulty"
                      value={aiForm.difficulty}
                      onChange={handleAiFormChange}
                    >
                      <option value="basic">Basic</option>
                      <option value="intermediate">Intermediate</option>
                      <option value="advanced">Advanced</option>
                    </select>
                  </label>

                  <label className="qm-field">
                    <span>Status</span>
                    <select
                      name="status"
                      value={aiForm.status}
                      onChange={handleAiFormChange}
                    >
                      <option value="inactive">Draft</option>
                      <option value="active">Active</option>
                    </select>
                  </label>
                </div>

                <button
                  className="qm-btn qm-btn-ai qm-generate-btn"
                  type="submit"
                  disabled={aiLoading}
                >
                  <Icon name="sparkles" />
                  {aiLoading ? 'Generating...' : 'Generate Quiz'}
                </button>
              </form>

              {aiError ? <div className="qm-ai-error">{aiError}</div> : null}
            </section>

            <section className="qm-ai-preview">
              {!aiPreview ? (
                <div className="qm-ai-empty">
                  <div className="qm-ai-empty-orb">
                    <Icon name="sparkles" size={30} />
                  </div>
                  <strong>AI preview</strong>
                  <span>Generated questions appear here.</span>
                </div>
              ) : (
                <>
                  <div className="qm-ai-preview-head">
                    <div>
                      <div className="qm-detail-tags">
                        <span className="qm-pill qm-pill-violet">
                          {aiPreview.generationMethod === 'ai_provider'
                            ? 'AI Generated'
                            : 'Template Generated'}
                        </span>
                        <span className="qm-pill qm-pill-blue">
                          {aiPreview.category}
                        </span>
                      </div>

                      <h2>{aiPreview.title}</h2>
                      <p>{aiPreview.questions.length} questions</p>
                    </div>

                    <div className="qm-ai-preview-actions">
                      <button
                        type="button"
                        className="qm-btn qm-btn-soft"
                        onClick={cancelAiPreview}
                        disabled={aiSaving}
                      >
                        Cancel
                      </button>

                      <button
                        type="button"
                        className="qm-btn qm-btn-primary"
                        onClick={saveAiGeneratedQuiz}
                        disabled={aiSaving || aiPreview.questions.length === 0}
                      >
                        {aiSaving ? 'Saving...' : 'Save Quiz'}
                      </button>
                    </div>
                  </div>

                  <div className="qm-ai-question-list">
                    {aiPreview.questions.map((question, index) => (
                      <article
                        key={`${question.question}-${index}`}
                        className="qm-ai-question"
                      >
                        <div className="qm-ai-question-head">
                          <span>Q{index + 1}</span>
                          <button
                            type="button"
                            className="qm-mini-action danger"
                            onClick={() => removeAiPreviewQuestion(index)}
                            disabled={aiSaving}
                            aria-label="Remove generated question"
                          >
                            <Icon name="trash" size={15} />
                          </button>
                        </div>

                        <h4>{question.question}</h4>

                        <div className="qm-ai-options">
                          {question.options.map((option, optionIndex) => (
                            <div
                              key={`${option}-${optionIndex}`}
                              className={
                                optionIndex === question.correctAnswerIndex
                                  ? 'correct'
                                  : ''
                              }
                            >
                              <span>{optionLetters[optionIndex]}</span>
                              <p>{option}</p>
                              {optionIndex === question.correctAnswerIndex ? (
                                <Icon name="check" size={15} />
                              ) : null}
                            </div>
                          ))}
                        </div>

                        <div className="qm-ai-source">
                          {question.sourceTitle || 'Knowledge Base'}
                        </div>
                      </article>
                    ))}
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
              Done
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
