import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';

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

export default function QuizManagement() {
  const { user } = useAuth();

  const [activeTab, setActiveTab] = useState('create');
  const [searchTerm, setSearchTerm] = useState('');

  const [quizzes, setQuizzes] = useState([]);
  const [selectedQuizId, setSelectedQuizId] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [quizForm, setQuizForm] = useState(emptyQuizForm);
  const [questionForm, setQuestionForm] = useState(emptyQuestionForm);
  const [editingQuizId, setEditingQuizId] = useState(null);
  const [editingQuestionId, setEditingQuestionId] = useState(null);
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

  const showSuccessModal = (title, text) => {
    setSuccessModal({
      show: true,
      title,
      text,
    });
  };

  const closeSuccessModal = () => {
    setSuccessModal({
      show: false,
      title: '',
      text: '',
    });
  };

  const fetchQuizzes = async () => {
    try {
      setLoading(true);

      const response = await api.get('/admin/quizzes');
      const data = Array.isArray(response.data) ? response.data : [];

      setQuizzes(data);

      if (!selectedQuizId && data.length > 0) {
        setSelectedQuizId(data[0].quiz_id);
      }
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
  };

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
  }, []);

  useEffect(() => {
    if (selectedQuizId && activeTab === 'manage') {
      fetchQuestions(selectedQuizId);
    }
  }, [selectedQuizId, activeTab]);

  const handleQuizChange = (event) => {
    const { name, value } = event.target;

    setQuizForm((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleQuestionChange = (event) => {
    const { name, value } = event.target;

    setQuestionForm((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSelectQuiz = (quizId) => {
    setSelectedQuizId(quizId);
    setEditingQuestionId(null);
    setQuestionForm(emptyQuestionForm);
    setActiveTab('manage');
    fetchQuestions(quizId);
  };

  const resetQuizForm = () => {
    setQuizForm(emptyQuizForm);
    setEditingQuizId(null);
    setActiveTab('create');
  };

  const resetQuestionForm = () => {
    setQuestionForm(emptyQuestionForm);
    setEditingQuestionId(null);
  };

  const submitQuiz = async (event) => {
    event.preventDefault();

    if (!quizForm.title.trim()) {
      setMessage('Please enter quiz title.');
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

        showSuccessModal(
          'Quiz Updated Successfully',
          'The selected quiz details have been updated in the system.'
        );
      } else {
        const response = await api.post('/admin/quizzes', payload);

        showSuccessModal(
          'Quiz Created Successfully',
          'The new quiz has been created and saved into the system.'
        );

        if (response.data?.quiz_id) {
          setSelectedQuizId(response.data.quiz_id);
          setActiveTab('manage');
        }
      }

      resetQuizForm();
      fetchQuizzes();
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
      'Are you sure you want to delete this quiz? All questions and results under this quiz will also be deleted.'
    );

    if (!confirmDelete) return;

    try {
      setMessage('');

      await api.delete(`/admin/quizzes/${quizId}`);

      if (selectedQuizId === quizId) {
        setSelectedQuizId(null);
        setQuestions([]);
      }

      setMessage('Quiz deleted successfully.');
      fetchQuizzes();
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
      setMessage('Please select a quiz first.');
      return;
    }

    if (
      !questionForm.question_text.trim() ||
      !questionForm.option_a.trim() ||
      !questionForm.option_b.trim() ||
      !questionForm.option_c.trim() ||
      !questionForm.option_d.trim()
    ) {
      setMessage('Please fill in all question fields.');
      return;
    }

    try {
      setMessage('');

      if (editingQuestionId) {
        await api.put(`/admin/questions/${editingQuestionId}`, questionForm);

        showSuccessModal(
          'Question Updated Successfully',
          'The selected quiz question has been updated.'
        );
      } else {
        await api.post(`/admin/quizzes/${selectedQuizId}/questions`, questionForm);

        showSuccessModal(
          'Question Added Successfully',
          'The new question has been added to the selected quiz.'
        );
      }

      resetQuestionForm();
      fetchQuestions(selectedQuizId);
      fetchQuizzes();
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
  };

  const deleteQuestion = async (questionId) => {
    const confirmDelete = window.confirm(
      'Are you sure you want to delete this question?'
    );

    if (!confirmDelete) return;

    try {
      setMessage('');

      await api.delete(`/admin/questions/${questionId}`);

      setMessage('Question deleted successfully.');
      fetchQuestions(selectedQuizId);
      fetchQuizzes();
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

    setAiForm((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const generateAiQuiz = async (event) => {
    event.preventDefault();

    setAiError('');
    setAiPreview(null);

    try {
      setAiLoading(true);

      // A real AI provider call (Knowledge Base retrieval + an external LLM
      // request) can comfortably take longer than the shared API client's
      // default timeout, so this specific call gets a longer one of its own
      // -- this does not change the shared axios instance or its baseURL.
      const response = await api.post(
        '/admin/quizzes/ai-generate',
        {
          title: aiForm.title.trim() || 'AI Generated Quiz',
          sourceCategory: aiForm.sourceCategory,
          questionCount: Number(aiForm.questionCount) || 5,
          difficulty: aiForm.difficulty,
          status: aiForm.status,
        },
        { timeout: 45000 }
      );

      setAiPreview(response.data?.quiz || null);
    } catch (error) {
      console.error('AI generate quiz error:', error.response?.data || error);

      let fallbackMessage = 'Quiz generation failed. Please try again.';

      if (error.code === 'ECONNABORTED' || !error.response) {
        fallbackMessage = 'AI provider request failed. Please try again, or create the quiz manually.';
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
      setAiError('There are no questions left to save.');
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

      showSuccessModal(
        'AI Quiz Saved Successfully',
        'The AI generated quiz has been saved and now appears in Manage Quizzes.'
      );

      setAiPreview(null);
      setAiForm(emptyAiForm);

      if (newQuizId) {
        setSelectedQuizId(newQuizId);
      }

      setActiveTab('manage');
      fetchQuizzes();
    } catch (error) {
      console.error('Save AI generated quiz error:', error.response?.data || error);
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
    <div>
      <PageHeader
        title="Quiz Management"
        subtitle="Create and manage training quizzes for Staff and Team Lead."
      />

      {message && (
        <section className="card-like top-gap-sm">
          <p className="muted">{message}</p>
        </section>
      )}

      <section className="card-like top-gap-sm">
        <div className="quiz-tab-bar">
          <button
            type="button"
            className={`quiz-tab-btn ${activeTab === 'create' ? 'active' : ''}`}
            onClick={() => setActiveTab('create')}
          >
            Create Quiz
          </button>

          <button
            type="button"
            className={`quiz-tab-btn ${activeTab === 'manage' ? 'active' : ''}`}
            onClick={() => setActiveTab('manage')}
          >
            Manage Quizzes
          </button>

          <button
            type="button"
            className={`quiz-tab-btn ${activeTab === 'ai-generate' ? 'active' : ''}`}
            onClick={() => setActiveTab('ai-generate')}
          >
            Auto Generate Quiz
          </button>
        </div>
      </section>

      {activeTab === 'create' && (
        <section className="card-like top-gap">
          <div className="row-between wrap-gap">
            <div>
              <h3>{editingQuizId ? 'Edit Quiz' : 'Create New Quiz'}</h3>
              <p className="muted">
                Add quiz title, category, description, and status.
              </p>
            </div>

            {editingQuizId && (
              <button className="secondary-btn" onClick={resetQuizForm}>
                Cancel Edit
              </button>
            )}
          </div>

          <form className="form-stack top-gap" onSubmit={submitQuiz}>
            <label>
              Quiz Title
              <input
                name="title"
                value={quizForm.title}
                onChange={handleQuizChange}
                placeholder="Example: Pre-Official Interview Training"
              />
            </label>

            <label>
              Description
              <textarea
                rows="4"
                name="description"
                value={quizForm.description}
                onChange={handleQuizChange}
                placeholder="Write a short quiz description"
              />
            </label>

            <label>
              Category
              <input
                name="category"
                value={quizForm.category}
                onChange={handleQuizChange}
                placeholder="Training"
              />
            </label>

            <label>
              Status
              <select
                name="status"
                value={quizForm.status}
                onChange={handleQuizChange}
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </label>

            <button className="primary-btn" type="submit">
              {editingQuizId ? 'Update Quiz' : 'Create Quiz'}
            </button>
          </form>
        </section>
      )}

      {activeTab === 'ai-generate' && (
        <section className="card-like top-gap">
          <div>
            <h3>Auto Generate Quiz</h3>
            <p className="muted">
              Automatically build multiple-choice questions from the latest
              published Knowledge Base / SOP articles. Review the preview
              before saving.
            </p>
          </div>

          <form className="form-grid top-gap" onSubmit={generateAiQuiz}>
            <label className="full-width">
              Quiz Title
              <input
                name="title"
                value={aiForm.title}
                onChange={handleAiFormChange}
                placeholder="Example: Opening SOP Quiz"
              />
            </label>

            <label>
              Category / Source Content
              <select
                name="sourceCategory"
                value={aiForm.sourceCategory}
                onChange={handleAiFormChange}
              >
                {aiSourceCategories.map((category) => (
                  <option key={category} value={category}>
                    {category === 'All' ? 'All latest verified articles' : category}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Number of Questions
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

            <label>
              Difficulty
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

            <label>
              Status
              <select
                name="status"
                value={aiForm.status}
                onChange={handleAiFormChange}
              >
                <option value="inactive">Draft</option>
                <option value="active">Active</option>
              </select>
            </label>

            <div className="full-width">
              <button className="primary-btn" type="submit" disabled={aiLoading}>
                {aiLoading ? 'Generating quiz from the latest Knowledge Base...' : 'Generate Quiz'}
              </button>
            </div>
          </form>

          {aiError && <p className="error-text top-gap-sm">{aiError}</p>}

          {aiPreview && (
            <div className="top-gap">
              <div className="row-between wrap-gap">
                <div>
                  <h3>
                    Preview: {aiPreview.title}{' '}
                    <span className="role-pill">
                      {aiPreview.generationMethod === 'ai_provider'
                        ? 'Generated by AI provider'
                        : 'Generated from templates'}
                    </span>
                  </h3>
                  <p className="muted">
                    {aiPreview.questions.length} question(s) generated from{' '}
                    {aiPreview.category}. Remove any question you don't want,
                    then save.
                  </p>
                </div>

                <div className="button-group wrap-gap">
                  <button
                    type="button"
                    className="primary-btn"
                    onClick={saveAiGeneratedQuiz}
                    disabled={aiSaving || aiPreview.questions.length === 0}
                  >
                    {aiSaving ? 'Saving...' : 'Save Quiz'}
                  </button>

                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={cancelAiPreview}
                    disabled={aiSaving}
                  >
                    Cancel
                  </button>
                </div>
              </div>

              <div className="stack-gap top-gap">
                {aiPreview.questions.map((question, index) => (
                  <article key={`${question.question}-${index}`} className="card-like">
                    <div className="row-between wrap-gap">
                      <div>
                        <p className="eyebrow">
                          Question {index + 1} | Source: {question.sourceTitle}
                        </p>
                        <h3>{question.question}</h3>
                      </div>

                      <button
                        type="button"
                        className="danger-btn"
                        onClick={() => removeAiPreviewQuestion(index)}
                        disabled={aiSaving}
                      >
                        Remove
                      </button>
                    </div>

                    <div className="cards-grid top-gap-sm">
                      {question.options.map((option, optionIndex) => (
                        <p
                          key={optionIndex}
                          className={
                            optionIndex === question.correctAnswerIndex
                              ? 'success-text'
                              : 'muted'
                          }
                        >
                          {optionLetters[optionIndex]}. {option}
                          {optionIndex === question.correctAnswerIndex ? ' (Correct)' : ''}
                        </p>
                      ))}
                    </div>

                    {question.explanation && (
                      <p className="muted top-gap">
                        Explanation: {question.explanation}
                      </p>
                    )}
                  </article>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {activeTab === 'manage' && (
        <>
          <div className="two-column-grid top-gap">
            <section className="card-like">
              <div className="row-between wrap-gap">
                <div>
                  <h3>Quiz List</h3>
                  <p className="muted">Select a quiz to manage its questions.</p>
                </div>
              </div>

              <div className="top-gap-sm">
                <input
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="Search quiz by title, category, or status"
                />
              </div>

              {loading ? (
                <p className="muted top-gap">Loading quizzes...</p>
              ) : filteredQuizzes.length === 0 ? (
                <p className="muted top-gap">No quizzes found.</p>
              ) : (
                <div className="quiz-list-scroll top-gap">
                  {filteredQuizzes.map((quiz) => (
                    <article
                      key={quiz.quiz_id}
                      className={`quiz-list-item ${
                        selectedQuizId === quiz.quiz_id ? 'selected' : ''
                      }`}
                    >
                      <div className="row-between wrap-gap">
                        <div className="quiz-list-main">
                          <p className="eyebrow">{quiz.category || 'Quiz'}</p>
                          <h3>{quiz.title}</h3>
                          <p className="muted small">
                            Questions: {quiz.question_count || 0} | Status: {quiz.status}
                          </p>
                        </div>

                        <div className="button-group wrap-gap">
                          <button
                            className="secondary-btn"
                            onClick={() => handleSelectQuiz(quiz.quiz_id)}
                          >
                            Manage
                          </button>

                          <button
                            className="secondary-btn"
                            onClick={() => editQuiz(quiz)}
                          >
                            Edit
                          </button>

                          <button
                            className="danger-btn"
                            onClick={() => deleteQuiz(quiz.quiz_id)}
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className="card-like">
              <div className="row-between wrap-gap">
                <div>
                  <h3>
                    {selectedQuiz ? selectedQuiz.title : 'Selected Quiz'}
                  </h3>
                  <p className="muted">
                    {selectedQuiz
                      ? 'Manage the selected quiz questions below.'
                      : 'Select a quiz from the list to manage it.'}
                  </p>
                </div>
              </div>

              {selectedQuiz ? (
                <div className="quiz-selected-summary top-gap">
                  <div className="quiz-summary-chip">
                    <span className="quiz-summary-label">Category</span>
                    <strong>{selectedQuiz.category || 'Quiz'}</strong>
                  </div>

                  <div className="quiz-summary-chip">
                    <span className="quiz-summary-label">Status</span>
                    <strong>{selectedQuiz.status || 'active'}</strong>
                  </div>

                  <div className="quiz-summary-chip">
                    <span className="quiz-summary-label">Questions</span>
                    <strong>{selectedQuiz.question_count || 0}</strong>
                  </div>
                </div>
              ) : (
                <p className="muted top-gap">No quiz selected yet.</p>
              )}
            </section>
          </div>

          <section className="card-like top-gap">
            <div className="row-between wrap-gap">
              <div>
                <h3>
                  {selectedQuiz
                    ? `Questions for: ${selectedQuiz.title}`
                    : 'Quiz Questions'}
                </h3>
                <p className="muted">
                  Add, edit, or remove multiple-choice questions for the selected quiz.
                </p>
              </div>

              {editingQuestionId && (
                <button className="secondary-btn" onClick={resetQuestionForm}>
                  Cancel Question Edit
                </button>
              )}
            </div>

            {!selectedQuizId ? (
              <p className="muted top-gap">
                Please select a quiz first before adding questions.
              </p>
            ) : (
              <form className="form-grid top-gap" onSubmit={submitQuestion}>
                <label className="full-width">
                  Question
                  <textarea
                    rows="3"
                    name="question_text"
                    value={questionForm.question_text}
                    onChange={handleQuestionChange}
                    placeholder="Enter the quiz question"
                  />
                </label>

                <label>
                  Option A
                  <input
                    name="option_a"
                    value={questionForm.option_a}
                    onChange={handleQuestionChange}
                    placeholder="Option A"
                  />
                </label>

                <label>
                  Option B
                  <input
                    name="option_b"
                    value={questionForm.option_b}
                    onChange={handleQuestionChange}
                    placeholder="Option B"
                  />
                </label>

                <label>
                  Option C
                  <input
                    name="option_c"
                    value={questionForm.option_c}
                    onChange={handleQuestionChange}
                    placeholder="Option C"
                  />
                </label>

                <label>
                  Option D
                  <input
                    name="option_d"
                    value={questionForm.option_d}
                    onChange={handleQuestionChange}
                    placeholder="Option D"
                  />
                </label>

                <label>
                  Correct Option
                  <select
                    name="correct_option"
                    value={questionForm.correct_option}
                    onChange={handleQuestionChange}
                  >
                    <option value="A">A</option>
                    <option value="B">B</option>
                    <option value="C">C</option>
                    <option value="D">D</option>
                  </select>
                </label>

                <label>
                  Points
                  <input
                    type="number"
                    min="1"
                    name="points"
                    value={questionForm.points}
                    onChange={handleQuestionChange}
                  />
                </label>

                <label className="full-width">
                  Explanation
                  <textarea
                    rows="3"
                    name="explanation"
                    value={questionForm.explanation}
                    onChange={handleQuestionChange}
                    placeholder="Optional explanation for the correct answer"
                  />
                </label>

                <div className="full-width">
                  <button className="primary-btn" type="submit">
                    {editingQuestionId ? 'Update Question' : 'Add Question'}
                  </button>
                </div>
              </form>
            )}
          </section>

          <section className="card-like top-gap">
            <h3>Question List</h3>

            {!selectedQuizId ? (
              <p className="muted">Select a quiz to view questions.</p>
            ) : questionLoading ? (
              <p className="muted">Loading questions...</p>
            ) : questions.length === 0 ? (
              <p className="muted">No questions added yet.</p>
            ) : (
              <div className="stack-gap top-gap">
                {questions.map((question, index) => (
                  <article
                    key={question.question_id || question.id}
                    className="card-like"
                  >
                    <div className="row-between wrap-gap">
                      <div>
                        <p className="eyebrow">Question {index + 1}</p>
                        <h3>{question.question_text || question.question}</h3>
                        <p className="muted small">
                          Correct Option: {question.correct_option} | Points:{' '}
                          {question.points || 1}
                        </p>
                      </div>

                      <div className="button-group wrap-gap">
                        <button
                          className="secondary-btn"
                          onClick={() => editQuestion(question)}
                        >
                          Edit
                        </button>

                        <button
                          className="danger-btn"
                          onClick={() =>
                            deleteQuestion(question.question_id || question.id)
                          }
                        >
                          Delete
                        </button>
                      </div>
                    </div>

                    <div className="cards-grid top-gap-sm">
                      <p className="muted">A. {question.option_a}</p>
                      <p className="muted">B. {question.option_b}</p>
                      <p className="muted">C. {question.option_c}</p>
                      <p className="muted">D. {question.option_d}</p>
                    </div>

                    {question.explanation && (
                      <p className="muted top-gap">
                        Explanation: {question.explanation}
                      </p>
                    )}
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      {successModal.show && (
        <div className="success-modal-overlay">
          <div className="success-modal-card">
            <button
              type="button"
              className="success-modal-close"
              onClick={closeSuccessModal}
            >
              ×
            </button>

            <div className="success-modal-icon-wrap">
              <div className="success-modal-icon">
                <svg
                  width="46"
                  height="46"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M20 6L9 17l-5-5" />
                </svg>
              </div>
            </div>

            <div className="success-modal-content">
              <h2>{successModal.title}</h2>
              <p>{successModal.text}</p>

              <div className="success-modal-actions">
                <button
                  type="button"
                  className="success-confirm-btn"
                  onClick={closeSuccessModal}
                >
                  OK
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}