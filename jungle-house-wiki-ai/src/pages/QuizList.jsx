import PageHeader from '../components/PageHeader';
import { quizItems } from '../data/mockData';

export default function QuizList() {
  return (
    <div>
      <PageHeader
        title="Quiz / Training"
        subtitle="Support onboarding with basic quizzes and learning reinforcement."
      />

      <div className="cards-grid">
        {quizItems.map((quiz) => (
          <article key={quiz.id} className="card-like">
            <h3>{quiz.title}</h3>
            <p className="muted">Questions: {quiz.questions}</p>
            <p className="muted">Last score: {quiz.lastScore}%</p>
            <button className="primary-btn">Attempt Quiz</button>
          </article>
        ))}
      </div>
    </div>
  );
}
