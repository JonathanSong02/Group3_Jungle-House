/* eslint-disable react-refresh/only-export-components */

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import api from '../services/api';

const AuthContext = createContext(null);

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

function isSessionRejection(error) {
  // Accept both Axios responses and locally generated/normalised auth errors.
  // refreshUser can create a SESSION_EXPIRED error when /auth/me returns an
  // invalid user; overlooking its direct code/status would keep a stale user.
  const code = error?.response?.data?.code || error?.data?.code || error?.code;
  const status = error?.response?.status ?? error?.status;
  return (
    status === 401 ||
    code === 'SESSION_EXPIRED' ||
    code === 'AUTH_REQUIRED' ||
    code === 'ACCOUNT_INACTIVE'
  );
}

function isPublicAuthenticationRequest(error) {
  // A failed login (or password recovery) is not evidence that an existing
  // authenticated request has expired. Do not globally sign out on its 401.
  const path = String(error?.config?.url || '').split('?')[0].replace(/\/+$/, '');
  return [
    '/auth/csrf',
    '/auth/login',
    '/auth/register',
    '/auth/forgot-password',
    '/auth/reset-password',
    '/auth/reset-password/validate',
  ].some((route) => path === route || path.endsWith(`/api${route}`));
}

function isActiveSessionUser(candidate) {
  return Boolean(candidate && candidate.id != null && candidate.status === 'active');
}

export function AuthProvider({ children }) {
  // Flask's signed session cookie and /auth/me are the source of truth.
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const sessionGeneration = useRef(0);

  useEffect(() => {
    // Old versions saved a user in localStorage; never restore authorization
    // from that value. Cleanup does not need localStorage to be available.
    try {
      localStorage.removeItem('jh_user');
    } catch {
      // Private browsing or disabled storage must not break authentication.
    }

    let cancelled = false;
    const generation = ++sessionGeneration.current;

    api.get('/auth/me')
      .then((response) => {
        if (cancelled || generation !== sessionGeneration.current) return;
        const sessionUser = response.data?.user;
        setUser(isActiveSessionUser(sessionUser) ? sessionUser : null);
      })
      .catch(() => {
        // An unavailable server is not proof of logout; on initial loading
        // there is no verified identity to display, so remain signed out.
        if (cancelled || generation !== sessionGeneration.current) return;
        setUser(null);
      })
      .finally(() => {
        if (!cancelled && generation === sessionGeneration.current) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    // Associate each request with the login/logout generation that started it.
    // An old failed request must not sign out a newer authenticated session.
    const requestInterceptorId = api.interceptors.request.use((config) => {
      config._jhAuthGeneration = sessionGeneration.current;
      return config;
    });

    const responseInterceptorId = api.interceptors.response.use(
      (response) => response,
      (error) => {
        const requestGeneration = error?.config?._jhAuthGeneration;
        const isCurrentRequest =
          requestGeneration == null || requestGeneration === sessionGeneration.current;

        if (
          isCurrentRequest &&
          !isPublicAuthenticationRequest(error) &&
          isSessionRejection(error)
        ) {
          ++sessionGeneration.current;
          setUser(null);
          setIsLoading(false);
        }
        // A 403 FORBIDDEN means insufficient permissions, not logout. A 503
        // AUTH_UNAVAILABLE is a temporary server failure, not an expired cookie.
        return Promise.reject(error);
      }
    );

    return () => {
      api.interceptors.request.eject(requestInterceptorId);
      api.interceptors.response.eject(responseInterceptorId);
    };
  }, []);

  const login = useCallback(async ({ email, password }) => {
    const generation = ++sessionGeneration.current;
    setUser(null);
    setIsLoading(true);

    try {
      const response = await api.post('/auth/login', { email, password });
      if (!isActiveSessionUser(response.data?.user)) {
        throw new Error('Invalid login response. Please sign in again.');
      }

      // Confirm that the browser retained the HttpOnly cookie. A successful
      // credential check alone cannot authenticate subsequent API requests.
      let sessionResponse;
      try {
        sessionResponse = await api.get('/auth/me');
      } catch (error) {
        if (error?.response?.status === 401) {
          const sessionError = new Error(
            'Login was accepted, but your browser did not retain the session. For local testing, use the same hostname (127.0.0.1) for Vite and Flask and check the cookie settings.'
          );
          sessionError.code = 'SESSION_NOT_PERSISTED';
          sessionError.status = 401;
          throw sessionError;
        }
        throw error;
      }

      const loggedInUser = sessionResponse.data?.user;
      if (!isActiveSessionUser(loggedInUser)) {
        throw new Error('Your account session could not be verified. Please sign in again.');
      }
      if (String(loggedInUser.id) !== String(response.data.user.id)) {
        throw new Error('The account session changed during sign-in. Please sign in again.');
      }

      if (generation !== sessionGeneration.current) {
        const superseded = new Error('Sign-in was interrupted by another authentication action. Please try again.');
        superseded.code = 'AUTH_OPERATION_SUPERSEDED';
        throw superseded;
      }
      setUser(loggedInUser);
      return loggedInUser;
    } catch (error) {
      if (generation === sessionGeneration.current) setUser(null);
      throw toAuthError(error, 'Login failed.');
    } finally {
      if (generation === sessionGeneration.current) setIsLoading(false);
    }
  }, []);

  const refreshUser = useCallback(async (userId) => {
    const generation = sessionGeneration.current;
    try {
      // Keep the optional userId parameter for existing profile pages, but
      // obtain identity and permissions only from the server-verified session.
      const response = await api.get('/auth/me');
      const refreshedUser = response.data?.user;
      if (!isActiveSessionUser(refreshedUser)) {
        const sessionError = new Error('Your session is no longer active. Please sign in again.');
        sessionError.code = 'SESSION_EXPIRED';
        sessionError.status = 401;
        throw sessionError;
      }
      if (userId != null && String(userId) !== String(refreshedUser.id)) {
        throw new Error('The requested profile does not match your signed-in account.');
      }
      if (generation !== sessionGeneration.current) {
        const superseded = new Error('Your session changed while refreshing your profile. Please try again.');
        superseded.code = 'AUTH_OPERATION_SUPERSEDED';
        throw superseded;
      }
      setUser(refreshedUser);
      return refreshedUser;
    } catch (error) {
      if (generation === sessionGeneration.current && isSessionRejection(error)) {
        ++sessionGeneration.current;
        setUser(null);
      }
      throw toAuthError(error, 'Unable to refresh user data.');
    }
  }, []);

  const updateUser = useCallback((updatedUser) => {
    // Preserve the synchronous profile-update interface used by other pages.
    // Client-supplied changes can update display fields only: never ID/role/status.
    setUser((current) => {
      if (!current || !updatedUser || String(current.id) !== String(updatedUser.id)) {
        return current;
      }
      const fullName = updatedUser.full_name ?? updatedUser.name ?? current.full_name;
      return {
        ...current,
        full_name: fullName,
        name: fullName,
        email: updatedUser.email ?? current.email,
      };
    });
  }, []);

  const logout = useCallback(async () => {
    const generation = ++sessionGeneration.current;
    setIsLoading(true);
    try {
      // Only the server can clear the signed session; never claim successful
      // logout merely because React cleared its user state.
      await api.post('/auth/logout');
      if (generation === sessionGeneration.current) setUser(null);
    } catch (error) {
      if (isSessionRejection(error)) {
        // The backend reports that there is no longer a valid session.
        if (generation === sessionGeneration.current) setUser(null);
      } else {
        // Preserve the existing UI identity on a network/CSRF/server error;
        // allow the caller to display the error and retry server-side logout.
        throw toAuthError(error, 'Unable to log out. Please try again.');
      }
    } finally {
      if (generation === sessionGeneration.current) setIsLoading(false);
    }
  }, []);

  const value = {
    user,
    login,
    logout,
    updateUser,
    refreshUser,
    isLoading,
    loading: isLoading,
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
