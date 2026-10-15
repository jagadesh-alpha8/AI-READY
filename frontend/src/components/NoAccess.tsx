import React from 'react';
import { Link } from 'react-router-dom';
import { Lock } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

/** Shown instead of a page this role may not use (see utils/access.ts). */
export const NoAccess: React.FC = () => {
  const { user } = useAuth();
  const role = user?.role?.replace(/_/g, ' ') || 'your role';
  return (
    <div className="glass-card p-8 max-w-lg mx-auto mt-10 text-center space-y-3">
      <Lock className="w-8 h-8 text-ink-500 mx-auto" />
      <h1 className="text-lg font-bold text-ink-900">No access</h1>
      <p className="text-sm text-ink-500">
        This page isn't available for {role}. If you need it, ask your institution admin or InGage to change your role.
      </p>
      <Link to="/dashboard" className="btn-primary inline-flex">Go to the dashboard</Link>
    </div>
  );
};
