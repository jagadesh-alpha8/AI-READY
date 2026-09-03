import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listInstitutions } from '../../api/institutions';
import { createSprint } from '../../api/sprints';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { InlineError } from '../../components/ApiStates';
import type { Institution, SprintMode } from '../../types';
import { Building, Sparkles, ArrowRight, Info } from 'lucide-react';

export const SprintSetup: React.FC = () => {
  const navigate = useNavigate();
  const { data: institutionsData } = useApiResource<Institution[]>(() => listInstitutions(), []);
  const institutions = institutionsData || [];
  const [selectedInstId, setSelectedInstId] = useState('');

  // Institutions are no longer created here. They are owned by the Institution
  // DNA module, so this screen only ever *selects* one — which keeps a single
  // place responsible for institutional master data instead of two forms that
  // can disagree about it.

  // Sprint Form state
  const [sprintMode, setSprintMode] = useState<SprintMode>('verified_cri');
  const [academicYear, setAcademicYear] = useState('2026-27');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  React.useEffect(() => {
    if (institutions.length > 0 && !selectedInstId) {
      setSelectedInstId(institutions[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [institutions.length]);

  const handleCreateSprint = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedInstId) {
      setError('Select an institution before creating a sprint.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      // Create discovery sprint
      const sprintRes = await createSprint({
        institution_id: selectedInstId,
        sprint_mode: sprintMode,
        academic_year: academicYear,
      });

      const newSprintId = sprintRes.data.id;
      navigate(`/sprint/${newSprintId}/upload`);
    } catch (err: any) {
      setError(getErrorMessage(err, 'Failed to create sprint'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-brand-500/10 border border-brand-500/30 text-brand-800 shrink-0">
            <Building className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900">Screen 1: Institution &amp; Discovery Sprint Setup</h1>
            <p className="text-sm text-ink-500">Setup institutional baseline parameters and select sprint audit mode.</p>
          </div>
        </div>
      </div>

      {error && <InlineError message={error} onDismiss={() => setError('')} />}

      <form onSubmit={handleCreateSprint} className="space-y-6">
        {/* Institution Details */}
        <div className="glass-card p-5 sm:p-6 space-y-4">
          <h2 className="eyebrow flex items-center gap-2">
            <Building className="w-4 h-4 text-brand-800" /> Institution Profile
          </h2>

          {institutions.length > 0 ? (
            <div>
              <label className="label">Select Institution</label>
              <select
                value={selectedInstId}
                onChange={(e) => setSelectedInstId(e.target.value)}
                required
                className="input"
              >
                {institutions.map((inst) => (
                  <option key={inst.id} value={inst.id}>
                    {inst.name} ({inst.city}, {inst.state}) - {inst.institution_type}
                  </option>
                ))}
              </select>
              <p className="mt-2 flex items-start gap-1.5 text-xs text-ink-500">
                <Info className="w-3.5 h-3.5 shrink-0 mt-px" />
                <span>Institution details are maintained in Institution DNA.</span>
              </p>
            </div>
          ) : (
            <div className="flex items-start gap-2.5 p-3 rounded-lg bg-surface border border-line-200 text-sm text-ink-600">
              <Info className="w-4 h-4 shrink-0 mt-0.5 text-ink-500" />
              <span>
                No institutions are set up yet. Add one in <strong>Institution DNA</strong> before
                starting a discovery sprint.
              </span>
            </div>
          )}
        </div>

        {/* Sprint Configuration */}
        <div className="glass-card p-5 sm:p-6 space-y-4">
          <h2 className="eyebrow flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-brand-800" /> Sprint Settings
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div
              onClick={() => setSprintMode('quick_cri')}
              className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${
                sprintMode === 'quick_cri'
                  ? 'bg-brand-50 border-brand-500 shadow-card'
                  : 'bg-card border-line-200 hover:border-line-300'
              }`}
            >
              <span className="text-xs font-bold text-brand-800">Quick CRI</span>
              <p className="text-sm font-semibold text-ink-900 mt-1">Same Day Audit</p>
              <p className="text-xs text-ink-500 mt-2">8-12 Documents | 60-75% Confidence | Rapid baseline for sales discovery</p>
            </div>

            <div
              onClick={() => setSprintMode('verified_cri')}
              className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${
                sprintMode === 'verified_cri'
                  ? 'bg-brand-50 border-brand-500 shadow-card'
                  : 'bg-card border-line-200 hover:border-line-300'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-brand-800">Verified CRI</span>
                <span className="text-[10px] font-extrabold bg-brand-500 text-on-brand px-1.5 py-0.5 rounded">RECOMMENDED</span>
              </div>
              <p className="text-sm font-semibold text-ink-900 mt-1">24-48 Hours Discovery</p>
              <p className="text-xs text-ink-500 mt-2">15-25 Documents | 80-90% Confidence | Formal baseline &amp; transformation proposal</p>
            </div>

            <div
              onClick={() => setSprintMode('full_digital_twin')}
              className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${
                sprintMode === 'full_digital_twin'
                  ? 'bg-brand-50 border-brand-500 shadow-card'
                  : 'bg-card border-line-200 hover:border-line-300'
              }`}
            >
              <span className="text-xs font-bold text-brand-800">Full Digital Twin</span>
              <p className="text-sm font-semibold text-ink-900 mt-1">5-15 Days Enterprise</p>
              <p className="text-xs text-ink-500 mt-2">40-80+ Documents | 90%+ Confidence | Continuous enterprise digital twin</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
            <div>
              <label className="label">Academic Year *</label>
              <input
                type="text"
                value={academicYear}
                onChange={(e) => setAcademicYear(e.target.value)}
                required
                className="input"
              />
            </div>

            <div>
              <label className="label">Nodal Officer</label>
              <input
                type="text"
                value="Prof. S. Kanthaswamy (IQAC Head)"
                disabled
                className="input"
              />
            </div>
          </div>
        </div>

        {/* Submit */}
        <div className="flex flex-col-reverse sm:flex-row justify-end gap-3">
          <button type="button" onClick={() => navigate('/dashboard')} className="btn-secondary">
            Cancel
          </button>
          <button type="submit" disabled={loading || !selectedInstId} className="btn-primary">
            <span>{loading ? 'Initializing Sprint...' : 'Create Sprint & Upload Pack'}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </form>
    </div>
  );
};
