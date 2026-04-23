import { createContext, useContext, useMemo, useState } from 'react';
import api from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('jh_user');
    return saved ? JSON.parse(saved) : null;
  });

  const saveUserToStorage = (userData) => {
    setUser(userData);
    localStorage.setItem('jh_user', JSON.stringify(userData));
  };

  const login = async ({ email, password }) => {
    try {
      const response = await api.post('/auth/login', {
        email,
        password,
      });

      const loggedInUser = response.data.user;

      saveUserToStorage(loggedInUser);
      return loggedInUser;
    } catch (error) {
      throw new Error(error.response?.data?.message || 'Login failed.');
    }
  };

  const updateUser = (updatedUser) => {
    saveUserToStorage(updatedUser);
  };

  const refreshUser = async (userId) => {
    try {
      const response = await api.get(`/profile/${userId}`);
      const refreshedUser = response.data;

      saveUserToStorage(refreshedUser);
      return refreshedUser;
    } catch (error) {
      throw new Error(error.response?.data?.message || 'Unable to refresh user data.');
    }
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('jh_user');
  };

  const value = useMemo(
    () => ({ user, login, logout, updateUser, refreshUser }),
    [user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return context;
}