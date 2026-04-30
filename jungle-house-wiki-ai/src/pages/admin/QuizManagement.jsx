import { useEffect, useState } from 'react';
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

export default function QuizManagement() {
  const { user } = useAuth();

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

  const selectedQuiz = quizzes.find((quiz) => quiz.quiz_id === selectedQuizId);

  const fetchQuizzes = async () => {
    try {
      setLoading(true);

      const response = await api.get('/admin/quizzes');
      const data = Array.isArray(response.data) ? response.data : [];

      setQuizzes(data);

      if (!selectedQuizId && data.length > 0) {
        setSelectedQuizId(data[0].quiz_id);
        fetchQuestions(data[0].quiz_id);
      }
    } catch (error) {
      console.error('Fetch admin quizzes error:', error);
      setMessage('Failed to load quizzes.');
    } finally {
      setLoading(false);
    }
  };

  const fetchQuestions = async (quizId) => {
    try {
      setQuestionLoading(true);

      const response = await api.get(`/quizzes/${quizId}/questions`);
      const data = Array.isArray(response.data) ? response.data : [];

      setQuestions(data);
    } catch (error) {
      console.error('Fetch quiz questions error:', error);
      setMessage('Failed to load quiz questions.');
    } finally {
      setQuestionLoading(false);
    }
  };

  useEffect(() => {
    fetchQuizzes();
  }, []);

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
    fetchQuestions(quizId);
  };

  const resetQuizForm = () => {
    setQuizForm(emptyQuizForm);
    setEditingQuizId(null);
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
        setMessage('Quiz updated successfully.');
      } else {
        const response = await api.post('/admin/quizzes', payload);
        setMessage('Quiz created successfully.');

        if (response.data?.quiz_id) {
          setSelectedQuizId(response.data.quiz_id);
        }
      }

      resetQuizForm();
      fetchQuizzes();
    } catch (error) {
      console.error('Submit quiz error:', error);
      setMessage(error.response?.data?.message || 'Failed to save quiz.');
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
  };

  const deleteQuiz = async (quizId) => {
    const confirmDelete = window.confirm(
      'Are you sure you want to delete this quiz? All questions and results under this quiz will also be deleted.'
    );

    if (!confirmDelete) return;

    try {
      setMessage('');

      await api.delete(`/admin/quizzes/${quizId}`);

      setMessage('Quiz deleted successfully.');
      setSelectedQuizId(null);
      setQuestions([]);
      fetchQuizzes();
    } catch (error) {
      console.error('Delete quiz error:', error);
      setMessage(error.response?.data?.message || 'Failed to delete quiz.');
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
        setMessage('Question updated successfully.');
      } else {
        await api.post(`/admin/quizzes/${selectedQuizId}/questions`, questionForm);
        setMessage('Question added successfully.');
      }

      resetQuestionForm();
      fetchQuestions(selectedQuizId);
      fetchQuizzes();
    } catch (error) {
      console.error('Submit question error:', error);
      setMessage(error.response?.data?.message || 'Failed to save question.');
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
      console.error('Delete question error:', error);
      setMessage(error.response?.data?.message || 'Failed to delete question.');
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

      <div className="two-column-grid">
        <section className="card-like">
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

        <section className="card-like">
          <h3>Quiz List</h3>
          <p className="muted">
            Select a quiz to manage its questions.
          </p>

          {loading ? (
            <p className="muted">Loading quizzes...</p>
          ) : quizzes.length === 0 ? (
            <p className="muted">No quizzes found.</p>
          ) : (
            <div className="stack-gap top-gap">
              {quizzes.map((quiz) => (
                <article
                  key={quiz.quiz_id}
                  className="card-like"
                  style={{
                    borderColor:
                      selectedQuizId === quiz.quiz_id ? 'var(--primary)' : 'var(--border)',
                  }}
                >
                  <div className="row-between wrap-gap">
                    <div>
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
              <article key={question.question_id || question.id} className="card-like">
                <div className="row-between wrap-gap">
                  <div>
                    <p className="eyebrow">Question {index + 1}</p>
                    <h3>{question.question_text || question.question}</h3>
                    <p className="muted small">
                      Correct Option: {question.correct_option} | Points: {question.points || 1}
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
    </div>
  );
}