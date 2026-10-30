import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../../testing/bundle.ts';
import type { Institution } from '../../types/index.ts';
import { getErrorMessage } from '../../utils/errors.ts';

const mockInstitution: Institution = {
  id: 'inst-123',
  name: 'Hindusthan College of Engineering',
  short_name: 'HCE',
  institution_type: 'Engineering',
  university_affiliation: 'Anna University',
  website_url: 'https://hce.edu',
  location: 'Coimbatore',
  city: 'Coimbatore',
  state: 'Tamil Nadu',
  country: 'India',
  accreditation_details: 'NAAC A+',
  accreditation_status: 'A+',
  contact_email: 'info@hce.edu',
  contact_phone: '+91 9876543210',
  is_active: true,
  sprint_count: 2,
  student_count: 4500,
  faculty_count: 320,
  priorities: ['NAAC 2026'],
  digital_maturity_level: 3,
  current_ai_usage: 'Pilot projects',
  coordinator_name: 'Dr. Coordinator',
  coordinator_email: 'coord@hce.edu',
  coordinator: {
    name: 'Dr. Coordinator',
    email: 'coord@hce.edu',
    status: 'accepted',
    invitation_status: 'accepted',
    delivery: 'sent',
    account_state: 'existing',
    has_account: true,
    user_id: 'user-coord',
    is_active: true,
  },
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('Institution Deletion & Dependency Preview UI', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');

  const modalBundle = await bundleComponent(new URL('./InstitutionDeleteModal.tsx', import.meta.url), {
    '../../api/institutions': `
      export const getInstitutionDeletionPreview = () => new Promise(() => {});
      export const archiveInstitution = () => new Promise(() => {});
      export const deleteInstitution = () => new Promise(() => {});
    `,
  });

  after(() => {
    modalBundle.cleanup();
  });

  it('returns null when modal is closed', () => {
    const html = renderToStaticMarkup(
      React.createElement(modalBundle.mod.InstitutionDeleteModal, {
        institution: mockInstitution,
        isOpen: false,
        onClose: () => {},
        onSuccess: () => {},
      })
    );
    assert.equal(html, '');
  });

  it('renders modal shell with institution name and loading indicator while inspecting dependencies', () => {
    const html = renderToStaticMarkup(
      React.createElement(modalBundle.mod.InstitutionDeleteModal, {
        institution: mockInstitution,
        isOpen: true,
        onClose: () => {},
        onSuccess: () => {},
      })
    );
    assert.ok(html.includes('Hindusthan College of Engineering'));
    assert.ok(html.includes('Inspecting institution dependencies and audit history'));
    assert.ok(html.includes('Cancel'));
  });

  it('safely extracts user-friendly error message from structured 409 responses and suppresses raw HTML', () => {
    // 1. Structured 409 error
    const err409 = {
      response: {
        status: 409,
        data: {
          error_code: 'INSTITUTION_DELETE_BLOCKED',
          block_reason: 'Cannot delete institution because it contains 2 active sprints and 5 uploaded documents.',
          detail: 'Protected records exist.',
        },
      },
    };
    const msg409 = getErrorMessage(err409);
    assert.equal(
      msg409,
      'Cannot delete institution because it contains 2 active sprints and 5 uploaded documents.'
    );

    // 2. Raw HTML traceback from Django debug page (the bug in the user screenshot)
    const errHtml = {
      response: {
        status: 500,
        data: '<!DOCTYPE html><html><head><title>ProtectedError at /api/v1/institutions/123/</title></head><body><h1>Traceback</h1></body></html>',
      },
    };
    const msgHtml = getErrorMessage(errHtml, 'Failed to delete institution.');
    assert.ok(!msgHtml.includes('<!DOCTYPE'));
    assert.ok(!msgHtml.includes('<h1>Traceback'));
    assert.equal(msgHtml, 'ProtectedError');
  });
});
