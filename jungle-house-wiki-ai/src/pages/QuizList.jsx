import { useEffect, useMemo, useRef, useState } from 'react';
import PageHeader from '../components/PageHeader';
import api from '../services/api';

export default function QuizList() {
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

      const response = await api.get('/quizzes');
      const data = response.data;

      if (Array.isArray(data)) {
        const formattedQuizzes = data.map((quiz) => ({
          id: quiz.quiz_id,
          title: quiz.title,
          description: quiz.description,
          category: quiz.category,
          questionCount: quiz.question_count,
          lastScore: 0,
          questions: [],
        }));

        setQuizItems(formattedQuizzes);
      } else {
        setQuizItems([]);
      }
    } catch (err) {
      console.error('Failed to load quizzes:', err);
      setQuizItems([]);
    } finally {
      setLoadingQuizzes(false);
    }
  };

  const fetchQuizQuestions = async (quizId) => {
    try {
      setLoadingQuestions(true);

      const response = await api.get(`/quizzes/${quizId}/questions`);
      const data = response.data;

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
    } finally {
      setLoadingQuestions(false);
    }
  };

  const activeQuiz = useMemo(
    () => quizItems.find((quiz) => quiz.id === activeQuizId) || null,
    [quizItems, activeQuizId]
  );

  const questions = activeQuiz?.questions || [];
  const currentQuestion = questions[currentQuestionIndex];
  const totalQuestions = questions.length;

  const score = useMemo(() => {
    if (!activeQuiz) return 0;

    let correctCount = 0;

    activeQuiz.questions.forEach((question) => {
      if (selectedAnswers[question.id] === question.correctAnswer) {
        correctCount += 1;
      }
    });

    return totalQuestions > 0 ? Math.round((correctCount / totalQuestions) * 100) : 0;
  }, [activeQuiz, selectedAnswers, totalQuestions]);

  const correctCount = useMemo(() => {
    if (!activeQuiz) return 0;

    let count = 0;

    activeQuiz.questions.forEach((question) => {
      if (selectedAnswers[question.id] === question.correctAnswer) {
        count += 1;
      }
    });

    return count;
  }, [activeQuiz, selectedAnswers]);

  const handleStartQuiz = async (quizId) => {
    clearAutoNextTimer();

    setActiveQuizId(quizId);
    setCurrentQuestionIndex(0);
    setSelectedAnswers({});
    setSubmitted(false);
    setShowWelcome(true);

    await fetchQuizQuestions(quizId);
  };

  const handleBeginQuestions = () => {
    clearAutoNextTimer();
    setShowWelcome(false);
  };

  const handleSelectAnswer = (questionId, optionValue) => {
    if (submitted) return;

    clearAutoNextTimer();

    setSelectedAnswers((prev) => ({
      ...prev,
      [questionId]: optionValue,
    }));

    if (currentQuestionIndex < totalQuestions - 1) {
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

  const getStoredUser = () => {
    const possibleKeys = ['user', 'currentUser', 'authUser', 'loggedInUser'];

    for (const key of possibleKeys) {
      try {
        const value = localStorage.getItem(key);

        if (!value) continue;

        const parsed = JSON.parse(value);

        if (parsed?.user) return parsed.user;
        if (parsed?.id || parsed?.user_id || parsed?.userId) return parsed;
      } catch (error) {
        console.warn(`Unable to read localStorage key: ${key}`, error);
      }
    }

    for (let index = 0; index < localStorage.length; index += 1) {
      try {
        const key = localStorage.key(index);
        const value = localStorage.getItem(key);

        if (!value) continue;

        const parsed = JSON.parse(value);

        if (parsed?.user?.id || parsed?.user?.user_id || parsed?.user?.userId) {
          return parsed.user;
        }

        if (parsed?.id || parsed?.user_id || parsed?.userId) {
          return parsed;
        }
      } catch (error) {
        // Ignore non-JSON localStorage values.
      }
    }

    return null;
  };

  const handleSubmit = async () => {
    try {
      clearAutoNextTimer();

      const user = getStoredUser();
      const userId = user?.id || user?.user_id || user?.userId || null;

      const payload = {
        user_id: userId,
        userId: userId,
        score: correctCount,
        total_questions: totalQuestions,
        percentage: score,
      };

      console.log('QUIZ RESULT SUBMIT PAYLOAD:', payload);

      try {
        const response = await api.post(`/quizzes/${activeQuizId}/submit`, payload);
        console.log('QUIZ RESULT SUBMIT RESPONSE:', response.data);
      } catch (submitError) {
        console.warn(
          'Quiz result save failed, but quiz will still show result:',
          submitError
        );
      }

      setSubmitted(true);
    } catch (err) {
      console.error('Failed to submit quiz:', err);
      alert('Failed to submit quiz. Please check Browser Console.');
    }
  };

  const handleRetake = () => {
    clearAutoNextTimer();

    setCurrentQuestionIndex(0);
    setSelectedAnswers({});
    setSubmitted(false);
    setShowWelcome(true);
  };

  const handleBackToList = () => {
    clearAutoNextTimer();

    setActiveQuizId(null);
    setCurrentQuestionIndex(0);
    setSelectedAnswers({});
    setSubmitted(false);
    setShowWelcome(false);
  };

  const answeredCount = Object.keys(selectedAnswers).length;

  return (
    <div>
      <PageHeader
        title="Quiz / Training"
        subtitle="Support onboarding with basic quizzes and learning reinforcement."
      />

      {!activeQuiz ? (
        <div className="cards-grid">
          {loadingQuizzes ? (
            <p>Loading quizzes...</p>
          ) : quizItems.length === 0 ? (
            <p>No quiz found.</p>
          ) : (
            quizItems.map((quiz) => (
              <article key={quiz.id} className="card-like quiz-card">
                <div className="quiz-card-top">
                  <h3>{quiz.title}</h3>
                  <span className="status-badge pending">Training Quiz</span>
                </div>

                <p className="muted">
                  Questions: {quiz.questionCount ?? 0}
                </p>
                <p className="muted">Last score: {quiz.lastScore ?? 0}%</p>

                <button
                  className="primary-btn"
                  onClick={() => handleStartQuiz(quiz.id)}
                >
                  Attempt Quiz
                </button>
              </article>
            ))
          )}
        </div>
      ) : (
        <div className="stack-gap">
          <div className="card-like">
            <div className="row-between wrap-gap">
              <div>
                <h2 style={{ marginBottom: '8px' }}>{activeQuiz.title}</h2>
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

          {showWelcome ? (
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
              <div className="card-like">
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

              {currentQuestion ? (
                <div className="card-like quiz-question-card">
                  <p className="eyebrow">Question</p>
                  <h3 className="quiz-question-title">{currentQuestion.question}</h3>

                  <div className="quiz-options">
                    {currentQuestion.options.map((option, index) => {
                      const optionLetter = String.fromCharCode(65 + index);
                      const isSelected =
                        selectedAnswers[currentQuestion.id] === option;

                      return (
                        <label
                          key={`${currentQuestion.id}-${option}-${index}`}
                          className={`quiz-option ${isSelected ? 'selected' : ''}`}
                        >
                          <input
                            type="radio"
                            name={`question-${currentQuestion.id}`}
                            value={option}
                            checked={isSelected}
                            onChange={() =>
                              handleSelectAnswer(currentQuestion.id, option)
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
                          disabled={!selectedAnswers[currentQuestion.id]}
                        >
                          Next
                        </button>
                      ) : (
                        <button
                          className="primary-btn"
                          onClick={handleSubmit}
                          disabled={answeredCount !== totalQuestions}
                        >
                          Submit Quiz
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="card-like">
                  <p>No questions found for this quiz.</p>
                </div>
              )}
            </>
          ) : (
            <div className="card-like quiz-result-card">
              <p className="eyebrow">Quiz Result</p>
              <h2 style={{ marginBottom: '10px' }}>{score}%</h2>
              <p className="muted">
                You answered {correctCount} out of{' '}
                {totalQuestions} questions correctly.
              </p>

              <div className="stack-gap top-gap">
                {questions.map((question, index) => {
                  const selected = selectedAnswers[question.id];
                  const isCorrect = selected === question.correctAnswer;

                  return (
                    <div key={question.id} className="quiz-review-card">
                      <h4 style={{ marginBottom: '8px' }}>
                        {index + 1}. {question.question}
                      </h4>
                      <p className={isCorrect ? 'success-text' : 'error-text'}>
                        Your answer: {selected || 'No answer'}
                      </p>
                      {!isCorrect ? (
                        <p className="muted" style={{ marginBottom: 0 }}>
                          Correct answer: {question.correctAnswer}
                        </p>
                      ) : null}
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