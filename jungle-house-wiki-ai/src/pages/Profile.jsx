import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../components/PageHeader';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

function ProfileIcon({ name, size = 18 }) {
  const common = {
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

  const paths = {
    edit: (
      <>
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" />
      </>
    ),
    refresh: (
      <>
        <path d="M20 7v5h-5" />
        <path d="M4 17v-5h5" />
        <path d="M6.1 9A7 7 0 0 1 18.3 6.4L20 8" />
        <path d="M4 16l1.7 1.6A7 7 0 0 0 17.9 15" />
      </>
    ),
    lock: (
      <>
        <rect x="4" y="10" width="16" height="10" rx="2" />
        <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      </>
    ),
    user: (
      <>
        <circle cx="12" cy="8" r="4" />
        <path d="M4 21a8 8 0 0 1 16 0" />
      </>
    ),
    mail: (
      <>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="m3 7 9 6 9-6" />
      </>
    ),
    calendar: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M16 3v4M8 3v4M3 10h18" />
      </>
    ),
    shield: (
      <>
        <path d="M12 3 5 6v5c0 5 3 8 7 10 4-2 7-5 7-10V6Z" />
        <path d="m9 12 2 2 4-4" />
      </>
    ),
    eye: (
      <>
        <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" />
        <circle cx="12" cy="12" r="2.5" />
      </>
    ),
    eyeOff: (
      <>
        <path d="m3 3 18 18" />
        <path d="M10.6 6.2A10.8 10.8 0 0 1 12 6c6.5 0 10 6 10 6" />
        <path d="M6.2 6.2C3.4 8 2 12 2 12s3.5 6 10 6a10.5 10.5 0 0 0 4.1-.8" />
      </>
    ),
  };

  return <svg {...common}>{paths[name] || null}</svg>;
}

export default function Profile() {
  const { user, updateUser, refreshUser } = useAuth();

  const [fullName, setFullName] = useState(user?.full_name || user?.name || '');
  const [email, setEmail] = useState(user?.email || '');

  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [isEditingPassword, setIsEditingPassword] = useState(false);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const [saveMessage, setSaveMessage] = useState('');
  const [saveError, setSaveError] = useState('');
  const [passwordMessage, setPasswordMessage] = useState('');
  const [passwordError, setPasswordError] = useState('');

  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [isSavingPassword, setIsSavingPassword] = useState(false);
  const [isLoadingProfile, setIsLoadingProfile] = useState(false);

  useEffect(() => {
    setFullName(user?.full_name || user?.name || '');
    setEmail(user?.email || '');
  }, [user]);

  const initialName = user?.full_name || user?.name || '';
  const initialEmail = user?.email || '';

  const displayName = fullName || user?.full_name || user?.name || '';
  const displayEmail = email || user?.email || '';
  const displayRole = user?.role || '-';
  const displayStatus = user?.status || 'active';
  const displayCreatedAt = user?.created_at || 'Not available';

  const userInitial = useMemo(
    () => (displayName || 'U').trim().charAt(0).toUpperCase(),
    [displayName]
  );

  const profileChanged =
    fullName.trim() !== initialName.trim() ||
    email.trim() !== initialEmail.trim();

  const profileCompleteness = useMemo(() => {
    const values = [displayName, displayEmail, displayRole, displayStatus];
    const completed = values.filter(
      (value) => value && value !== '-' && String(value).trim()
    ).length;

    return Math.round((completed / values.length) * 100);
  }, [displayName, displayEmail, displayRole, displayStatus]);

  const passwordChecks = useMemo(
    () => ({
      length: newPassword.length >= 8,
      uppercase: /[A-Z]/.test(newPassword),
      lowercase: /[a-z]/.test(newPassword),
      number: /\d/.test(newPassword),
    }),
    [newPassword]
  );

  const passwordStrength = useMemo(() => {
    const passed = Object.values(passwordChecks).filter(Boolean).length;

    if (!newPassword) {
      return { percent: 0, label: 'Not entered', className: 'empty' };
    }
    if (passed <= 1) {
      return { percent: 25, label: 'Weak', className: 'weak' };
    }
    if (passed === 2) {
      return { percent: 50, label: 'Fair', className: 'fair' };
    }
    if (passed === 3) {
      return { percent: 75, label: 'Good', className: 'good' };
    }
    return { percent: 100, label: 'Strong', className: 'strong' };
  }, [newPassword, passwordChecks]);

  useEffect(() => {
    const warnBeforeLeave = (event) => {
      if (!isEditingProfile || !profileChanged) return;
      event.preventDefault();
      event.returnValue = '';
    };

    window.addEventListener('beforeunload', warnBeforeLeave);
    return () => window.removeEventListener('beforeunload', warnBeforeLeave);
  }, [isEditingProfile, profileChanged]);

  const getJoinedDate = (value) => {
    if (!value || value === 'Not available') return 'Not available';

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;

    return parsed.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const validateProfile = () => {
    if (!fullName.trim()) return 'Name is required.';
    if (fullName.trim().length < 3) return 'Name must be at least 3 characters.';
    if (!email.trim()) return 'Email is required.';

    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailPattern.test(email.trim())) {
      return 'Please enter a valid email address.';
    }

    return '';
  };

  const validatePassword = () => {
    if (!currentPassword.trim()) return 'Current password is required.';
    if (!newPassword.trim()) return 'New password is required.';
    if (newPassword.length < 8) {
      return 'New password must be at least 8 characters.';
    }
    if (!/[A-Z]/.test(newPassword)) {
      return 'New password must include at least one uppercase letter.';
    }
    if (!/\d/.test(newPassword)) {
      return 'New password must include at least one number.';
    }
    if (newPassword === currentPassword) {
      return 'New password must be different from current password.';
    }
    if (!confirmPassword.trim()) {
      return 'Please confirm your new password.';
    }
    if (newPassword !== confirmPassword) {
      return 'New password and confirm password do not match.';
    }

    return '';
  };

  const handleRefreshProfile = async () => {
    setSaveMessage('');
    setSaveError('');

    if (!user?.id) {
      setSaveError('User information is missing.');
      return;
    }

    if (
      isEditingProfile &&
      profileChanged &&
      !window.confirm('Discard your unsaved profile changes and refresh?')
    ) {
      return;
    }

    setIsLoadingProfile(true);

    try {
      const refreshedUser = await refreshUser(user.id);
      setFullName(refreshedUser?.full_name || refreshedUser?.name || '');
      setEmail(refreshedUser?.email || '');
      setIsEditingProfile(false);
      setSaveMessage('Profile refreshed successfully.');
    } catch (error) {
      setSaveError(error.message || 'Unable to refresh profile.');
    } finally {
      setIsLoadingProfile(false);
    }
  };

  const handleStartEditProfile = () => {
    setSaveMessage('');
    setSaveError('');
    setIsEditingProfile(true);
  };

  const handleCancelEditProfile = () => {
    setFullName(initialName);
    setEmail(initialEmail);
    setSaveMessage('');
    setSaveError('');
    setIsEditingProfile(false);
  };

  const handleSaveProfile = async (event) => {
    event.preventDefault();
    setSaveMessage('');
    setSaveError('');

    const validationError = validateProfile();
    if (validationError) {
      setSaveError(validationError);
      return;
    }

    if (!user?.id) {
      setSaveError('User information is missing.');
      return;
    }

    setIsSavingProfile(true);

    try {
      const response = await api.put(`/profile/${user.id}`, {
        full_name: fullName.trim(),
        email: email.trim(),
      });

      const updatedUser = response.data.user;
      updateUser(updatedUser);
      setFullName(updatedUser.full_name || updatedUser.name || '');
      setEmail(updatedUser.email || '');
      setSaveMessage(response.data.message || 'Profile updated successfully.');
      setIsEditingProfile(false);
    } catch (error) {
      setSaveError(
        error.response?.data?.message || 'Unable to save profile.'
      );
    } finally {
      setIsSavingProfile(false);
    }
  };

  const handleStartEditPassword = () => {
    setPasswordMessage('');
    setPasswordError('');
    setIsEditingPassword(true);
  };

  const handleCancelEditPassword = () => {
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setShowCurrentPassword(false);
    setShowNewPassword(false);
    setShowConfirmPassword(false);
    setPasswordMessage('');
    setPasswordError('');
    setIsEditingPassword(false);
  };

  const handleSavePassword = async (event) => {
    event.preventDefault();
    setPasswordMessage('');
    setPasswordError('');

    const validationError = validatePassword();
    if (validationError) {
      setPasswordError(validationError);
      return;
    }

    if (!user?.id) {
      setPasswordError('User information is missing.');
      return;
    }

    setIsSavingPassword(true);

    try {
      const response = await api.put(
        `/profile/${user.id}/change-password`,
        {
          current_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }
      );

      handleCancelEditPassword();
      setPasswordMessage(
        response.data.message || 'Password updated successfully.'
      );
    } catch (error) {
      setPasswordError(
        error.response?.data?.message || 'Unable to update password.'
      );
    } finally {
      setIsSavingPassword(false);
    }
  };

  const passwordFields = [
    {
      key: 'current',
      label: 'Current Password',
      value: currentPassword,
      setter: setCurrentPassword,
      visible: showCurrentPassword,
      setVisible: setShowCurrentPassword,
      autoComplete: 'current-password',
      placeholder: 'Enter current password',
    },
    {
      key: 'new',
      label: 'New Password',
      value: newPassword,
      setter: setNewPassword,
      visible: showNewPassword,
      setVisible: setShowNewPassword,
      autoComplete: 'new-password',
      placeholder: 'Create a new password',
    },
    {
      key: 'confirm',
      label: 'Confirm New Password',
      value: confirmPassword,
      setter: setConfirmPassword,
      visible: showConfirmPassword,
      setVisible: setShowConfirmPassword,
      autoComplete: 'new-password',
      placeholder: 'Re-enter new password',
    },
  ];

  return (
    <div className="profile-page">
      <PageHeader
        title="My Account"
        subtitle="Manage your employee profile, account details, and sign-in security."
      />

      <section className="profile-overview-card">
        <div className="profile-identity-area">
          <div className="profile-avatar-modern" aria-hidden="true">
            {userInitial}
          </div>

          <div className="profile-identity-copy">
            <span className="profile-kicker">Employee profile</span>
            <h2>{displayName || 'User'}</h2>

            <div className="profile-email-line">
              <ProfileIcon name="mail" size={15} />
              <span>{displayEmail || 'No email available'}</span>
            </div>

            <div className="profile-badges">
              <span className="role-pill">{displayRole}</span>
              <span
                className={`status-badge ${String(
                  displayStatus
                ).toLowerCase()}`}
              >
                {displayStatus}
              </span>
            </div>
          </div>
        </div>

        <div className="profile-quick-actions">
          <button
            type="button"
            className="secondary-btn"
            onClick={handleRefreshProfile}
            disabled={isLoadingProfile}
          >
            <ProfileIcon name="refresh" />
            {isLoadingProfile ? 'Refreshing...' : 'Refresh'}
          </button>

          <button
            type="button"
            className="primary-btn"
            onClick={handleStartEditProfile}
            disabled={isEditingProfile}
          >
            <ProfileIcon name="edit" />
            Edit Profile
          </button>
        </div>

        <div className="profile-overview-divider" />

        <div className="profile-meta-strip">
          <div className="profile-meta-item">
            <span className="profile-meta-icon">
              <ProfileIcon name="user" />
            </span>
            <div>
              <small>User ID</small>
              <strong>{user?.id || '-'}</strong>
            </div>
          </div>

          <div className="profile-meta-item">
            <span className="profile-meta-icon">
              <ProfileIcon name="calendar" />
            </span>
            <div>
              <small>Joined</small>
              <strong>{getJoinedDate(displayCreatedAt)}</strong>
            </div>
          </div>

          <div className="profile-meta-item">
            <span className="profile-meta-icon">
              <ProfileIcon name="shield" />
            </span>
            <div>
              <small>Role</small>
              <strong className="capitalize-text">{displayRole}</strong>
            </div>
          </div>

          <div className="profile-meta-item">
            <span className="profile-meta-icon">
              <ProfileIcon name="shield" />
            </span>
            <div>
              <small>Account Status</small>
              <strong className="capitalize-text">{displayStatus}</strong>
            </div>
          </div>
        </div>
      </section>

      <div className="profile-workspace-grid">
        <section className="profile-panel">
          <div className="profile-panel-header">
            <span className="profile-panel-icon">
              <ProfileIcon name="user" />
            </span>
            <div>
              <h3>Personal Information</h3>
              <p>Keep your staff account details accurate and up to date.</p>
            </div>
          </div>

          <form onSubmit={handleSaveProfile} className="profile-form">
            <div className="profile-field">
              <label htmlFor="profile-full-name">Full Name</label>
              {isEditingProfile ? (
                <input
                  id="profile-full-name"
                  type="text"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  placeholder="Enter your full name"
                  autoComplete="name"
                />
              ) : (
                <div className="profile-field-value">
                  {displayName || '-'}
                </div>
              )}
            </div>

            <div className="profile-field">
              <label htmlFor="profile-email">Email Address</label>
              {isEditingProfile ? (
                <input
                  id="profile-email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="Enter your email"
                  autoComplete="email"
                />
              ) : (
                <div className="profile-field-value">
                  {displayEmail || '-'}
                </div>
              )}
            </div>

            <div className="profile-readonly-grid">
              <div className="profile-field">
                <label>Role</label>
                <div className="profile-field-value capitalize-text">
                  {displayRole}
                </div>
                <small>Assigned by system administrator.</small>
              </div>

              <div className="profile-field">
                <label>Status</label>
                <div className="profile-field-value capitalize-text">
                  {displayStatus}
                </div>
                <small>Controls access to company resources.</small>
              </div>
            </div>

            <div className="profile-completeness-card">
              <div className="profile-completeness-head">
                <span>Profile completeness</span>
                <strong>{profileCompleteness}%</strong>
              </div>
              <p>
                Complete details help staff and managers identify your
                account correctly.
              </p>
              <div
                className="profile-completeness-track"
                role="progressbar"
                aria-label="Profile completeness"
                aria-valuemin="0"
                aria-valuemax="100"
                aria-valuenow={profileCompleteness}
              >
                <span style={{ width: `${profileCompleteness}%` }} />
              </div>
            </div>

            <div className="profile-feedback" aria-live="polite">
              {saveMessage ? (
                <p className="profile-alert success">{saveMessage}</p>
              ) : null}
              {saveError ? (
                <p className="profile-alert error">{saveError}</p>
              ) : null}
            </div>

            <div className="profile-form-actions">
              {isEditingProfile ? (
                <>
                  <button
                    type="submit"
                    className="primary-btn"
                    disabled={isSavingProfile || !profileChanged}
                  >
                    {isSavingProfile ? 'Saving Changes...' : 'Save Changes'}
                  </button>

                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={handleCancelEditProfile}
                    disabled={isSavingProfile}
                  >
                    Cancel
                  </button>

                  {profileChanged ? (
                    <span className="profile-unsaved-indicator">
                      Unsaved changes
                    </span>
                  ) : null}
                </>
              ) : (
                <button
                  type="button"
                  className="secondary-btn"
                  onClick={handleStartEditProfile}
                >
                  <ProfileIcon name="edit" size={16} />
                  Update Personal Details
                </button>
              )}
            </div>
          </form>
        </section>

        <section className="profile-panel">
          <div className="profile-panel-header">
            <span className="profile-panel-icon security">
              <ProfileIcon name="lock" />
            </span>
            <div>
              <h3>Sign-in Security</h3>
              <p>
                Change your password with live quality checks before saving.
              </p>
            </div>
          </div>

          {!isEditingPassword ? (
            <>
              <div className="profile-security-summary">
                <span className="profile-security-shield">
                  <ProfileIcon name="shield" size={26} />
                </span>
                <div>
                  <span>Password protection</span>
                  <strong>Password configured</strong>
                  <p>
                    Your password can be securely updated through the account API.
                  </p>
                </div>
              </div>

              <div className="profile-security-note">
                <strong>Company account tip</strong>
                <p>
                  Use a unique password that you do not reuse for personal services.
                </p>
              </div>

              <div className="profile-feedback" aria-live="polite">
                {passwordMessage ? (
                  <p className="profile-alert success">{passwordMessage}</p>
                ) : null}
                {passwordError ? (
                  <p className="profile-alert error">{passwordError}</p>
                ) : null}
              </div>

              <button
                type="button"
                className="primary-btn profile-security-action"
                onClick={handleStartEditPassword}
              >
                <ProfileIcon name="lock" size={16} />
                Change Password
              </button>
            </>
          ) : (
            <form
              onSubmit={handleSavePassword}
              className="profile-password-form"
            >
              {passwordFields.map((field) => (
                <div className="profile-password-field" key={field.key}>
                  <label htmlFor={`${field.key}-password`}>
                    {field.label}
                  </label>

                  <div className="profile-password-input">
                    <input
                      id={`${field.key}-password`}
                      type={field.visible ? 'text' : 'password'}
                      value={field.value}
                      onChange={(event) => field.setter(event.target.value)}
                      placeholder={field.placeholder}
                      autoComplete={field.autoComplete}
                    />

                    <button
                      type="button"
                      className="profile-password-toggle"
                      onClick={() =>
                        field.setVisible((previous) => !previous)
                      }
                      aria-label={
                        field.visible
                          ? `Hide ${field.label.toLowerCase()}`
                          : `Show ${field.label.toLowerCase()}`
                      }
                    >
                      <ProfileIcon
                        name={field.visible ? 'eyeOff' : 'eye'}
                        size={17}
                      />
                    </button>
                  </div>

                  {field.key === 'confirm' && confirmPassword ? (
                    <span
                      className={
                        newPassword === confirmPassword
                          ? 'profile-password-match matched'
                          : 'profile-password-match'
                      }
                    >
                      {newPassword === confirmPassword
                        ? 'Passwords match'
                        : 'Passwords do not match yet'}
                    </span>
                  ) : null}
                </div>
              ))}

              <div className="profile-password-strength">
                <div className="profile-password-strength-head">
                  <span>Password strength</span>
                  <strong className={passwordStrength.className}>
                    {passwordStrength.label}
                  </strong>
                </div>

                <div className="profile-password-strength-track">
                  <span
                    className={passwordStrength.className}
                    style={{ width: `${passwordStrength.percent}%` }}
                  />
                </div>

                <div className="profile-password-checks">
                  <span className={passwordChecks.length ? 'passed' : ''}>
                    8+ characters
                  </span>
                  <span className={passwordChecks.uppercase ? 'passed' : ''}>
                    Uppercase
                  </span>
                  <span className={passwordChecks.lowercase ? 'passed' : ''}>
                    Lowercase
                  </span>
                  <span className={passwordChecks.number ? 'passed' : ''}>
                    Number
                  </span>
                </div>
              </div>

              <div className="profile-feedback" aria-live="polite">
                {passwordError ? (
                  <p className="profile-alert error">{passwordError}</p>
                ) : null}
              </div>

              <div className="profile-form-actions">
                <button
                  type="submit"
                  className="primary-btn"
                  disabled={isSavingPassword}
                >
                  {isSavingPassword
                    ? 'Updating Password...'
                    : 'Update Password'}
                </button>

                <button
                  type="button"
                  className="secondary-btn"
                  onClick={handleCancelEditPassword}
                  disabled={isSavingPassword}
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}
