import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listInstitutions } from '../../api/institutions';
import { createSprint } from '../../api/sprints';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { InlineError } from '../../components/ApiStates';
import type { Institution } from '../../types';
import { Building, Sparkles, ArrowRight, Info } from 'lucide-react';
import { useAccess } from '../../utils/access';
import { TakeTourButton } from '../../components/tour/MenuTourOfferBanner';

export const SprintSetup: React.FC = () => {
  const { step } = useAccess();
  const navigate = useNavigate();
  const { data: institutionsData } = useApiResource<Institution[]>(() => listInstitutions(), []);
  const institutions = institutionsData || [];
  const [selectedInstId, setSelectedInstId] = useState('');

  // Institutions are no longer created here. They are owned by the Institution
  // DNA module, so this screen only ever *selects* one — which keeps a single
  // place responsible for institutional master data instead of two forms that
  // can disagree about it.

  // No sprint-mode picker: the platform runs one discovery method, so there is
  // nothing to choose. `sprint_mode` is left off the create payload entirely
  // and Sprint.mode's model default supplies it — one place decides the
  // method, rather than a form that always sends the same value.
  const [academicYear, setAcademicYear] = useState('2026-27');
  // A sprint used to be created with no name at all, so every list showed a
  // bare code ("SPR-2AC52B86") that says nothing about whose sprint it is.
  // The name defaults to the selected college and follows it until the user
  // types their own, at which point their wording wins.
  const [name, setName] = useState('');
  const [nameEdited, setNameEdited] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const selectedInstitution = institutions.find((inst) => inst.id === selectedInstId);

  React.useEffect(() => {
    if (nameEdited || !selectedInstitution) return;
    setName(`${selectedInstitution.name} — AI Readiness ${academicYear}`);
  }, [selectedInstitution, academicYear, nameEdited]);

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
        academic_year: academicYear,
        name: name.trim() || `${selectedInstitution?.name ?? 'Institution'} — AI Readiness ${academicYear}`,
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
      {error && <InlineError message={error} onDismiss={() => setError('')} />}

      <form onSubmit={handleCreateSprint} className="space-y-6">
        {/* One card, one heading: with the mode picker gone there are only
            three fields left, and splitting them across two headed sections
            made the screen look busier than it is. */}
        <div data-tour="sprint-setup-form" className="glass-card p-5 sm:p-6 space-y-4">
          <h2 className="eyebrow flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-brand-800" /> Sprint Settings
          </h2>

          {institutions.length > 0 ? (
            <div data-tour="sprint-setup-institution">
              <label className="label">Select Institution</label>
              <select
                value={selectedInstId}
                onChange={(e) => setSelectedInstId(e.target.value)}
                required
                className="input"
              >
                {institutions.map((inst) => (
                  <option key={inst.id} value={inst.id}>
                    {/* Only the parts that exist: an institution with no
                        city, state or type rendered as "NAME (, ) -". */}
                    {[
                      inst.name,
                      [inst.city, inst.state].filter(Boolean).join(', '),
                      inst.institution_type,
                    ].filter(Boolean).join(' · ')}
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

          <div data-tour="sprint-setup-name">
            <label className="label" htmlFor="sprint-name">Sprint Name *</label>
            <input
              id="sprint-name"
              type="text"
              value={name}
              onChange={(e) => { setName(e.target.value); setNameEdited(true); }}
              required
              className="input"
              placeholder="e.g. St. Joseph's College — AI Readiness 2026-27"
            />
            <p className="text-xs text-ink-500 mt-1.5">
              Names the sprint everywhere it is listed. It follows the selected college until you
              change it.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
          <button type="submit" data-tour="sprint-setup-submit" disabled={loading || !selectedInstId} className="btn-primary">
            <span>{loading ? 'Initializing Sprint...' : 'Create Sprint & Upload Pack'}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </form>
    </div>
  );
};
