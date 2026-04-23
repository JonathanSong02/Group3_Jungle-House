import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../components/PageHeader';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

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

  const userInitial = useMemo(() => {
    return (displayName || 'U').trim().charAt(0).toUpperCase();
  }, [displayName]);

  const profileChanged =
    fullName.trim() !== initialName.trim() || email.trim() !== initialEmail.trim();

  const getJoinedDate = (value) => {
    if (!value || value === 'Not available') return 'Not available';

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;

    return parsed.toLocaleString();
  };

  const validateProfile = () => {
    if (!fullName.trim()) {
      return 'Name is required.';
    }

    if (fullName.trim().length < 3) {
      return 'Name must be at least 3 characters.';
    }

    if (!email.trim()) {
      return 'Email is required.';
    }

    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailPattern.test(email.trim())) {
      return 'Please enter a valid email address.';
    }

    return '';
  };

  const validatePassword = () => {
    if (!currentPassword.trim()) {
      return 'Current password is required.';
    }

    if (!newPassword.trim()) {
      return 'New password is required.';
    }

    if (newPassword.length < 6) {
      return 'New password must be at least 6 characters.';
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

    setIsLoadingProfile(true);

    try {
      const refreshedUser = await refreshUser(user.id);
      setFullName(refreshedUser?.full_name || refreshedUser?.name || '');
      setEmail(refreshedUser?.email || '');
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
      setSaveError(error.response?.data?.message || 'Unable to save profile.');
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
      const response = await api.put(`/profile/${user.id}/change-password`, {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });

      handleCancelEditPassword();
      setPasswordMessage(response.data.message || 'Password updated successfully.');
    } catch (error) {
      setPasswordError(error.response?.data?.message || 'Unable to update password.');
    } finally {
      setIsSavingPassword(false);
    }
  };

  return (
    <div className="profile-v2-layout">
      <PageHeader
        title="Profile"
        subtitle="Manage your personal account details, email, and password."
      />

      <section className="card-like profile-v2-header">
        <div className="profile-v2-top">
          <div className="profile-avatar large">{userInitial}</div>

          <div className="profile-v2-main-info">
            <h2>{displayName || 'User'}</h2>
            <p className="muted">{displayEmail || 'No email available'}</p>

            <div className="profile-v2-badges">
              <span className="role-pill">{displayRole}</span>
              <span className={`status-badge ${String(displayStatus).toLowerCase()}`}>
                {displayStatus}
              </span>
            </div>
          </div>
        </div>

        <div className="profile-inline-actions">
          <button
            type="button"
            className="secondary-btn"
            onClick={handleRefreshProfile}
            disabled={isLoadingProfile}
          >
            {isLoadingProfile ? 'Refreshing...' : 'Refresh Profile'}
          </button>
        </div>

        <div className="profile-v2-meta-grid">
          <div className="profile-v2-meta-box">
            <span className="profile-detail-label">User ID</span>
            <strong>{user?.id || '-'}</strong>
          </div>

          <div className="profile-v2-meta-box">
            <span className="profile-detail-label">Joined</span>
            <strong>{getJoinedDate(displayCreatedAt)}</strong>
          </div>

          <div className="profile-v2-meta-box">
            <span className="profile-detail-label">Role</span>
            <strong style={{ textTransform: 'capitalize' }}>{displayRole}</strong>
          </div>

          <div className="profile-v2-meta-box">
            <span className="profile-detail-label">Account Status</span>
            <strong style={{ textTransform: 'capitalize' }}>{displayStatus}</strong>
          </div>
        </div>
      </section>

      <div className="two-column-grid profile-main-grid">
        <section className="card-like profile-v2-details-card">
          <div className="profile-section-title">
            <h3>Personal Information</h3>
            <p className="muted">
              Review and update your basic account details.
            </p>
          </div>

          <form onSubmit={handleSaveProfile}>
            <div className="profile-detail-row">
              <div className="profile-detail-content">
                <span className="profile-detail-label">Full Name</span>

                {isEditingProfile ? (
                  <div className="profile-inline-editor">
                    <input
                      type="text"
                      value={fullName}
                      onChange={(event) => setFullName(event.target.value)}
                      placeholder="Enter your full name"
                    />
                  </div>
                ) : (
                  <strong>{displayName || '-'}</strong>
                )}
              </div>
            </div>

            <div className="profile-detail-row">
              <div className="profile-detail-content">
                <span className="profile-detail-label">Email</span>

                {isEditingProfile ? (
                  <div className="profile-inline-editor">
                    <input
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="Enter your email"
                    />
                  </div>
                ) : (
                  <strong>{displayEmail || '-'}</strong>
                )}
              </div>
            </div>

            <div className="profile-detail-row readonly">
              <div className="profile-detail-content">
                <span className="profile-detail-label">Role</span>
                <strong style={{ textTransform: 'capitalize' }}>{displayRole}</strong>
              </div>
            </div>

            <div className="profile-detail-row readonly">
              <div className="profile-detail-content">
                <span className="profile-detail-label">Status</span>
                <strong style={{ textTransform: 'capitalize' }}>{displayStatus}</strong>
              </div>
            </div>

            {saveMessage ? (
              <p className="success-text top-gap-sm">{saveMessage}</p>
            ) : null}

            {saveError ? (
              <p className="error-text top-gap-sm">{saveError}</p>
            ) : null}

            <div className="profile-inline-actions top-gap">
              {isEditingProfile ? (
                <>
                  <button
                    type="submit"
                    className="primary-btn"
                    disabled={isSavingProfile || !profileChanged}
                  >
                    {isSavingProfile ? 'Saving...' : 'Save Changes'}
                  </button>

                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={handleCancelEditProfile}
                    disabled={isSavingProfile}
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="primary-btn"
                  onClick={handleStartEditProfile}
                >
                  Edit Profile
                </button>
              )}
            </div>
          </form>
        </section>

        <section className="card-like profile-v2-details-card">
          <div className="profile-section-title">
            <h3>Security</h3>
            <p className="muted">
              Manage your password and protect your account.
            </p>
          </div>

          {!isEditingPassword ? (
            <>
              <div className="profile-detail-row readonly">
                <div className="profile-detail-content">
                  <span className="profile-detail-label">Password</span>
                  <strong>••••••••</strong>
                  <span className="muted small">
                    Your password is now connected to backend update API.
                  </span>
                </div>
              </div>

              {passwordMessage ? (
                <p className="success-text top-gap-sm">{passwordMessage}</p>
              ) : null}

              {passwordError ? (
                <p className="error-text top-gap-sm">{passwordError}</p>
              ) : null}

              <div className="profile-inline-actions top-gap">
                <button
                  type="button"
                  className="primary-btn"
                  onClick={handleStartEditPassword}
                >
                  Change Password
                </button>
              </div>
            </>
          ) : (
            <form onSubmit={handleSavePassword} className="form-stack">
              <div className="profile-password-stack">
                <div>
                  <label className="profile-detail-label">Current Password</label>
                  <div className="password-input-group">
                    <input
                      type={showCurrentPassword ? 'text' : 'password'}
                      value={currentPassword}
                      onChange={(event) => setCurrentPassword(event.target.value)}
                      placeholder="Enter current password"
                    />
                    <button
                      type="button"
                      className="secondary-btn password-toggle-btn"
                      onClick={() => setShowCurrentPassword((prev) => !prev)}
                    >
                      {showCurrentPassword ? 'Hide' : 'Show'}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="profile-detail-label">New Password</label>
                  <div className="password-input-group">
                    <input
                      type={showNewPassword ? 'text' : 'password'}
                      value={newPassword}
                      onChange={(event) => setNewPassword(event.target.value)}
                      placeholder="Enter new password"
                    />
                    <button
                      type="button"
                      className="secondary-btn password-toggle-btn"
                      onClick={() => setShowNewPassword((prev) => !prev)}
                    >
                      {showNewPassword ? 'Hide' : 'Show'}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="profile-detail-label">Confirm Password</label>
                  <div className="password-input-group">
                    <input
                      type={showConfirmPassword ? 'text' : 'password'}
                      value={confirmPassword}
                      onChange={(event) => setConfirmPassword(event.target.value)}
                      placeholder="Confirm new password"
                    />
                    <button
                      type="button"
                      className="secondary-btn password-toggle-btn"
                      onClick={() => setShowConfirmPassword((prev) => !prev)}
                    >
                      {showConfirmPassword ? 'Hide' : 'Show'}
                    </button>
                  </div>
                </div>
              </div>

              <div className="password-hint-box">
                <span className="profile-detail-label">Password Tips</span>
                <p className="muted small" style={{ marginBottom: 0 }}>
                  Use at least 6 characters and avoid reusing your current password.
                </p>
              </div>

              {passwordMessage ? (
                <p className="success-text">{passwordMessage}</p>
              ) : null}

              {passwordError ? (
                <p className="error-text">{passwordError}</p>
              ) : null}

              <div className="profile-inline-actions">
                <button
                  type="submit"
                  className="primary-btn"
                  disabled={isSavingPassword}
                >
                  {isSavingPassword ? 'Updating...' : 'Update Password'}
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