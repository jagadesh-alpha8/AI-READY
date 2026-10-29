import React, { useState } from 'react';
import {
  CheckCircle2,
  Shield,
  ShieldAlert,
  Building2,
  Lock,
  Globe2,
  Layers,
  Sparkles,
  RefreshCw,
  UserCheck,
} from 'lucide-react';

import { getRoleAccessMatrix, type RoleAccessDefinition, type RoleAccessMatrixResponse } from '../../api/auth';
import { useApiResource } from '../../hooks/useApiResource';
import { useAuth } from '../../context/AuthContext';
import { LoadingState, ErrorState } from '../../components/ApiStates';

export const RoleAccessMatrixTab: React.FC = () => {
  const { user } = useAuth();
  const [selectedRole, setSelectedRole] = useState<string>('all');

  const { data, loading, error, refetch } = useApiResource<RoleAccessMatrixResponse>(
    () => getRoleAccessMatrix(),
    [],
  );

  const roles = data?.roles ?? [];
  const displayRoles = selectedRole === 'all'
    ? roles
    : roles.filter((r) => r.role === selectedRole);

  const getScopeBadge = (roleKey: string) => {
    switch (roleKey) {
      case 'super_admin':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200">
            <Globe2 className="w-3.5 h-3.5" />
            Platform-wide Cross-Institution
          </span>
        );
      case 'consultant':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
            <Sparkles className="w-3.5 h-3.5" />
            InGage Operational Cross-Institution
          </span>
        );
      case 'iqac_coordinator':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <Building2 className="w-3.5 h-3.5" />
            Institution-Scoped (Own College Only)
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Synchronization Notice */}
      <div className="bg-white rounded-xl border border-ink-100 p-5 shadow-sm space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Shield className="w-5 h-5 text-brand-600" />
              <h2 className="text-lg font-semibold text-ink-900">Platform Access Control Matrix</h2>
              <span className="px-2 py-0.5 text-xs font-medium bg-brand-50 text-brand-700 rounded-md border border-brand-200">
                Authoritative 3-Role Architecture
              </span>
            </div>
            <p className="text-sm text-ink-500 mt-1">
              Synchronized directly with backend Django/DRF permission classes and institution-scoped database queries.
              Client navigation guards mirror these authoritative rules.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => refetch()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-ink-700 bg-ink-50 hover:bg-ink-100 rounded-lg transition-colors border border-ink-200"
              title="Refresh access definitions from backend"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Sync Status
            </button>
          </div>
        </div>

        {/* Security Alert Note */}
        <div className="bg-amber-50/70 border border-amber-200/80 rounded-lg p-3 text-xs text-amber-900 flex items-start gap-2.5">
          <Lock className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">Backend-Enforced Security Boundary: </span>
            Hiding menus in the UI is only a navigation convenience. Every action, API route, and data record is
            strictly validated on the backend. IQAC Coordinator accounts can never query, read, or modify data
            belonging to another institution.
          </div>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-2 pt-1 border-t border-ink-100">
          <span className="text-xs font-medium text-ink-500 mr-1">Filter View:</span>
          <button
            onClick={() => setSelectedRole('all')}
            className={`px-3 py-1 text-xs rounded-full font-medium transition-colors ${
              selectedRole === 'all'
                ? 'bg-brand-600 text-white shadow-sm'
                : 'bg-ink-50 text-ink-600 hover:bg-ink-100 border border-ink-200'
            }`}
          >
            All 3 Roles Comparison
          </button>
          {roles.map((r) => (
            <button
              key={r.role}
              onClick={() => setSelectedRole(r.role)}
              className={`px-3 py-1 text-xs rounded-full font-medium transition-colors ${
                selectedRole === r.role
                  ? 'bg-brand-600 text-white shadow-sm'
                  : 'bg-ink-50 text-ink-600 hover:bg-ink-100 border border-ink-200'
              }`}
            >
              {r.name}
              {user?.role === r.role && ' (You)'}
            </button>
          ))}
        </div>
      </div>

      {loading && <LoadingState message="Loading live role & access definitions..." />}
      {error && <ErrorState message={error} onRetry={refetch} />}

      {/* Role Cards */}
      {!loading && !error && (
        <div className="space-y-6">
          {displayRoles.map((roleDef: RoleAccessDefinition) => {
            const isMyRole = user?.role === roleDef.role;

            return (
              <div
                key={roleDef.role}
                className={`bg-white rounded-xl border transition-shadow shadow-sm ${
                  isMyRole
                    ? 'border-brand-300 ring-2 ring-brand-100'
                    : 'border-ink-200'
                }`}
              >
                {/* Role Header */}
                <div className="p-5 border-b border-ink-100 flex flex-col md:flex-row md:items-center justify-between gap-3 bg-gradient-to-r from-ink-50/50 to-transparent">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2.5">
                      <h3 className="text-base font-bold text-ink-900">{roleDef.name}</h3>
                      <code className="text-xs font-mono bg-ink-100 px-2 py-0.5 rounded text-ink-700">
                        {roleDef.role}
                      </code>
                      {isMyRole && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-brand-100 text-brand-800">
                          <UserCheck className="w-3.5 h-3.5" />
                          Your Active Role
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-ink-600">{roleDef.description}</p>
                  </div>
                  <div>{getScopeBadge(roleDef.role)}</div>
                </div>

                <div className="p-5 space-y-6">
                  {/* Scope Details */}
                  <div className="bg-ink-50/60 rounded-lg p-3 text-xs text-ink-700 border border-ink-100">
                    <span className="font-semibold text-ink-900">Institution Scope: </span>
                    {roleDef.institution_scope}
                  </div>

                  {/* Modules & Access Levels */}
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-wider text-ink-500 mb-3 flex items-center gap-1.5">
                      <Layers className="w-3.5 h-3.5" />
                      Available Modules & Permissions
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {roleDef.modules.map((mod, i) => (
                        <div
                          key={i}
                          className="p-3 rounded-lg border border-ink-100 bg-white hover:border-ink-200 transition-colors"
                        >
                          <div className="flex items-center justify-between gap-2 mb-1">
                            <span className="text-xs font-semibold text-ink-900">{mod.name}</span>
                            <span
                              className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                                mod.access.includes('None')
                                  ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                  : mod.access.includes('Full') || mod.access.includes('Exclusive')
                                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                  : 'bg-blue-50 text-blue-700 border border-blue-200'
                              }`}
                            >
                              {mod.access}
                            </span>
                          </div>
                          <p className="text-[11px] text-ink-500 line-clamp-2">{mod.description}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Actions Grid: Permitted vs Prohibited */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                    {/* Permitted Actions */}
                    <div className="bg-emerald-50/40 border border-emerald-100 rounded-lg p-4 space-y-2.5">
                      <h4 className="text-xs font-bold text-emerald-900 flex items-center gap-1.5">
                        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                        Permitted Actions ({roleDef.permitted_actions.length})
                      </h4>
                      <ul className="space-y-1.5">
                        {roleDef.permitted_actions.map((act, idx) => (
                          <li key={idx} className="text-xs text-emerald-950 flex items-start gap-2">
                            <span className="text-emerald-500 font-bold mt-0.5">•</span>
                            <span>{act}</span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* Prohibited / Restricted Actions */}
                    <div className="bg-rose-50/40 border border-rose-100 rounded-lg p-4 space-y-2.5">
                      <h4 className="text-xs font-bold text-rose-900 flex items-center gap-1.5">
                        <ShieldAlert className="w-4 h-4 text-rose-600" />
                        Restricted / Prohibited Actions ({roleDef.prohibited_actions.length})
                      </h4>
                      <ul className="space-y-1.5">
                        {roleDef.prohibited_actions.map((act, idx) => (
                          <li key={idx} className="text-xs text-rose-950 flex items-start gap-2">
                            <span className="text-rose-500 font-bold mt-0.5">•</span>
                            <span>{act}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

