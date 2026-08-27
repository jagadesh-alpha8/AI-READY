import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listInstitutions, createInstitution } from '../../api/institutions';
import { createSprint } from '../../api/sprints';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { InlineError } from '../../components/ApiStates';
import type { Institution, SprintMode } from '../../types';
import { Building, Sparkles, ArrowRight } from 'lucide-react';

export const SprintSetup: React.FC = () => {
  const navigate = useNavigate();
  const { data: institutionsData } = useApiResource<Institution[]>(() => listInstitutions(), []);
  const institutions = institutionsData || [];
  const [selectedInstId, setSelectedInstId] = useState('');

  // Institution Create Form state
  const [instName, setInstName] = useState('M. Kumarasamy College of Engineering');
  const [instType, setInstType] = useState('Autonomous Engineering College');
  const [city, setCity] = useState('Karur');
  const [state, setState] = useState('Tamil Nadu');
  const [website, setWebsite] = useState('https://mkce.ac.in');
  const [affiliation, setAffiliation] = useState('Anna University');
  const [accreditation, setAccreditation] = useState('NAAC A+ / NBA Accredited');

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
    setLoading(true);
    setError('');
    try {
      let instId = selectedInstId;

      // Create institution if none selected
      if (!instId) {
        const instRes = await createInstitution({
          name: instName,
          institution_type: instType,
          city,
          state,
          website_url: website,
          affiliation,
          accreditation_status: accreditation,
        });
        instId = instRes.data.id;
      }

      // Create discovery sprint
      const sprintRes = await createSprint({
        institution_id: instId,
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

          {institutions.length > 0 && (
            <div>
              <label className="label">Select Existing Institution</label>
              <select
                value={selectedInstId}
                onChange={(e) => setSelectedInstId(e.target.value)}
                className="input"
              >
                {institutions.map((inst) => (
                  <option key={inst.id} value={inst.id}>
                    {inst.name} ({inst.city}, {inst.state}) - {inst.institution_type}
                  </option>
                ))}
                <option value="">+ Create New Institution Profile</option>
              </select>
            </div>
          )}

          {(!selectedInstId || institutions.length === 0) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
              <div>
                <label className="label">Institution Name *</label>
                <input
                  type="text"
                  value={instName}
                  onChange={(e) => setInstName(e.target.value)}
                  required
                  className="input"
                />
              </div>

              <div>
                <label className="label">Institution Type *</label>
                <input
                  type="text"
                  value={instType}
                  onChange={(e) => setInstType(e.target.value)}
                  required
                  className="input"
                />
              </div>

              <div>
                <label className="label">City</label>
                <input
                  type="text"
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  className="input"
                />
              </div>

              <div>
                <label className="label">State</label>
                <input
                  type="text"
                  value={state}
                  onChange={(e) => setState(e.target.value)}
                  className="input"
                />
              </div>
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
          <button type="submit" disabled={loading} className="btn-primary">
            <span>{loading ? 'Initializing Sprint...' : 'Create Sprint & Upload Pack'}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </form>
    </div>
  );
};
