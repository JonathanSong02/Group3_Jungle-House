import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import '../styles/Quiz.css';

export default function QuizList() {
  const { user } = useAuth();
  const { t, tOr } = useLanguage();
  const staffMode = String(user?.role || '').toLowerCase() === 'staff';
  const titleLabel = (title) => (title === 'AI Generated Quiz' ? t('qm.defaultAiTitle') : title);
  const catLabel = (category) => tOr(`cat.${category}`, category);
  // Descriptions written by the AI builder are stored in English; translate those.
  const localizeDescription = (text) => {
    const match = String(text || '').match(/^AI generated quiz based on the latest verified (.*) content\.$/);
    if (match) return t('quiz.autoDesc', { category: catLabel(match[1]) });
    const plain = String(text || '').match(/^Quiz generated from the latest verified (.*) content\.$/);
    return plain ? t('quiz.autoDescTemplate', { category: catLabel(plain[1]) }) : text;
  };
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
  const [showUnanswered, setShowUnanswered] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const startedAtRef = useRef(null);

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
          difficulty: quiz.difficulty,
          questions: [],
        }));

        setQuizItems(formattedQuizzes);
      } else {
        setQuizItems([]);
      }
    } catch (err) {
      console.error('Failed to load quizzes:', err);
      setQuizItems([]);
      setQuizError(err.response?.data?.message || t('quiz.err.loadList'));
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
      setQuestionError(err.response?.data?.message || t('quiz.err.loadQs'));
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
  const passingScore = Number(serverResult?.passing_score ?? 80);
  const passed = serverResult?.passed ?? score >= passingScore;
  const sourceArticle = serverResult?.source_article || null;

  const formatElapsed = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const rest = seconds % 60;
    return minutes > 0 ? `${minutes}m ${String(rest).padStart(2, '0')}s` : `${rest}s`;
  };

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
    startedAtRef.current = Date.now();
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
    if (submitting || submitted || !activeQuizId || !totalQuestions) {
      return;
    }

    if (answeredCount !== totalQuestions) {
      setShowUnanswered(true);
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
      setElapsedSeconds(
        startedAtRef.current ? Math.round((Date.now() - startedAtRef.current) / 1000) : 0
      );
      setSaveStatus('saved');
      setSubmitted(true);
    } catch (submitError) {
      console.warn('Quiz result save was not confirmed:', submitError);
      setSaveStatus('unsaved');
      setSaveError(
        submitError.response?.data?.message ||
        t('quiz.err.unconfirmed')
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
  const unansweredNumbers = questions
    .map((item, index) => (selectedAnswers[item.id] === undefined ? index + 1 : null))
    .filter(Boolean);

  return (
    <div className={`quiz-page ${staffMode ? 'staff-quiz-page' : ''}`}>
      <PageHeader
        title={staffMode ? t('quiz.page.titleStaff') : t('quiz.page.title')}
        subtitle={staffMode ? t('quiz.page.subtitleStaff') : t('quiz.page.subtitle')}
      />

      {staffMode && !activeQuiz && !loadingQuizzes && quizItems.length > 0 ? (
        <div className="staff-quiz-filters" role="group" aria-label={t('quiz.filterAria')}
          style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
          {categories.map((category) => (
            <button key={category} type="button"
              className={categoryFilter === category ? 'primary-btn' : 'secondary-btn'}
              aria-pressed={categoryFilter === category}
              onClick={() => setCategoryFilter(category)}>{catLabel(category)}</button>
          ))}
        </div>
      ) : null}

      {!activeQuiz ? (
        <div className="cards-grid quiz-list-grid"
          style={staffMode ? { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: 16 } : undefined}>
          {loadingQuizzes ? (
            <div className="quiz-state-card" aria-live="polite">
              <span className="quiz-loading-spinner" aria-hidden="true" />
              <strong>{t('quiz.loadingList')}</strong>
              <p>{t('quiz.loadingListHint')}</p>
            </div>
          ) : quizError ? (
            <div className="quiz-state-card" role="alert">
              <strong>{t('quiz.loadFailedTitle')}</strong>
              <p>{quizError}</p>
              <button type="button" className="secondary-btn" onClick={fetchQuizzes}>{t('quiz.retry')}</button>
            </div>
          ) : quizItems.length === 0 ? (
            <div className="quiz-state-card">
              <span className="quiz-state-icon" aria-hidden="true">?</span>
              <strong>{t('quiz.noneTitle')}</strong>
              <p>{t('quiz.noneHint')}</p>
            </div>
          ) : (
            visibleQuizzes.map((quiz) => (
              <article key={quiz.id} className="card-like quiz-card">
                <div className="quiz-card-top">
                  <div className="quiz-card-heading">
                    <span className="quiz-card-icon" aria-hidden="true">✓</span>
                    <div>
                      <span className="quiz-card-kicker">
                        {catLabel(quiz.category || 'Training')}
                      </span>
                      <h3>{titleLabel(quiz.title)}</h3>
                    </div>
                  </div>

                  {quiz.difficulty ? (
                    <span className={`quiz-diff-badge ${String(quiz.difficulty).toLowerCase()}`}>
                      {tOr(`quiz.difficulty.${quiz.difficulty}`, quiz.difficulty)}
                    </span>
                  ) : null}
                  {!staffMode && <span className="status-badge pending">{t('quiz.trainingQuiz')}</span>}
                </div>

                {quiz.description ? (
                  <p className="quiz-card-description">{staffMode && quiz.description.length > 100 ? `${localizeDescription(quiz.description).slice(0, 97).trim()}…` : localizeDescription(quiz.description)}</p>
                ) : (
                  !staffMode && <p className="quiz-card-description">
                    {t('quiz.defaultDesc')}
                  </p>
                )}

                <div className="quiz-card-meta">
                  <span>
                    <strong>{quiz.questionCount ?? 0}</strong>
                    {t('quiz.questionsLabel')}
                  </span>
                  {/* The current /quizzes API provides no previous score. Do not show a fabricated 0%. */}
                </div>

                <button
                  type="button"
                  className="primary-btn quiz-card-action"
                  onClick={() => handleStartQuiz(quiz.id)}
                  disabled={!quiz.questionCount}
                >
                  {staffMode ? t('quiz.start') : t('quiz.attempt')}
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
                <h2 className="quiz-session-title">{titleLabel(activeQuiz.title)}</h2>
                {!showWelcome ? (
                  <p className="muted" style={{ marginBottom: 0 }}>
                    {t('quiz.questionN', { n: currentQuestionIndex + 1, total: totalQuestions })}
                  </p>
                ) : (
                  <p className="muted" style={{ marginBottom: 0 }}>
                    {t('quiz.welcomeTo')}
                  </p>
                )}
              </div>

              <div className="button-group wrap-gap">
                <button className="secondary-btn" onClick={handleBackToList}>
                  {t('quiz.backToList')}
                </button>
              </div>
            </div>
          </div>

          {showWelcome ? staffMode ? (
            <div className="card-like quiz-welcome-card staff-quiz-welcome">
              <span className="eyebrow">{t('quiz.ready')}</span>
              <h2>{titleLabel(activeQuiz.title)}</h2>
              <p>{t('quiz.readyInfo', { n: totalQuestions })}</p>
              {loadingQuestions && <p role="status">{t('quiz.loadingQs')}</p>}
              {questionError && <p role="alert">{questionError}</p>}
              {!loadingQuestions && !questionError && totalQuestions === 0 && <p>{t('quiz.noQs')}</p>}
              <div className="button-group wrap-gap top-gap">
                <button type="button" className="secondary-btn" onClick={handleBackToList}>{t('quiz.back')}</button>
                {questionError ? (
                  <button type="button" className="primary-btn" onClick={() => fetchQuizQuestions(activeQuizId)}>{t('quiz.retry')}</button>
                ) : (
                  <button type="button" className="primary-btn"
                    onClick={handleBeginQuestions} disabled={loadingQuestions || totalQuestions === 0}>{t('quiz.begin')}</button>
                )}
              </div>
            </div>
          ) : (
            <div className="card-like quiz-welcome-card">
              <p className="eyebrow">{t('quiz.welcome.kicker')}</p>
              <h2 style={{ marginBottom: '10px' }}>
                {t('quiz.welcome.title')}
              </h2>

              <div className="quiz-welcome-message">
                <p>{t('quiz.welcome.dear')}</p>
                <p>{t('quiz.welcome.p1')}</p>
                <p>{t('quiz.welcome.p2')}</p>
                <p>{t('quiz.welcome.p3')}</p>
                <p>{t('quiz.welcome.p4')}</p>
                <p>{t('quiz.welcome.p5')}</p>

                <p style={{ marginBottom: 0 }}>
                  {t('quiz.welcome.regards')}
                  <br />
                  <strong>Eno Wong</strong>
                  <br />
                  King Bee (Kuching)
                </p>
              </div>

              <div className="button-group wrap-gap top-gap">
                <button className="secondary-btn" onClick={handleBackToList}>
                  {t('quiz.back')}
                </button>
                <button className="primary-btn" onClick={handleBeginQuestions}>
                  {t('quiz.welcome.start')}
                </button>
              </div>
            </div>
          ) : loadingQuestions ? (
            <div className="card-like">
              <p>{t('quiz.loadingQuiz')}</p>
            </div>
          ) : !submitted ? (
            <>
              {staffMode && totalQuestions > 0 && (
                <nav className="staff-quiz-question-nav" aria-label={t('quiz.questionsNav')}
                  style={{ display: 'flex', flexWrap: 'nowrap', overflowX: 'auto', gap: 8, marginBottom: 12, paddingBottom: 4, maxWidth: '100%' }}>
                  {questions.map((item, index) => (
                    <button key={item.id} type="button"
                      className={index === currentQuestionIndex ? 'primary-btn' : 'secondary-btn'}
                      aria-label={selectedAnswers[item.id] !== undefined ? t('quiz.navAnswered', { n: index + 1 }) : t('quiz.navQuestion', { n: index + 1 })}
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
                    {t('quiz.answered', { n: answeredCount, total: totalQuestions })}
                  </p>
                </div>
              </div>

              {saveError && (
                <div className="quiz-state-card" role="alert" style={{ marginBottom: 12 }}>
                  <strong>{t('quiz.notConfirmed')}</strong>
                  <p>{saveError}</p>
                </div>
              )}

              {currentQuestion ? (
                <div className="card-like quiz-question-card">
                  <div className="quiz-question-label">
                    <span>{t('quiz.navQuestion', { n: currentQuestionIndex + 1 })}</span>
                    <small>{t('quiz.totalN', { n: totalQuestions })}</small>
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
                      {t('quiz.previous')}
                    </button>

                    <div className="button-group wrap-gap">
                      {currentQuestionIndex < totalQuestions - 1 ? (
                        <button
                          className="primary-btn"
                          onClick={handleNext}
                          disabled={selectedAnswers[currentQuestion.id] === undefined}
                        >
                          {t('quiz.next')}
                        </button>
                      ) : (
                        <button
                          className="primary-btn"
                          onClick={handleSubmit}
                          disabled={submitting}
                        >
                          {submitting ? t('quiz.submitting') : t('quiz.submit')}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="quiz-state-card">
                  <span className="quiz-state-icon" aria-hidden="true">!</span>
                  <strong>{t('quiz.noQsFound')}</strong>
                  <p>{t('quiz.noQsFoundHint')}</p>
                </div>
              )}
            </>
          ) : (
            <div className="card-like quiz-result-card">
              <div className={`quiz-result-summary quiz-rv-header ${passed ? 'is-pass' : 'is-fail'}`}>
                <p role="status" className="quiz-save-status">
                  {saveStatus === 'saved' ? t('quiz.result.saved') : t('quiz.savingNotConfirmed')}
                </p>
                <span className="quiz-result-kicker">{t('quiz.result.title')}</span>
                <div className="quiz-result-score">{score}%</div>
                <span className={`quiz-rv-badge ${passed ? 'pass' : 'fail'}`}>
                  {passed ? '✓ ' : '✗ '}
                  {passed ? t('quiz.result.pass') : t('quiz.result.fail')}
                </span>
                <p>
                  {t('quiz.result.summary', {
                    score: correctCount,
                    total: serverResult?.total_questions ?? totalQuestions,
                  })}
                </p>
                <p className="muted small">
                  {t('quiz.result.passMark', { n: passingScore })}
                  {elapsedSeconds > 0
                    ? ` · ${t('quiz.result.time', { time: formatElapsed(elapsedSeconds) })}`
                    : ''}
                </p>
              </div>

              <div className="stack-gap top-gap">
                <h3 className="quiz-rv-title">{t('quiz.result.review')}</h3>
                {questions.map((question, index) => {
                  const selectedLetter = selectedAnswers[question.id];
                  const reviewEntry = serverResult?.review?.find(
                    (entry) => entry.question_id === question.id
                  );
                  const correctLetter = reviewEntry?.correct_answer || reviewEntry?.correct_option || '';
                  const isCorrect = reviewEntry?.is_correct === true;

                  return (
                    <div
                      key={question.id}
                      className={`quiz-review-card quiz-rv-card ${isCorrect ? 'is-correct' : 'is-wrong'}`}
                    >
                      <h4 className="quiz-rv-question">
                        <span className="quiz-rv-mark" aria-hidden="true">{isCorrect ? '✓' : '✗'}</span>
                        {index + 1}. {question.question}
                      </h4>

                      <ul className="quiz-rv-options">
                        {(Array.isArray(question.options) ? question.options : []).map((option, optionIndex) => {
                          const letter = String.fromCharCode(65 + optionIndex);
                          const isChosen = selectedLetter === letter;
                          const isAnswer = correctLetter === letter;
                          let state = '';
                          if (isAnswer) state = 'correct';
                          else if (isChosen) state = 'wrong';

                          return (
                            <li key={letter} className={`quiz-rv-option ${state} ${isChosen ? 'chosen' : ''}`}>
                              <span className="quiz-rv-letter">{letter}</span>
                              <span className="quiz-rv-text">{option}</span>
                              <span className="quiz-rv-tag">
                                {isChosen && isAnswer ? `✓ ${t('quiz.result.yourAnswer')}` : null}
                                {isChosen && !isAnswer ? `✗ ${t('quiz.result.yourAnswer')}` : null}
                                {!isChosen && isAnswer ? t('quiz.result.correctAnswer') : null}
                              </span>
                            </li>
                          );
                        })}
                        {!selectedLetter ? (
                          <li className="quiz-rv-option wrong">{t('quiz.result.noAnswer')}</li>
                        ) : null}
                      </ul>

                      {reviewEntry?.explanation ? (
                        <div className="quiz-rv-explanation">
                          <strong>{t('quiz.result.explanation')}:</strong> {reviewEntry.explanation}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>

              {sourceArticle ? (
                <Link to={`/knowledge/${sourceArticle.id}`} className="quiz-rv-source">
                  📖 {t('quiz.result.readSource', { title: sourceArticle.title })}
                </Link>
              ) : null}

              <div className="button-group wrap-gap top-gap">
                <button className="secondary-btn" onClick={handleRetake}>
                  {t('quiz.result.retake')}
                </button>
                <button className="primary-btn" onClick={handleBackToList}>
                  {t('quiz.result.back')}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {showUnanswered ? (
        <div className="quiz-rv-overlay" role="dialog" aria-modal="true" aria-labelledby="quiz-unanswered-title">
          <div className="quiz-rv-modal">
            <h3 id="quiz-unanswered-title">{t('quiz.unanswered.title')}</h3>
            <p>
              {t('quiz.unanswered.body', {
                n: unansweredNumbers.length,
                list: unansweredNumbers.map((n) => `Q${n}`).join(', '),
              })}
            </p>
            <p className="muted small">{t('quiz.answerAll')}</p>
            <div className="button-group wrap-gap">
              <button
                type="button"
                className="primary-btn"
                onClick={() => {
                  setShowUnanswered(false);
                  setCurrentQuestionIndex(Math.max(0, unansweredNumbers[0] - 1));
                }}
              >
                {t('quiz.unanswered.go')}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
