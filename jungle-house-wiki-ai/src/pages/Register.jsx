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
  const [registrationResult, setRegistrationResult] = useState(null);

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

      setRegistrationResult(response.data || {});
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
            Register using your own email. Your account will be reviewed by a
            Manager or Team Leader before one-time key activation.
          </p>
        </div>

        <div className="auth-registration-flow" aria-label="Registration steps">
          <span className="current">1. Register</span>
          <span>2. Approval</span>
          <span>3. Activation Key</span>
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
              Your account request has been received. A Manager or Team Leader
              will normally review it within 24 hours. No action is required now.
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
                <span>If approved, receive and enter the one-time registration key</span>
              </div>
            </div>

            <div className="auth-email-status">
              {registrationResult?.email_sent === false
                ? 'Your registration was saved, but the confirmation email could not be delivered. Your account is still pending review.'
                : 'A registration-received confirmation has been sent to your email. You will receive another email after approval or rejection.'}
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
