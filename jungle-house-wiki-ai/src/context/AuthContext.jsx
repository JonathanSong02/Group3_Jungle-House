/* eslint-disable react-refresh/only-export-components */

import { createContext, useContext, useState } from 'react';
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
  authError.status = error?.response?.status || null;
  authError.networkError = networkError;
  authError.originalError = error;

  return authError;
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const saved = localStorage.getItem('jh_user');
      return saved ? JSON.parse(saved) : null;
    } catch (error) {
      console.error('Failed to load saved user:', error);
      localStorage.removeItem('jh_user');
      return null;
    }
  });

  const saveUserToStorage = (userData) => {
    setUser(userData);

    if (userData) {
      localStorage.setItem('jh_user', JSON.stringify(userData));
    } else {
      localStorage.removeItem('jh_user');
    }
  };

  const login = async ({ email, password }) => {
    try {
      const response = await api.post('/auth/login', {
        email,
        password,
      });

      const loggedInUser = response.data?.user;

      if (!loggedInUser) {
        throw new Error('Invalid login response.');
      }

      saveUserToStorage(loggedInUser);
      return loggedInUser;
    } catch (error) {
      // Keep the backend status/code/payload. Login.jsx needs these values to
      // distinguish pending approval from "registration key required".
      throw toAuthError(error, 'Login failed.');
    }
  };

  const updateUser = (updatedUser) => {
    saveUserToStorage(updatedUser);
  };

  const refreshUser = async (userId) => {
    if (!userId) {
      throw new Error('User ID is required.');
    }

    try {
      const response = await api.get(`/profile/${userId}`);
      const refreshedUser = response.data;

      if (!refreshedUser) {
        throw new Error('Unable to retrieve user data.');
      }

      saveUserToStorage(refreshedUser);
      return refreshedUser;
    } catch (error) {
      throw toAuthError(error, 'Unable to refresh user data.');
    }
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('jh_user');
  };

  const value = {
    user,
    login,
    logout,
    updateUser,
    refreshUser,
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
