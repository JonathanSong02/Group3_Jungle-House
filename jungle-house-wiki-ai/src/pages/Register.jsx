import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../services/api';
import '../styles/AuthSecurity.css';

export default function Register() {
  const navigate = useNavigate();

  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    confirm_password: '',
  });

  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPasswords, setShowPasswords] = useState(false);
  const [showSuccessModal, setShowSuccessModal] = useState(false);

  const handleChange = (event) => {
    const { name, value } = event.target;

    setForm((previous) => ({
      ...previous,
      [name]: value,
    }));

    if (error) setError('');
  };

  const passwordChecks = useMemo(
    () => ({
      length: form.password.length >= 8,
      uppercase: /[A-Z]/.test(form.password),
      number: /\d/.test(form.password),
      match:
        Boolean(form.confirm_password) &&
        form.password === form.confirm_password,
    }),
    [form.password, form.confirm_password]
  );

  const passwordValid =
    passwordChecks.length &&
    passwordChecks.uppercase &&
    passwordChecks.number;

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');

    if (form.password !== form.confirm_password) {
      setError('Passwords do not match.');
      return;
    }

    if (!passwordValid) {
      setError(
        'Password must be at least 8 characters and include an uppercase letter and a number.'
      );
      return;
    }

    try {
      setLoading(true);

      const response = await api.post('/auth/register', {
        full_name: form.full_name.trim(),
        email: form.email.trim().toLowerCase(),
        password: form.password,
        confirm_password: form.confirm_password,
        role: 'staff',
      });

      // Only show success after the backend confirms a pending registration.
      // A failed HTTP response must not display the success popup.
      if (response.status !== 201 || response.data?.account_status !== 'pending') {
        throw new Error('The server did not confirm your pending registration.');
      }

      setShowSuccessModal(true);
    } catch (requestError) {
      setError(
        requestError.response?.data?.message ||
          'Registration could not be submitted. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  };

  const goToLogin = () => {
    setShowSuccessModal(false);
    navigate('/login');
  };

  return (
    <div className="login-page">
      <div className="login-card card-like auth-card">
        <div className="auth-brand">
          <span className="auth-brand-mark" aria-hidden="true">
            JH
          </span>
          <div>
            <p className="eyebrow">Jungle House AI Wiki</p>
            <span>Staff account registration</span>
          </div>
        </div>

        <div className="auth-heading">
          <h1>Create your account</h1>
          <p>
            Submit your details for Manager or Team Leader approval. You can
            sign in once your account is approved.
          </p>
        </div>

        <div className="auth-registration-flow" aria-label="Registration steps">
          <span className="current">1. Register</span>
          <span>2. Approval</span>
          <span>3. Sign In</span>
        </div>

        <form onSubmit={handleSubmit} className="form-stack auth-form">
          <label>
            Full name
            <input
              type="text"
              name="full_name"
              placeholder="Enter your full name"
              value={form.full_name}
              onChange={handleChange}
              autoComplete="name"
              required
            />
          </label>

          <label>
            Email address
            <input
              type="email"
              name="email"
              placeholder="you@example.com"
              value={form.email}
              onChange={handleChange}
              autoComplete="email"
              required
            />
          </label>

          <div className="row-between">
            <strong className="auth-field-heading">Password</strong>
            <button
              type="button"
              className="auth-inline-action"
              onClick={() => setShowPasswords((previous) => !previous)}
            >
              {showPasswords ? 'Hide' : 'Show'}
            </button>
          </div>

          <input
            type={showPasswords ? 'text' : 'password'}
            name="password"
            placeholder="Create password"
            value={form.password}
            onChange={handleChange}
            autoComplete="new-password"
            required
          />

          <input
            type={showPasswords ? 'text' : 'password'}
            name="confirm_password"
            placeholder="Confirm password"
            value={form.confirm_password}
            onChange={handleChange}
            autoComplete="new-password"
            required
          />

          <div className="auth-password-checks">
            <span className={passwordChecks.length ? 'passed' : ''}>
              {passwordChecks.length ? '✓' : '○'} 8+ characters
            </span>
            <span className={passwordChecks.uppercase ? 'passed' : ''}>
              {passwordChecks.uppercase ? '✓' : '○'} Uppercase
            </span>
            <span className={passwordChecks.number ? 'passed' : ''}>
              {passwordChecks.number ? '✓' : '○'} Number
            </span>
            <span className={passwordChecks.match ? 'passed' : ''}>
              {passwordChecks.match ? '✓' : '○'} Passwords match
            </span>
          </div>

          {error ? (
            <p className="auth-error-message" role="alert">
              {error}
            </p>
          ) : null}

          <button
            className="primary-btn auth-primary-action"
            type="submit"
            disabled={loading}
          >
            {loading ? 'Submitting registration...' : 'Submit Registration'}
          </button>

          <div className="auth-footer-row">
            <span>Already registered?</span>
            <Link to="/login" className="text-link">
              Back to Sign In
            </Link>
          </div>
        </form>
      </div>

      {showSuccessModal ? (
        <div className="auth-modal-overlay" role="presentation">
          <div
            className="auth-success-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="registration-success-title"
          >
            <span className="auth-success-mark" aria-hidden="true">
              ✓
            </span>

            <p className="eyebrow">Registration submitted</p>
            <h2 id="registration-success-title">Registration received</h2>

            <p>
              Your registration request has been received successfully.
              Please allow up to 24 hours for a Manager or Team Leader to
              review your account.
            </p>

            <div className="auth-success-steps">
              <div className="done">
                <strong>1</strong>
                <span>Registration submitted</span>
              </div>
              <div>
                <strong>2</strong>
                <span>Manager / Team Leader review</span>
              </div>
              <div>
                <strong>3</strong>
                <span>Once approved, sign in with your email and password</span>
              </div>
            </div>

            <div className="auth-email-status" role="status">
              Account status: Awaiting approval. You can try signing in after
              your Manager or Team Leader has approved your registration.
            </div>

            <button
              type="button"
              className="primary-btn auth-primary-action"
              onClick={goToLogin}
            >
              Go to Sign In
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
