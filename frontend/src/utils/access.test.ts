import { after, describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { bundleComponent } from '../testing/bundle.ts';

describe('Role and Access Control System (3 Target Roles)', async () => {
  const access = await bundleComponent(new URL('./access.ts', import.meta.url), {
    AuthContext: 'export const useAuth = () => ({ user: null });',
  });
  after(() => access.cleanup());

  const {
    ROLE_LABELS,
    roleLabel,
    canDo,
    canSeeMenu,
    canSeeSettingsTab,
  } = access.mod;

  it('defines exactly the 3 target roles in ROLE_LABELS', () => {
    const roles = Object.keys(ROLE_LABELS);
    assert.deepEqual(roles.sort(), ['consultant', 'iqac_coordinator', 'super_admin']);
    assert.equal(ROLE_LABELS.super_admin, 'Super Admin');
    assert.equal(ROLE_LABELS.consultant, 'InGage Consultant');
    assert.equal(ROLE_LABELS.iqac_coordinator, 'IQAC Coordinator');
  });

  it('formats display names for the 3 target roles and legacy historical roles', () => {
    assert.equal(roleLabel('super_admin'), 'Super Admin');
    assert.equal(roleLabel('consultant'), 'InGage Consultant');
    assert.equal(roleLabel('iqac_coordinator'), 'IQAC Coordinator');
    // Historical audit labels
    assert.equal(roleLabel('institution_admin'), 'Institution Admin');
    assert.equal(roleLabel('registrar'), 'Registrar');
    assert.equal(roleLabel('viewer'), 'Viewer');
    assert.equal(roleLabel(''), '');
  });

  it('strictly separates Super Admin vs Consultant vs IQAC Coordinator privileges', () => {
    // 1. User Administration: Super Admin (platform-wide) and IQAC Coordinator (own college); NOT Consultant
    assert.equal(canDo('super_admin', 'users.manage'), true);
    assert.equal(canDo('iqac_coordinator', 'users.manage'), true);
    assert.equal(canDo('consultant', 'users.manage'), false);

    // 2. AI-QIF Expert queue: Super Admin only
    assert.equal(canDo('super_admin', 'aiqif.expert'), true);
    assert.equal(canDo('consultant', 'aiqif.expert'), false);
    assert.equal(canDo('iqac_coordinator', 'aiqif.expert'), false);

    // 3. Benchmark Studio: InGage Staff (Super Admin & Consultant); NOT IQAC Coordinator
    assert.equal(canDo('super_admin', 'benchmarks.studio'), true);
    assert.equal(canDo('consultant', 'benchmarks.studio'), true);
    assert.equal(canDo('iqac_coordinator', 'benchmarks.studio'), false);

    // 4. Recommendation editing: InGage Staff only
    assert.equal(canDo('super_admin', 'recommendations.edit'), true);
    assert.equal(canDo('consultant', 'recommendations.edit'), true);
    assert.equal(canDo('iqac_coordinator', 'recommendations.edit'), false);

    // 5. Institution Deletion: Super Admin & Consultant
    assert.equal(canDo('super_admin', 'institution.delete'), true);
    assert.equal(canDo('consultant', 'institution.delete'), true);
    assert.equal(canDo('iqac_coordinator', 'institution.delete'), false);

    // 6. Sprint management & Baseline approval: All 3 roles within scope
    assert.equal(canDo('super_admin', 'sprint.manage'), true);
    assert.equal(canDo('consultant', 'sprint.manage'), true);
    assert.equal(canDo('iqac_coordinator', 'sprint.manage'), true);

    // 7. Fact review & Gap resolution: All 3 roles within scope
    assert.equal(canDo('super_admin', 'facts.review'), true);
    assert.equal(canDo('consultant', 'facts.review'), true);
    assert.equal(canDo('iqac_coordinator', 'facts.review'), true);
    assert.equal(canDo('super_admin', 'gaps.resolve'), true);
    assert.equal(canDo('consultant', 'gaps.resolve'), true);
    assert.equal(canDo('iqac_coordinator', 'gaps.resolve'), true);
  });

  it('allows all 3 roles to see the Role & Access Matrix settings tab', () => {
    const roles = ['super_admin', 'consultant', 'iqac_coordinator'];
    for (const role of roles) {
      assert.equal(canSeeSettingsTab(role, 'access'), true, `${role} sees access tab`);
    }
  });

  it('restricts benchmark studio and AI usage settings menus', () => {
    assert.equal(canSeeMenu('super_admin', 'benchmark-studio'), true);
    assert.equal(canSeeMenu('consultant', 'benchmark-studio'), true);
    assert.equal(canSeeMenu('iqac_coordinator', 'benchmark-studio'), false);

    assert.equal(canSeeMenu('super_admin', 'sprint-aiqif-review'), true);
    assert.equal(canSeeMenu('consultant', 'sprint-aiqif-review'), false);
    assert.equal(canSeeMenu('iqac_coordinator', 'sprint-aiqif-review'), false);
  });
});

