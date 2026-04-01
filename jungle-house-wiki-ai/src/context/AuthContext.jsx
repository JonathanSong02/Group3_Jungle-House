import { createContext, useContext, useMemo, useState } from 'react';

const AuthContext = createContext(null);

const mockUsers = {
  staff: {
    name: 'Aina Staff',
    email: 'staff@junglehouse.test',
    role: 'staff',
  },
  teamlead: {
    name: 'Brandon Team Lead',
    email: 'lead@junglehouse.test',
    role: 'teamlead',
  },
  manager: {
    name: 'Cheryl Manager',
    email: 'manager@junglehouse.test',
    role: 'manager',
  },
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('jh_user');
    return saved ? JSON.parse(saved) : null;
  });

  const login = async ({ email, password, role }) => {
    // This is a temporary frontend-only login for development before backend auth is ready.
    if (!email || !password) {
      throw new Error('Email and password are required.');
    }

    const selected = mockUsers[role] ?? mockUsers.staff;
    const loggedInUser = { ...selected, email };
    setUser(loggedInUser);
    localStorage.setItem('jh_user', JSON.stringify(loggedInUser));
    return loggedInUser;
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('jh_user');
  };

  const value = useMemo(() => ({ user, login, logout }), [user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return context;
}
