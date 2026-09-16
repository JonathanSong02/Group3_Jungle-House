/* eslint-disable react-refresh/only-export-components */

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import api from '../services/api';

const AuthContext = createContext(null);

// The shared Axios instance is also used by pages outside AuthContext.
// Cookies, rather than a browser-stored user object, identify the session.
api.defaults.withCredentials = true;

function removeLegacyUserCache() {
  try {
    // Never read this value: old localStorage profiles are not authentication.
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem('jh_user');
    }
  } catch {
    // Private browsing/storage restrictions must not break authentication.
  }
}

function toAuthError(error, fallbackMessage) {
  const responseData = error?.response?.data || {};
  const networkError = Boolean(error?.request) && !error?.response;

  const message =
    responseData?.message ||
    (networkError
      ? 'Unable to reach the authentication server.'
      : error?.message || fallbackMessage);

  const authError = new Error(message);
  authError.code = responseData?.code || error?.code || null;
  authError.data = responseData;
  authError.status = error?.response?.status || error?.status || null;
  authError.networkError = networkError;
  authError.originalError = error;

  return authError;
}

function readActiveSession(data) {
  const sessionUser = data?.user;
  const csrfToken = data?.csrf_token;

  if (
    !sessionUser ||
    (sessionUser.id == null && sessionUser.user_id == null) ||
    String(sessionUser.status || '').toLowerCase() !== 'active' ||
    typeof csrfToken !== 'string' ||
    !csrfToken
  ) {
    throw new Error('The authentication server returned an invalid session.');
  }

  return { sessionUser, csrfToken };
}

function isPublicAuthRequest(url) {
  return /\/auth\/(?:login|register|forgot-password|reset-password)(?:\/|\?|$)/.test(
    String(url || '')
  );
}

export function AuthProvider({ children }) {
  // No localStorage hydration: the server must confirm every session.
  const [user, setUser] = useState(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [authError, setAuthError] = useState(null);
  const csrfTokenRef = useRef(null);
  const operationRef = useRef(0);
  const authenticatedRef = useRef(false);

  const clearAuth = useCallback(() => {
    csrfTokenRef.current = null;
    authenticatedRef.current = false;
    setUser(null);
    removeLegacyUserCache();
  }, []);

  const acceptSession = useCallback((data) => {
    const { sessionUser, csrfToken } = readActiveSession(data);
    csrfTokenRef.current = csrfToken;
    authenticatedRef.current = true;
    setUser(sessionUser);
    setAuthError(null);
    removeLegacyUserCache();
    return sessionUser;
  }, []);

  useEffect(() => {
    removeLegacyUserCache();

    // Install on the existing instance so User Management and other pages
    // automatically send the backend's session-bound CSRF token on writes.
    const requestInterceptor = api.interceptors.request.use((config) => {
      const method = String(config.method || 'get').toLowerCase();
      const csrfToken = csrfTokenRef.current;

      if (csrfToken && !['get', 'head', 'options'].includes(method)) {
        config.headers = config.headers || {};
        if (!config.headers['X-CSRF-Token']) {
          config.headers['X-CSRF-Token'] = csrfToken;
        }
      }

      return config;
    });

    const responseInterceptor = api.interceptors.response.use(
      (response) => response,
      (error) => {
        const url = String(error?.config?.url || '');
        const isSessionCheck = /\/auth\/me(?:\?|$)/.test(url);
        const isLogout = /\/auth\/logout(?:\?|$)/.test(url);

        // /auth/me is handled by its own caller to avoid an older restore
        // request clearing a newer successful login. Invalid credentials and
        // pending approvals must retain their backend status and error code.
        if (
          error?.response?.status === 401 &&
          !isSessionCheck &&
          !isLogout &&
          !isPublicAuthRequest(url)
        ) {
          const hadSession = authenticatedRef.current;
          operationRef.current += 1;
          clearAuth();
          setIsAuthLoading(false);
          if (hadSession) {
            setAuthError('Your session has expired. Please sign in again.');
          }
        }

        return Promise.reject(error);
      }
    );

    const operation = ++operationRef.current;
    api.get('/auth/me')
      .then((response) => {
        if (operation === operationRef.current) {
          acceptSession(response.data);
        }
      })
      .catch((error) => {
        if (operation !== operationRef.current) return;
        clearAuth();
        if (error?.response?.status !== 401) {
          setAuthError(toAuthError(error, 'Unable to restore your session.').message);
        }
      })
      .finally(() => {
        if (operation === operationRef.current) {
          setIsAuthLoading(false);
        }
      });

    return () => {
      operationRef.current += 1;
      api.interceptors.request.eject(requestInterceptor);
      api.interceptors.response.eject(responseInterceptor);
    };
  }, [acceptSession, clearAuth]);

  const login = async ({ email, password }) => {
    const operation = ++operationRef.current;
    clearAuth();
    setAuthError(null);
    setIsAuthLoading(true);

    try {
      const response = await api.post('/auth/login', { email, password });
      if (operation !== operationRef.current) {
        throw new Error('This login request was superseded. Please try again.');
      }
      return acceptSession(response.data);
    } catch (error) {
      const authErrorResult = toAuthError(error, 'Login failed.');
      if (operation === operationRef.current) {
        clearAuth();
        setAuthError(authErrorResult.message);
      }
      // Preserve ACCOUNT_PENDING_APPROVAL / ACCOUNT_INACTIVE for Login.jsx.
      throw authErrorResult;
    } finally {
      if (operation === operationRef.current) {
        setIsAuthLoading(false);
      }
    }
  };

  // Keep this existing function for Profile/Account pages. Only update
  // non-authoritative display fields of the SAME authenticated user; a
  // frontend object must never change its own role, status, or identity.
  const updateUser = (updatedUser) => {
    if (!updatedUser || typeof updatedUser !== 'object') return;
    setUser((current) => {
      if (!current) return null;
      const currentId = current.id ?? current.user_id;
      const updatedId = updatedUser.id ?? updatedUser.user_id;
      if (updatedId == null || String(updatedId) !== String(currentId)) {
        return current;
      }

      const fullName = updatedUser.full_name ?? updatedUser.name;
      return {
        ...current,
        ...(typeof fullName === 'string'
          ? { name: fullName, full_name: fullName }
          : {}),
        ...(typeof updatedUser.email === 'string'
          ? { email: updatedUser.email }
          : {}),
      };
    });
  };

  // Preserve refreshUser(userId) callers, but verify the cookie and obtain
  // the profile from /auth/me instead of trusting an unrestricted profile ID.
  const refreshUser = async (userId) => {
    const operation = ++operationRef.current;
    try {
      const response = await api.get('/auth/me');
      const { sessionUser } = readActiveSession(response.data);
      const actualId = sessionUser.id ?? sessionUser.user_id;

      if (userId != null && String(userId) !== String(actualId)) {
        throw new Error('The requested profile does not match your session.');
      }
      if (operation === operationRef.current) {
        return acceptSession(response.data);
      }
      throw new Error('The session changed during the profile refresh.');
    } catch (error) {
      if (operation === operationRef.current) {
        clearAuth();
        setAuthError('Your session could not be verified. Please sign in again.');
        setIsAuthLoading(false);
      }
      throw toAuthError(error, 'Unable to refresh user data.');
    } finally {
      if (operation === operationRef.current) {
        setIsAuthLoading(false);
      }
    }
  };

  const logout = async () => {
    const operation = ++operationRef.current;
    const csrfToken = csrfTokenRef.current;
    // Hide protected screens immediately; do not claim server logout until
    // Flask confirms it has cleared its signed session cookie.
    clearAuth();
    setAuthError(null);
    setIsAuthLoading(false);

    try {
      await api.post('/auth/logout', {}, {
        headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : {},
      });
      return true;
    } catch (error) {
      if (error?.response?.status === 401) return true;
      if (operation === operationRef.current) {
        setAuthError(
          'Server logout could not be confirmed. Your session may still be active; please try again.'
        );
      }
      return false;
    }
  };

  const value = {
    user,
    login,
    logout,
    updateUser,
    refreshUser,
    isAuthenticated: Boolean(user) && !isAuthLoading,
    isAuthLoading,
    authLoading: isAuthLoading,
    loading: isAuthLoading,
    authError,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider');
  }

  return context;
}
