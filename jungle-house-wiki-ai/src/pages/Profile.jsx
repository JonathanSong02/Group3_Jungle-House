import { useEffect, useMemo, useRef, useState } from 'react';
import AvatarPicture from '../components/AvatarPicture';
import PageHeader from '../components/PageHeader';
import PushSetupPanel from '../components/PushSetupPanel';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { useLanguage } from '../i18n/LanguageContext';

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
    camera: (
      <>
        <path d="M4 7h4l2-3h4l2 3h4a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z" />
        <circle cx="12" cy="13" r="3.5" />
      </>
    ),
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
  const { t, tOr, locale, language } = useLanguage();
  const photoText = ({
    en: {
      change: 'Change profile picture',
      saving: 'Saving photo…', saved: 'Profile picture updated.', removed: 'Profile picture removed.',
      invalid: 'Choose a JPEG, PNG or WebP image up to 5 MB.', failed: 'Unable to save your photo. Please try again.',
      hint: 'JPEG, PNG or WebP · max 5 MB',
      title: 'Profile picture', description: 'Choose a photo and preview it before saving.',
      choose: 'Choose photo', another: 'Choose another', save: 'Save picture', cancel: 'Cancel', close: 'Close',
      current: 'Current profile picture', preview: 'New picture preview', defaultAvatar: 'Default avatar',
      crop: 'Your photo will be centre-cropped to a square.',
      removeTitle: 'Remove profile picture?', removeDescription: 'Your current photo will be deleted and replaced with your initial. You can upload a new picture anytime.',
      removeConfirm: 'Remove picture', useDefault: 'Use default avatar',
    },
    zh: {
      change: '更换头像',
      saving: '正在保存头像…', saved: '头像已更新。', removed: '头像已移除。',
      invalid: '请选择不超过 5 MB 的 JPEG、PNG 或 WebP 图片。', failed: '无法保存头像，请重试。',
      hint: 'JPEG、PNG 或 WebP · 最大 5 MB',
      title: '个人头像', description: '选择图片，并在保存前预览效果。',
      choose: '选择图片', another: '重新选择', save: '保存头像', cancel: '取消', close: '关闭',
      current: '当前头像', preview: '新头像预览', defaultAvatar: '默认头像',
      crop: '图片将从中心裁剪为正方形。',
      removeTitle: '移除个人头像？', removeDescription: '当前照片将被删除，并恢复为姓名首字母头像。您可以随时上传新照片。',
      removeConfirm: '确认移除', useDefault: '恢复默认头像',
    },
    ms: {
      change: 'Tukar gambar profil',
      saving: 'Menyimpan gambar…', saved: 'Gambar profil dikemas kini.', removed: 'Gambar profil dibuang.',
      invalid: 'Pilih imej JPEG, PNG atau WebP sehingga 5 MB.', failed: 'Gagal menyimpan gambar. Sila cuba lagi.',
      hint: 'JPEG, PNG atau WebP · maksimum 5 MB',
      title: 'Gambar profil', description: 'Pilih gambar dan lihat pratonton sebelum menyimpan.',
      choose: 'Pilih gambar', another: 'Pilih gambar lain', save: 'Simpan gambar', cancel: 'Batal', close: 'Tutup',
      current: 'Gambar profil semasa', preview: 'Pratonton gambar baharu', defaultAvatar: 'Avatar lalai',
      crop: 'Gambar akan dipangkas dari tengah menjadi segi empat sama.',
      removeTitle: 'Buang gambar profil?', removeDescription: 'Gambar semasa akan dipadam dan digantikan dengan huruf awal nama anda. Anda boleh memuat naik gambar baharu pada bila-bila masa.',
      removeConfirm: 'Buang gambar', useDefault: 'Guna avatar lalai',
    },
  })[language || 'en'];
  const photoInput = useRef(null);
  const photoBusy = useRef(false);
  const photoDialog = useRef(null);
  const [photoMode, setPhotoMode] = useState(null);
  const [photoDraft, setPhotoDraft] = useState(null);
  const [photoReady, setPhotoReady] = useState(false);
  const photoOpen = photoMode !== null;
  const [photoSaving, setPhotoSaving] = useState(false);
  const [photoNotice, setPhotoNotice] = useState(null);

  const savePhoto = async (file, remove = false) => {
    if (!user?.id || photoBusy.current) return false;
    setPhotoNotice(null);
    if (!remove && (!file || file.size > 5 * 1024 * 1024 ||
      (file.type && !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)))) {
      setPhotoNotice({ error: true, text: photoText.invalid });
      return false;
    }
    photoBusy.current = true;
    setPhotoSaving(true);
    try {
      const path = `/profile/${user.id}/avatar`;
      let response;
      if (remove) {
        response = await api.delete(path);
      } else {
        const form = new FormData();
        form.append('avatar', file);
        response = await api.put(path, form);
      }
      const updated = response.data?.user;
      if (!updated || String(updated.id) !== String(user.id) ||
          !Object.prototype.hasOwnProperty.call(updated, 'profile_picture')) {
        throw new Error('Invalid avatar response');
      }
      updateUser(updated);
      setPhotoNotice({ error: false, text: remove ? photoText.removed : photoText.saved });
      return true;
    } catch (error) {
      setPhotoNotice({
        error: true,
        text: error.response?.data?.code === 'AVATAR_INVALID' ? photoText.invalid : photoText.failed,
      });
      return false;
    } finally {
      photoBusy.current = false;
      setPhotoSaving(false);
    }
  };

  // Native modal enters the browser top layer, above the fixed staff navigation.
  useEffect(() => {
    const dialog = photoDialog.current;
    if (!photoOpen || !dialog) return undefined;
    if (!dialog.open) dialog.showModal();
    return () => { if (dialog.open) dialog.close(); };
  }, [photoOpen]);

  const draftUrl = photoDraft?.url;
  useEffect(() => {
    return () => { if (draftUrl) URL.revokeObjectURL(draftUrl); };
  }, [draftUrl]);

  const openPhotoDialog = (mode = 'change') => {
    if (photoBusy.current) return;
    setPhotoDraft(null);
    setPhotoReady(false);
    setPhotoNotice(null);
    setPhotoMode(mode);
  };

  const closePhotoDialog = () => {
    if (photoBusy.current) return;
    setPhotoMode(null);
    setPhotoDraft(null);
    setPhotoReady(false);
    setPhotoNotice(null);
  };

  const choosePhoto = (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || photoBusy.current) return;
    setPhotoReady(false);
    setPhotoNotice(null);
    if (!file.size || file.size > 5 * 1024 * 1024 ||
        (file.type && !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))) {
      setPhotoDraft(null);
      setPhotoNotice({ error: true, text: photoText.invalid });
      return;
    }
    setPhotoDraft({ file, url: URL.createObjectURL(file) });
  };

  const confirmPhotoChange = async () => {
    const removing = photoMode === 'remove';
    if (photoBusy.current || (removing ? !user?.profile_picture : !photoDraft || !photoReady)) return;
    const success = await savePhoto(removing ? null : photoDraft.file, removing);
    if (success) {
      setPhotoMode(null);
      setPhotoDraft(null);
      setPhotoReady(false);
    }
  };


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
  const displayCreatedAt = user?.created_at || '';

  const roleKey = String(displayRole).toLowerCase().replace(/[\s_-]/g, '');
  const roleLabel = tOr(`role.${roleKey}`, displayRole);
  const statusLabel = tOr(`status.${String(displayStatus).toLowerCase()}`, displayStatus);

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
      return { percent: 0, label: t('profile.pw.notEntered'), className: 'empty' };
    }
    if (passed <= 1) {
      return { percent: 25, label: t('profile.pw.weak'), className: 'weak' };
    }
    if (passed === 2) {
      return { percent: 50, label: t('profile.pw.fair'), className: 'fair' };
    }
    if (passed === 3) {
      return { percent: 75, label: t('profile.pw.good'), className: 'good' };
    }
    return { percent: 100, label: t('profile.pw.strong'), className: 'strong' };
  }, [newPassword, passwordChecks, t]);

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
    if (!value) return t('profile.notAvailable');

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;

    return parsed.toLocaleDateString(locale, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const validateProfile = () => {
    if (!fullName.trim()) return t('profile.v.nameReq');
    if (fullName.trim().length < 3) return t('profile.v.nameShort');
    if (!email.trim()) return t('profile.v.emailReq');

    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailPattern.test(email.trim())) {
      return t('profile.v.emailBad');
    }

    return '';
  };

  const validatePassword = () => {
    if (!currentPassword.trim()) return t('profile.v.curReq');
    if (!newPassword.trim()) return t('profile.v.newReq');
    if (newPassword.length < 8) {
      return t('profile.v.newLen');
    }
    if (!/[A-Z]/.test(newPassword)) {
      return t('profile.v.newUpper');
    }
    if (!/\d/.test(newPassword)) {
      return t('profile.v.newNum');
    }
    if (newPassword === currentPassword) {
      return t('profile.v.newSame');
    }
    if (!confirmPassword.trim()) {
      return t('profile.v.confirmReq');
    }
    if (newPassword !== confirmPassword) {
      return t('profile.v.mismatch');
    }

    return '';
  };

  const handleRefreshProfile = async () => {
    setSaveMessage('');
    setSaveError('');

    if (!user?.id) {
      setSaveError(t('profile.err.missingUser'));
      return;
    }

    if (
      isEditingProfile &&
      profileChanged &&
      !window.confirm(t('profile.confirm.discard'))
    ) {
      return;
    }

    setIsLoadingProfile(true);

    try {
      const refreshedUser = await refreshUser(user.id);
      setFullName(refreshedUser?.full_name || refreshedUser?.name || '');
      setEmail(refreshedUser?.email || '');
      setIsEditingProfile(false);
      setSaveMessage(t('profile.ok.refreshed'));
    } catch (error) {
      setSaveError(error.message || t('profile.err.refresh'));
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
      setSaveError(t('profile.err.missingUser'));
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
      setSaveMessage(t('profile.ok.updated'));
      setIsEditingProfile(false);
    } catch (error) {
      setSaveError(
        error.response?.data?.message || t('profile.err.save')
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
      setPasswordError(t('profile.err.missingUser'));
      return;
    }

    setIsSavingPassword(true);

    try {
      await api.put(
        `/profile/${user.id}/change-password`,
        {
          current_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }
      );

      handleCancelEditPassword();
      setPasswordMessage(
        t('profile.ok.pwUpdated')
      );
    } catch (error) {
      setPasswordError(
        error.response?.data?.message || t('profile.err.pw')
      );
    } finally {
      setIsSavingPassword(false);
    }
  };

  const passwordFields = [
    {
      key: 'current',
      label: t('profile.pw.current'),
      value: currentPassword,
      setter: setCurrentPassword,
      visible: showCurrentPassword,
      setVisible: setShowCurrentPassword,
      autoComplete: 'current-password',
      placeholder: t('profile.pw.enterCurrent'),
    },
    {
      key: 'new',
      label: t('profile.pw.new'),
      value: newPassword,
      setter: setNewPassword,
      visible: showNewPassword,
      setVisible: setShowNewPassword,
      autoComplete: 'new-password',
      placeholder: t('profile.pw.createNew'),
    },
    {
      key: 'confirm',
      label: t('profile.pw.confirm'),
      value: confirmPassword,
      setter: setConfirmPassword,
      visible: showConfirmPassword,
      setVisible: setShowConfirmPassword,
      autoComplete: 'new-password',
      placeholder: t('profile.pw.reenter'),
    },
  ];

  return (
    <div className="profile-page">
      <PageHeader
        title={t('profile.title')}
        subtitle={t('profile.subtitle')}
      />

      <dialog ref={photoDialog} className="profile-photo-dialog"
        aria-labelledby="profile-photo-title" aria-describedby="profile-photo-description"
        onCancel={(event) => { event.preventDefault(); closePhotoDialog(); }}>
        <div className="profile-photo-dialog-inner">
          <header className="profile-photo-header">
            <div>
              <h2 id="profile-photo-title">{photoMode === 'remove' ? photoText.removeTitle : photoText.title}</h2>
              <p id="profile-photo-description">{photoMode === 'remove' ? photoText.removeDescription : photoText.description}</p>
            </div>
            <button type="button" className="profile-photo-close" aria-label={photoText.close}
              disabled={photoSaving} onClick={closePhotoDialog}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>
            </button>
          </header>
          <div className="profile-photo-stage">
            <div className="profile-photo-preview">
              {photoMode === 'remove' ? userInitial : photoDraft ? (
                <img key={photoDraft.url} src={photoDraft.url} alt={photoText.preview}
                  onLoad={(event) => {
                    const { naturalWidth, naturalHeight } = event.currentTarget;
                    if (!naturalWidth || !naturalHeight || naturalWidth * naturalHeight > 20000000) {
                      setPhotoDraft(null);
                      setPhotoReady(false);
                      setPhotoNotice({ error: true, text: photoText.invalid });
                    } else setPhotoReady(true);
                  }}
                  onError={() => {
                    setPhotoDraft(null);
                    setPhotoReady(false);
                    setPhotoNotice({ error: true, text: photoText.invalid });
                  }}/>
              ) : <AvatarPicture src={user?.profile_picture} fallback={userInitial}/>}
            </div>
            <strong>{photoMode === 'remove' || (!photoDraft && !user?.profile_picture)
              ? photoText.defaultAvatar : photoDraft ? photoText.preview : photoText.current}</strong>
            {photoMode !== 'remove' && (
              <>
                {photoDraft && <p>{photoText.crop}</p>}
                <p>{photoText.hint}</p>
              </>
            )}
          </div>
          {photoMode !== 'remove' && (
            <div className="profile-photo-selection">
              <input ref={photoInput} type="file" accept="image/jpeg,image/png,image/webp"
                hidden onChange={choosePhoto}/>
              <button type="button" className="profile-photo-button is-secondary" disabled={photoSaving}
                onClick={() => photoInput.current?.click()}>
                <ProfileIcon name="camera" size={17}/>{photoDraft ? photoText.another : photoText.choose}
              </button>
              {user?.profile_picture && <button type="button" className="profile-photo-default"
                disabled={photoSaving} onClick={() => openPhotoDialog('remove')}>{photoText.useDefault}</button>}
            </div>
          )}
          {photoNotice?.error && <p className="profile-photo-error" role="alert">{photoNotice.text}</p>}
          <footer className="profile-photo-footer">
            <button type="button" className="profile-photo-button is-secondary" disabled={photoSaving}
              onClick={closePhotoDialog}>{photoText.cancel}</button>
            <button type="button" className={`profile-photo-button ${photoMode === 'remove' ? 'is-danger' : 'is-primary'}`}
              disabled={photoSaving || (photoMode === 'remove' ? !user?.profile_picture : !photoReady || !photoDraft)}
              onClick={() => void confirmPhotoChange()}>
              {photoSaving ? photoText.saving : photoMode === 'remove' ? photoText.removeConfirm : photoText.save}
            </button>
          </footer>
          {photoSaving && <span className="profile-photo-sr-only" role="status">{photoText.saving}</span>}
        </div>
      </dialog>

      <section className="profile-overview-card">
        <div className="profile-identity-area">
          <div className="profile-picture-wrap">
            <div className="profile-avatar-modern" aria-hidden="true">
              <AvatarPicture src={user?.profile_picture} fallback={userInitial} />
            </div>
            <button type="button" className="profile-picture-camera"
              title={photoText.change} aria-label={photoText.change}
              disabled={photoSaving || isEditingProfile || isLoadingProfile || !user?.id}
              onClick={() => openPhotoDialog('change')}>
              <ProfileIcon name="camera" size={16}/>
            </button>
          </div>

          <div className="profile-identity-copy">
            <span className="profile-kicker">{t('profile.kicker')}</span>
            <h2>{displayName || t('profile.user')}</h2>

            <div className="profile-email-line">
              <ProfileIcon name="mail" size={15} />
              <span>{displayEmail || t('profile.noEmail')}</span>
            </div>

            <div className="profile-badges">
              <span className="role-pill">{roleLabel}</span>
              <span
                className={`status-badge ${String(
                  displayStatus
                ).toLowerCase()}`}
              >
                {statusLabel}
              </span>
            </div>
            {!photoOpen && photoNotice && <p className={`profile-picture-notice ${photoNotice.error ? 'is-error' : ''}`}
              role={photoNotice.error ? 'alert' : 'status'}>{photoNotice.text}</p>}
          </div>
        </div>

        <div className="profile-quick-actions">
          <button
            type="button"
            className="secondary-btn"
            onClick={handleRefreshProfile}
            disabled={isLoadingProfile || photoSaving}
          >
            <ProfileIcon name="refresh" />
            {isLoadingProfile ? t('profile.refreshing') : t('profile.refresh')}
          </button>

          <button
            type="button"
            className="primary-btn"
            onClick={handleStartEditProfile}
            disabled={isEditingProfile || photoSaving}
          >
            <ProfileIcon name="edit" />
            {t('profile.editProfile')}
          </button>
        </div>

        <div className="profile-overview-divider" />

        <div className="profile-meta-strip">
          <div className="profile-meta-item">
            <span className="profile-meta-icon">
              <ProfileIcon name="user" />
            </span>
            <div>
              <small>{t('profile.userId')}</small>
              <strong>{user?.id || '-'}</strong>
            </div>
          </div>

          <div className="profile-meta-item">
            <span className="profile-meta-icon">
              <ProfileIcon name="calendar" />
            </span>
            <div>
              <small>{t('profile.joined')}</small>
              <strong>{getJoinedDate(displayCreatedAt)}</strong>
            </div>
          </div>

          <div className="profile-meta-item">
            <span className="profile-meta-icon">
              <ProfileIcon name="shield" />
            </span>
            <div>
              <small>{t('profile.role')}</small>
              <strong className="capitalize-text">{roleLabel}</strong>
            </div>
          </div>

          <div className="profile-meta-item">
            <span className="profile-meta-icon">
              <ProfileIcon name="shield" />
            </span>
            <div>
              <small>{t('profile.accountStatus')}</small>
              <strong className="capitalize-text">{statusLabel}</strong>
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
              <h3>{t('profile.personalInfo')}</h3>
              <p>{t('profile.personalInfoHint')}</p>
            </div>
          </div>

          <form onSubmit={handleSaveProfile} className="profile-form">
            <div className="profile-field">
              <label htmlFor="profile-full-name">{t('profile.fullName')}</label>
              {isEditingProfile ? (
                <input
                  id="profile-full-name"
                  type="text"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  placeholder={t('profile.enterName')}
                  autoComplete="name"
                />
              ) : (
                <div className="profile-field-value">
                  {displayName || '-'}
                </div>
              )}
            </div>

            <div className="profile-field">
              <label htmlFor="profile-email">{t('profile.email')}</label>
              {isEditingProfile ? (
                <input
                  id="profile-email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder={t('profile.enterEmail')}
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
                <label>{t('profile.role')}</label>
                <div className="profile-field-value capitalize-text">
                  {roleLabel}
                </div>
                <small>{t('profile.roleHint')}</small>
              </div>

              <div className="profile-field">
                <label>{t('profile.status')}</label>
                <div className="profile-field-value capitalize-text">
                  {statusLabel}
                </div>
                <small>{t('profile.statusHint')}</small>
              </div>
            </div>

            <div className="profile-completeness-card">
              <div className="profile-completeness-head">
                <span>{t('profile.completeness')}</span>
                <strong>{profileCompleteness}%</strong>
              </div>
              <p>{t('profile.completenessHint')}</p>
              <div
                className="profile-completeness-track"
                role="progressbar"
                aria-label={t('profile.completeness')}
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
                    {isSavingProfile ? t('profile.savingChanges') : t('profile.saveChanges')}
                  </button>

                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={handleCancelEditProfile}
                    disabled={isSavingProfile}
                  >
                    {t('common.cancel')}
                  </button>

                  {profileChanged ? (
                    <span className="profile-unsaved-indicator">
                      {t('profile.unsaved')}
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
                  {t('profile.updateDetails')}
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
              <h3>{t('profile.security')}</h3>
              <p>{t('profile.securityHint')}</p>
            </div>
          </div>

          {!isEditingPassword ? (
            <>
              <div className="profile-security-summary">
                <span className="profile-security-shield">
                  <ProfileIcon name="shield" size={26} />
                </span>
                <div>
                  <span>{t('profile.pwProtection')}</span>
                  <strong>{t('profile.pwConfigured')}</strong>
                  <p>{t('profile.pwConfiguredHint')}</p>
                </div>
              </div>

              <div className="profile-security-note">
                <strong>{t('profile.tip')}</strong>
                <p>{t('profile.tipHint')}</p>
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
                {t('profile.changePassword')}
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
                          ? t('profile.pw.hide', { label: field.label })
                          : t('profile.pw.show', { label: field.label })
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
                        ? t('profile.pw.match')
                        : t('profile.pw.noMatch')}
                    </span>
                  ) : null}
                </div>
              ))}

              <div className="profile-password-strength">
                <div className="profile-password-strength-head">
                  <span>{t('profile.pw.strength')}</span>
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
                    {t('profile.pw.chars')}
                  </span>
                  <span className={passwordChecks.uppercase ? 'passed' : ''}>
                    {t('profile.pw.upper')}
                  </span>
                  <span className={passwordChecks.lowercase ? 'passed' : ''}>
                    {t('profile.pw.lower')}
                  </span>
                  <span className={passwordChecks.number ? 'passed' : ''}>
                    {t('profile.pw.number')}
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
                    ? t('profile.pw.updating')
                    : t('profile.pw.update')}
                </button>

                <button
                  type="button"
                  className="secondary-btn"
                  onClick={handleCancelEditPassword}
                  disabled={isSavingPassword}
                >
                  {t('common.cancel')}
                </button>
              </div>
            </form>
          )}
        </section>

        {/* AI-ready phone / browser notifications (2026-11-26) */}
        <section className="profile-panel">
          <div className="profile-panel-header">
            <span className="profile-panel-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"
                strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M18 9a6 6 0 0 0-12 0c0 6-3 8-3 8h18s-3-2-3-8M10 21h4" />
              </svg>
            </span>
            <div>
              <h3>{t('push.title')}</h3>
              <p>{t('push.hint')}</p>
            </div>
          </div>
          <PushSetupPanel t={t} />
        </section>
      </div>
    </div>
  );
}
