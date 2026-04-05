import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import RoleRoute from './components/RoleRoute';
import Login from './pages/Login';
import Register from "./pages/Register";
import Dashboard from './pages/Dashboard';
import Chat from './pages/Chat';
import KnowledgeBase from './pages/KnowledgeBase';
import ArticleDetail from './pages/ArticleDetail';
import Escalation from './pages/Escalation';
import Notifications from './pages/Notifications';
import Profile from './pages/Profile';
import QuizList from './pages/QuizList';
import ContentManagement from './pages/admin/ContentManagement';
import ReviewManagement from './pages/admin/ReviewManagement';
import UserManagement from './pages/admin/UserManagement';
import AISettings from './pages/admin/AISettings';
import Analytics from './pages/admin/Analytics';
import SecurityMonitoring from './pages/admin/SecurityMonitoring';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="chat" element={<Chat />} />
        <Route path="knowledge" element={<KnowledgeBase />} />
        <Route path="knowledge/:id" element={<ArticleDetail />} />
        <Route
          path="escalation"
          element={
            <RoleRoute allowedRoles={['teamlead', 'manager']}>
              <Escalation />
            </RoleRoute>
          }
        />
        <Route path="notifications" element={<Notifications />} />
        <Route path="profile" element={<Profile />} />
        <Route path="quiz" element={<QuizList />} />

        <Route
          path="admin/content"
          element={
            <RoleRoute allowedRoles={['manager']}>
              <ContentManagement />
            </RoleRoute>
          }
        />
        <Route
          path="admin/review"
          element={
            <RoleRoute allowedRoles={['manager']}>
              <ReviewManagement />
            </RoleRoute>
          }
        />
        <Route
          path="admin/users"
          element={
            <RoleRoute allowedRoles={['manager']}>
              <UserManagement />
            </RoleRoute>
          }
        />
        <Route
          path="admin/ai-settings"
          element={
            <RoleRoute allowedRoles={['manager']}>
              <AISettings />
            </RoleRoute>
          }
        />
        <Route
          path="admin/analytics"
          element={
            <RoleRoute allowedRoles={['manager']}>
              <Analytics />
            </RoleRoute>
          }
        />
        <Route
          path="admin/security"
          element={
            <RoleRoute allowedRoles={['manager']}>
              <SecurityMonitoring />
            </RoleRoute>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
