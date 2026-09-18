import { useEffect, useMemo, useRef, useState } from 'react';
import PageHeader from '../components/PageHeader';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import '../styles/Quiz.css';

export default function QuizList() {
  const { user } = useAuth();
  const staffMode = String(user?.role || '').toLowerCase() === 'staff';
  const [categoryFilter, setCategoryFilter] = useState('All');
  const [quizError, setQuizError] = useState('');
  const [questionError, setQuestionError] = useState('');
  const [saveStatus, setSaveStatus] = useState('idle');
  const [saveError, setSaveError] = useState('');
  const [serverResult, setServerResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [quizItems, setQuizItems] = useState([]);
  const [activeQuizId, setActiveQuizId] = useState(null);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [selectedAnswers, setSelectedAnswers] = useState({});
  const [submitted, setSubmitted] = useState(false);
  const [showWelcome, setShowWelcome] = useState(false);
  const [loadingQuizzes, setLoadingQuizzes] = useState(true);
  const [loadingQuestions, setLoadingQuestions] = useState(false);

  const autoNextTimerRef = useRef(null);

  const clearAutoNextTimer = () => {
    if (autoNextTimerRef.current) {
      clearTimeout(autoNextTimerRef.current);
      autoNextTimerRef.current = null;
    }
  };

  useEffect(() => {
    fetchQuizzes();

    return () => {
      clearAutoNextTimer();
    };
  }, []);

  const fetchQuizzes = async () => {
    try {
      setLoadingQuizzes(true);
      setQuizError('');

      const response = await api.get('/quizzes');
      const data = response.data;

      if (Array.isArray(data)) {
        const formattedQuizzes = data.map((quiz) => ({
          id: quiz.quiz_id,
          title: quiz.title,
          description: quiz.description,
          category: quiz.category,
          questionCount: quiz.question_count,
          questions: [],
        }));

        setQuizItems(formattedQuizzes);
      } else {
        setQuizItems([]);
      }
    } catch (err) {
      console.error('Failed to load quizzes:', err);
      setQuizItems([]);
      setQuizError(err.response?.data?.message || 'Could not load quizzes. Please try again.');
    } finally {
      setLoadingQuizzes(false);
    }
  };

  const fetchQuizQuestions = async (quizId) => {
    try {
      setLoadingQuestions(true);
      setQuestionError('');

      const response = await api.get(`/quizzes/${quizId}/questions`);
      const data = response.data;

      if (!Array.isArray(data)) {
        throw new Error('Invalid quiz question response.');
      }

      if (Array.isArray(data)) {
        setQuizItems((prev) =>
          prev.map((quiz) =>
            quiz.id === quizId
              ? {
                  ...quiz,
                  questions: data,
                }
              : quiz
          )
        );
      }
    } catch (err) {
      console.error('Failed to load quiz questions:', err);
      setQuestionError(err.response?.data?.message || 'Questions could not be loaded. Try again.');
    } finally {
      setLoadingQuestions(false);
    }
  };

  const activeQuiz = useMemo(
    () => quizItems.find((quiz) => quiz.id === activeQuizId) || null,
    [quizItems, activeQuizId]
  );

  const categories = useMemo(() =>
    ['All', ...new Set(quizItems.map((quiz) => quiz.category || 'Training'))],
    [quizItems]
  );
  const visibleQuizzes = staffMode && categoryFilter !== 'All'
    ? quizItems.filter((quiz) => (quiz.category || 'Training') === categoryFilter)
    : quizItems;

  const questions = activeQuiz?.questions || [];
  const currentQuestion = questions[currentQuestionIndex];
  const totalQuestions = questions.length;

  // Results are authoritative only after Flask marks and saves the attempt.
  // The pre-submission questions API intentionally does not expose answer keys.
  const score = serverResult?.percentage ?? 0;
  const correctCount = serverResult?.score ?? 0;

  const handleStartQuiz = async (quizId) => {
    clearAutoNextTimer();

    setActiveQuizId(quizId);
    setCurrentQuestionIndex(0);
    setSelectedAnswers({});
    setSubmitted(false);
    setShowWelcome(true);
    setSaveStatus('idle');
    setSaveError('');
    setServerResult(null);
    setQuestionError('');

    await fetchQuizQuestions(quizId);
  };

  const handleBeginQuestions = () => {
    clearAutoNextTimer();
    if (loadingQuestions || questionError || totalQuestions === 0) return;
    setShowWelcome(false);
  };

  const handleSelectAnswer = (questionId, optionValue) => {
    if (submitted || submitting) return;

    clearAutoNextTimer();

    setSelectedAnswers((prev) => ({
      ...prev,
      [questionId]: optionValue,
    }));

    // Staff can review an answer before moving on; automatic advance is too
    // quick for mobile touch screens. Keep the established non-staff flow.
    if (!staffMode && currentQuestionIndex < totalQuestions - 1) {
      autoNextTimerRef.current = setTimeout(() => {
        setCurrentQuestionIndex((prev) =>
          Math.min(prev + 1, totalQuestions - 1)
        );
        autoNextTimerRef.current = null;
      }, 350);
    }
  };

  const handleNext = () => {
    clearAutoNextTimer();

    if (currentQuestionIndex < totalQuestions - 1) {
      setCurrentQuestionIndex((prev) => prev + 1);
    }
  };

  const handlePrevious = () => {
    clearAutoNextTimer();

    if (currentQuestionIndex > 0) {
      setCurrentQuestionIndex((prev) => prev - 1);
    }
  };

  const handleSubmit = async () => {
    if (submitting || submitted || !activeQuizId || !totalQuestions || answeredCount !== totalQuestions) {
      return;
    }

    clearAutoNextTimer();
    setSubmitting(true);
    setSaveStatus('idle');
    setSaveError('');

    try {
      // Send option LETTERS only. Flask determines user ID from the session,
      // recalculates the score using MySQL and inserts the quiz_result row.
      const response = await api.post(`/quizzes/${activeQuizId}/submit`, {
        answers: selectedAnswers,
      });
      const result = response.data;
      if (result?.saved !== true || !Number.isFinite(Number(result.score)) ||
          !Number.isFinite(Number(result.percentage)) || !Number.isFinite(Number(result.total_questions))) {
        throw new Error('Server did not confirm a saved result.');
      }
      setServerResult(result);
      setSaveStatus('saved');
      setSubmitted(true);
    } catch (submitError) {
      console.warn('Quiz result save was not confirmed:', submitError);
      setSaveStatus('unsaved');
      setSaveError(
        submitError.response?.data?.message ||
        'Could not confirm that your attempt was saved. Check your training record before submitting again to avoid duplicates.'
      );
      // Keep answers and the quiz visible. Never show a fabricated score.
    } finally {
      setSubmitting(false);
    }
  };

  const handleRetake = () => {
    clearAutoNextTimer();

    setCurrentQuestionIndex(0);
    setSelectedAnswers({});
    setSubmitted(false);
    setShowWelcome(true);
    setSaveStatus('idle');
    setSaveError('');
    setServerResult(null);
  };

  const handleBackToList = () => {
    clearAutoNextTimer();

    setActiveQuizId(null);
    setCurrentQuestionIndex(0);
    setSelectedAnswers({});
    setSubmitted(false);
    setShowWelcome(false);
    setSaveStatus('idle');
    setSaveError('');
    setServerResult(null);
    setQuestionError('');
  };

  const answeredCount = Object.keys(selectedAnswers).length;

  return (
    <div className={`quiz-page ${staffMode ? 'staff-quiz-page' : ''}`}>
      <PageHeader
        title={staffMode ? 'Training' : 'Quiz / Training'}
        subtitle={staffMode ? 'Learn. Practise. Grow.' : 'Support onboarding with basic quizzes and learning reinforcement.'}
      />

      {staffMode && !activeQuiz && !loadingQuizzes && quizItems.length > 0 ? (
        <div className="staff-quiz-filters" role="group" aria-label="Filter training quizzes"
          style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
          {categories.map((category) => (
            <button key={category} type="button"
              className={categoryFilter === category ? 'primary-btn' : 'secondary-btn'}
              aria-pressed={categoryFilter === category}
              onClick={() => setCategoryFilter(category)}>{category}</button>
          ))}
        </div>
      ) : null}

      {!activeQuiz ? (
        <div className="cards-grid quiz-list-grid"
          style={staffMode ? { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: 16 } : undefined}>
          {loadingQuizzes ? (
            <div className="quiz-state-card" aria-live="polite">
              <span className="quiz-loading-spinner" aria-hidden="true" />
              <strong>Loading training quizzes</strong>
              <p>Preparing the available learning activities...</p>
            </div>
          ) : quizError ? (
            <div className="quiz-state-card" role="alert">
              <strong>Unable to load training</strong>
              <p>{quizError}</p>
              <button type="button" className="secondary-btn" onClick={fetchQuizzes}>Retry</button>
            </div>
          ) : quizItems.length === 0 ? (
            <div className="quiz-state-card">
              <span className="quiz-state-icon" aria-hidden="true">?</span>
              <strong>No quizzes available</strong>
              <p>Training quizzes will appear here when they are published.</p>
            </div>
          ) : (
            visibleQuizzes.map((quiz) => (
              <article key={quiz.id} className="card-like quiz-card">
                <div className="quiz-card-top">
                  <div className="quiz-card-heading">
                    <span className="quiz-card-icon" aria-hidden="true">✓</span>
                    <div>
                      <span className="quiz-card-kicker">
                        {quiz.category || 'Training'}
                      </span>
                      <h3>{quiz.title}</h3>
                    </div>
                  </div>

                  {!staffMode && <span className="status-badge pending">Training Quiz</span>}
                </div>

                {quiz.description ? (
                  <p className="quiz-card-description">{staffMode && quiz.description.length > 100 ? `${quiz.description.slice(0, 97).trim()}…` : quiz.description}</p>
                ) : (
                  !staffMode && <p className="quiz-card-description">
                    Complete this quiz to reinforce your Jungle House knowledge.
                  </p>
                )}

                <div className="quiz-card-meta">
                  <span>
                    <strong>{quiz.questionCount ?? 0}</strong>
                    Questions
                  </span>
                  {/* The current /quizzes API provides no previous score. Do not show a fabricated 0%. */}
                </div>

                <button
                  type="button"
                  className="primary-btn quiz-card-action"
                  onClick={() => handleStartQuiz(quiz.id)}
                  disabled={!quiz.questionCount}
                >
                  {staffMode ? 'Start' : 'Attempt Quiz'}
                  <span aria-hidden="true">→</span>
                </button>
              </article>
            ))
          )}
        </div>
      ) : (
        <div className="stack-gap quiz-session">
          <div className="card-like quiz-session-header">
            <div className="row-between wrap-gap">
              <div>
                <h2 className="quiz-session-title">{activeQuiz.title}</h2>
                {!showWelcome ? (
                  <p className="muted" style={{ marginBottom: 0 }}>
                    Question {currentQuestionIndex + 1} of {totalQuestions}
                  </p>
                ) : (
                  <p className="muted" style={{ marginBottom: 0 }}>
                    Welcome to this training quiz
                  </p>
                )}
              </div>

              <div className="button-group wrap-gap">
                <button className="secondary-btn" onClick={handleBackToList}>
                  Back to Quiz List
                </button>
              </div>
            </div>
          </div>

          {showWelcome ? staffMode ? (
            <div className="card-like quiz-welcome-card staff-quiz-welcome">
              <span className="eyebrow">Ready?</span>
              <h2>{activeQuiz.title}</h2>
              <p>{totalQuestions} questions · Choose one answer per question.</p>
              {loadingQuestions && <p role="status">Loading questions…</p>}
              {questionError && <p role="alert">{questionError}</p>}
              {!loadingQuestions && !questionError && totalQuestions === 0 && <p>No questions available.</p>}
              <div className="button-group wrap-gap top-gap">
                <button type="button" className="secondary-btn" onClick={handleBackToList}>Back</button>
                {questionError ? (
                  <button type="button" className="primary-btn" onClick={() => fetchQuizQuestions(activeQuizId)}>Retry</button>
                ) : (
                  <button type="button" className="primary-btn"
                    onClick={handleBeginQuestions} disabled={loadingQuestions || totalQuestions === 0}>Begin →</button>
                )}
              </div>
            </div>
          ) : (
            <div className="card-like quiz-welcome-card">
              <p className="eyebrow">Welcome</p>
              <h2 style={{ marginBottom: '10px' }}>
                Pre-Official Interview Training Session
              </h2>

              <div className="quiz-welcome-message">
                <p>Dear Candidate,</p>

                <p>
                  Welcome to the Pre-Official Interview Training Session!
                </p>

                <p>
                  We’re excited to have you here and appreciate your interest in joining
                  our team. This session is designed to help you better understand our
                  interview process, set clear expectations, and equip you with valuable
                  tips to present your best self during the official interview.
                </p>

                <p>
                  Whether you're new to our industry or bringing in prior experience,
                  this training will guide you through the essential aspects of what
                  we’re looking for, our company culture, and how to confidently
                  communicate your strengths.
                </p>

                <p>
                  Take this opportunity to prepare, learn, and ask questions. Our goal
                  is to support you in making this journey as smooth and insightful as
                  possible.
                </p>

                <p>Let’s get started!</p>

                <p style={{ marginBottom: 0 }}>
                  Warm regards,
                  <br />
                  <strong>Eno Wong</strong>
                  <br />
                  King Bee (Kuching)
                </p>
              </div>

              <div className="button-group wrap-gap top-gap">
                <button className="secondary-btn" onClick={handleBackToList}>
                  Back
                </button>
                <button className="primary-btn" onClick={handleBeginQuestions}>
                  Start Quiz Now
                </button>
              </div>
            </div>
          ) : loadingQuestions ? (
            <div className="card-like">
              <p>Loading quiz questions...</p>
            </div>
          ) : !submitted ? (
            <>
              {staffMode && totalQuestions > 0 && (
                <nav className="staff-quiz-question-nav" aria-label="Quiz questions"
                  style={{ display: 'flex', flexWrap: 'nowrap', overflowX: 'auto', gap: 8, marginBottom: 12, paddingBottom: 4, maxWidth: '100%' }}>
                  {questions.map((item, index) => (
                    <button key={item.id} type="button"
                      className={index === currentQuestionIndex ? 'primary-btn' : 'secondary-btn'}
                      aria-label={`Question ${index + 1}${selectedAnswers[item.id] !== undefined ? ', answered' : ''}`}
                      aria-current={index === currentQuestionIndex ? 'step' : undefined}
                      onClick={() => { clearAutoNextTimer(); setCurrentQuestionIndex(index); }}
                      style={{ minWidth: 42, minHeight: 42, padding: '8px 12px', flex: '0 0 auto' }}>
                      {index + 1}{selectedAnswers[item.id] !== undefined && index !== currentQuestionIndex ? ' ✓' : ''}
                    </button>
                  ))}
                </nav>
              )}
              <div className="card-like quiz-progress-card">
                <div className="quiz-progress-row">
                  <div className="quiz-progress-bar">
                    <div
                      className="quiz-progress-fill"
                      style={{
                        width:
                          totalQuestions > 0
                            ? `${((currentQuestionIndex + 1) / totalQuestions) * 100}%`
                            : '0%',
                      }}
                    />
                  </div>
                  <p className="muted small" style={{ marginBottom: 0 }}>
                    Answered {answeredCount} / {totalQuestions}
                  </p>
                </div>
              </div>

              {saveError && (
                <div className="quiz-state-card" role="alert" style={{ marginBottom: 12 }}>
                  <strong>Result not confirmed</strong>
                  <p>{saveError}</p>
                </div>
              )}

              {currentQuestion ? (
                <div className="card-like quiz-question-card">
                  <div className="quiz-question-label">
                    <span>Question {currentQuestionIndex + 1}</span>
                    <small>{totalQuestions} total</small>
                  </div>
                  <h3 className="quiz-question-title">{currentQuestion.question}</h3>

                  <div className="quiz-options">
                    {(Array.isArray(currentQuestion.options) ? currentQuestion.options : []).map((option, index) => {
                      const optionLetter = String.fromCharCode(65 + index);
                      const isSelected =
                        selectedAnswers[currentQuestion.id] === optionLetter;

                      return (
                        <label
                          key={`${currentQuestion.id}-${option}-${index}`}
                          className={`quiz-option ${isSelected ? 'selected' : ''}`}
                        >
                          <input
                            type="radio"
                            name={`question-${currentQuestion.id}`}
                            value={optionLetter}
                            checked={isSelected}
                            onChange={() =>
                              handleSelectAnswer(currentQuestion.id, optionLetter)
                            }
                          />
                          <span className="quiz-option-badge">{optionLetter}</span>
                          <span>{option}</span>
                        </label>
                      );
                    })}
                  </div>

                  <div className="row-between wrap-gap top-gap">
                    <button
                      className="secondary-btn"
                      onClick={handlePrevious}
                      disabled={currentQuestionIndex === 0}
                    >
                      Previous
                    </button>

                    <div className="button-group wrap-gap">
                      {currentQuestionIndex < totalQuestions - 1 ? (
                        <button
                          className="primary-btn"
                          onClick={handleNext}
                          disabled={selectedAnswers[currentQuestion.id] === undefined}
                        >
                          Next
                        </button>
                      ) : (
                        <button
                          className="primary-btn"
                          onClick={handleSubmit}
                          disabled={answeredCount !== totalQuestions || submitting}
                        >
                          {submitting ? 'Submitting…' : 'Submit Quiz'}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="quiz-state-card">
                  <span className="quiz-state-icon" aria-hidden="true">!</span>
                  <strong>No questions found</strong>
                  <p>This quiz does not contain any questions yet.</p>
                </div>
              )}
            </>
          ) : (
            <div className="card-like quiz-result-card">
              <div className="quiz-result-summary">
                <p role="status" className="quiz-save-status">
                  {saveStatus === 'saved' ? 'Result saved to system.' : 'Saving not confirmed.'}
                </p>
                <span className="quiz-result-kicker">Quiz Result</span>
                <div className="quiz-result-score">{score}%</div>
                <strong>
                  {score >= 80
                    ? 'Great work'
                    : score >= 60
                      ? 'Good progress'
                      : 'Keep practising'}
                </strong>
                <p>
                  You answered {correctCount} out of {serverResult?.total_questions ?? totalQuestions} questions correctly.
                </p>
              </div>

              <div className="stack-gap top-gap">
                <p className="muted small">Your submitted answers are shown below. Individual correct answers are not provided by this API.</p>
                {questions.map((question, index) => {
                  const selectedLetter = selectedAnswers[question.id];
                  const selectedIndex = selectedLetter ? selectedLetter.charCodeAt(0) - 65 : -1;
                  const selectedText = question.options?.[selectedIndex] || 'No answer';
                  return (
                    <div key={question.id} className="quiz-review-card">
                      <h4 style={{ marginBottom: '8px' }}>{index + 1}. {question.question}</h4>
                      <p className="muted" style={{ marginBottom: 0 }}>
                        Your answer: {selectedLetter ? `${selectedLetter}. ` : ''}{selectedText}
                      </p>
                    </div>
                  );
                })}
              </div>

              <div className="button-group wrap-gap top-gap">
                <button className="secondary-btn" onClick={handleRetake}>
                  Retake Quiz
                </button>
                <button className="primary-btn" onClick={handleBackToList}>
                  Back to Quiz List
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}