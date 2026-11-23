// End-to-end rehearsal of frontend-new's production build against scripts/rehearsal/standin_server.py.
//
// Drives the college's whole flow in a real browser: the Stage 1 assessment, the overview and results with no tier,
// follow-up questions (an answer with an upload, a Skip), a document we missed, "Check answers now", publishing
// (closing the follow-up stage), the Final AI-READY Score with its tier band, every report for both results, and plan
// evaluation. Stops at the first step that doesn't show what it should, and leaves a screenshot of it.
//
// Usage, with the stand-in server on :8000 and `npx vite preview --port 4173` running in frontend-new:
//   PLAYWRIGHT_MODULE=/path/to/node_modules/playwright/index.mjs node scripts/rehearsal/rehearse.mjs
// Each run needs a fresh stand-in server (it starts from an empty sprint).
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const BASE = process.env.REHEARSAL_URL || 'http://127.0.0.1:4173';
const OUT = process.env.REHEARSAL_OUT || mkdtempSync(join(tmpdir(), 'rehearsal-'));
mkdirSync(OUT, { recursive: true });
const EMAIL = 'rehearsal@example.com';
const PASSWORD = 'rehearsal-pass-1';

// Two small PDFs written on the fly. "NEWEVIDENCE" is what the stand-in model treats as new, supporting evidence.
function pdf(text) {
  const words = text.replace(/[()\\]/g, '').split(' ');
  const lines = [''];
  for (const w of words) {
    if ((lines[lines.length - 1] + ' ' + w).length > 80) lines.push(w);
    else lines[lines.length - 1] = (lines[lines.length - 1] + ' ' + w).trim();
  }
  const stream = `BT /F1 11 Tf 14 TL 40 760 Td ${lines.map((l) => `(${l}) Tj T*`).join(' ')} ET`;
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
  ];
  let body = '%PDF-1.4\n';
  const offsets = [];
  objects.forEach((o, i) => { offsets.push(body.length); body += `${i + 1} 0 obj\n${o}\nendobj\n`; });
  const xref = body.length;
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets.map((n) => `${String(n).padStart(10, '0')} 00000 n \n`).join('')}`;
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return body;
}
const REGISTER = join(OUT, 'certificate-register.pdf');
const MINUTES = join(OUT, 'ethics-minutes.pdf');
// Over 120 characters each: the re-judge ignores new pieces shorter than that (layer2.MIN_PIECE).
writeFileSync(REGISTER, pdf('NEWEVIDENCE Certificate register 2024-25: 85 of 120 faculty completed the 40-hour accredited AI programme run with the state university; hours, provider accreditation and completion are recorded.'));
writeFileSync(MINUTES, pdf('NEWEVIDENCE Board minutes 2024-25: the college adopted an AI research ethics review procedure, with a named committee, approval records and an annual review of every AI research project.'));

let stageOne = null;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const problems = [];
page.on('pageerror', (e) => problems.push(`page error: ${e.message}`));
page.on('response', (r) => {
  if (r.url().includes('/api/') && r.status() >= 500) problems.push(`HTTP ${r.status()} ${r.request().method()} ${r.url()}`);
});

let n = 0;
async function step(name, fn) {
  n += 1;
  process.stdout.write(`${String(n).padStart(2)}. ${name} … `);
  try {
    await fn();
    if (problems.length) throw new Error(problems.join('; '));
    console.log('ok');
  } catch (err) {
    console.log('FAILED');
    const shot = join(OUT, `failed-step-${n}.png`);
    await page.screenshot({ path: shot, fullPage: true }).catch(() => {});
    console.error(`   ${err.message}\n   screenshot: ${shot}`);
    await browser.close();
    process.exit(1);
  }
}
const main = () => page.locator('main');
const text = async () => main().innerText();
async function expectText(pattern, message) {
  await main().getByText(pattern).first().waitFor({ timeout: 20000 }).catch(() => {});
  const body = await text();
  if (!(pattern instanceof RegExp ? pattern.test(body) : body.includes(pattern))) {
    throw new Error(`${message || 'expected'} ${pattern} on the page`);
  }
}
async function expectNoText(pattern, message) {
  const body = await text();
  if (pattern instanceof RegExp ? pattern.test(body) : body.includes(pattern)) throw new Error(`${message || 'did not expect'} ${pattern}`);
}
async function open(link) {
  await page.getByRole('link', { name: link, exact: true }).first().click();
  await page.waitForLoadState('networkidle');
}
async function reload() { await page.reload(); await page.waitForLoadState('networkidle'); }
const button = (name, exact = false) => main().getByRole('button', { name, exact }).first();
async function tab(name) { await main().getByRole('tab', { name }).click(); await page.waitForLoadState('networkidle'); }
// Click and wait for the API call it makes, so a click on a page that is still re-rendering isn't lost.
async function clickAndWait(locator, urlPart) {
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.request().method() === 'POST' && r.url().includes(urlPart), { timeout: 30000 }),
    locator.click(),
  ]);
  if (response.status() >= 400) throw new Error(`${urlPart}: HTTP ${response.status()} ${(await response.text()).slice(0, 300)}`);
  await page.waitForLoadState('networkidle');
}
async function shot(name) { await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: true }); }

await step('sign in', async () => {
  await page.goto(`${BASE}/login`);
  await page.fill('#login-email', EMAIL);
  await page.fill('#login-password', PASSWORD);
  await page.click('button[type=submit]');
  await page.getByRole('link', { name: 'Overview', exact: true }).first().waitFor();
});

await step('Stage 1 assessment from the Assessment page', async () => {
  await open('Assessment');
  await button('Start new assessment').click();
  await button('Start (uses credits)').click();
  await expectText(/STAGE 1 RESULT: DOCUMENT REVIEW|Stage 1 result: Document Review/i, 'the Stage 1 label');
  await shot('assessment-stage-1');
});

await step('Overview and Results show the Stage 1 result and no tier', async () => {
  await open('Overview');
  await expectText(/Stage 1/i);
  stageOne = Number(((await text()).match(/(\d+(?:\.\d+)?)\s*\n?\s*AI-READY score \/ 100/) || [])[1]);
  if (!Number.isFinite(stageOne)) throw new Error('no Stage 1 score on the overview');
  await expectNoText(/Final AI-READY Score\s*\n?\s*\d/, 'a final score before publishing:');
  await shot('overview-stage-1');
  await open('Results');
  await expectText('The tier is awarded on the final AI-READY Score');
  await expectNoText(/Tier: (none yet|Silver|Gold|Platinum|Diamond)/, 'a tier at Stage 1:');
  await expectNoText(/Audit CRI|Unverified/, 'the old pillar score in demo mode:');
  await shot('results-stage-1');
});

await step('plan the follow-up questions', async () => {
  await open('Questionnaire');
  await expectText('Before you start');
  await button('Plan follow-up questions').click();
  await page.waitForTimeout(1500);
  await reload();
  await expectText(/Question 1 of \d+/);
});

await step('answer a question with an uploaded document', async () => {
  await main().locator('input[type=file]').first().setInputFiles(REGISTER);
  await main().locator('textarea').first().fill('Item 1: 85 of 120 faculty completed the accredited programme; the register is attached.');
  await clickAndWait(button('Submit answer'), '/responses');
  await page.waitForTimeout(1500);
  await reload();
  if ((await text()).includes('One follow-up')) {   // the check asked one follow-up: Skip it
    await clickAndWait(button('Skip', true), '/follow-up');
    await reload();
  }
  await expectText(/Questions answered\s*\n?\s*1\s*\/\s*\d+/, 'one question answered:');
});

await step('Skip a question', async () => {
  await main().getByText(/Question \d+ of \d+/).first().waitFor();
  await clickAndWait(button('Skip', true), '/responses');
  await reload();
  await expectText(/Questions answered\s*\n?\s*2\s*\/\s*\d+/, 'two questions answered:');
  await shot('questionnaire-answered');
});

await step('send a document we missed', async () => {
  await tab('Send a document we missed');
  await main().locator('input[type=file]').first().setInputFiles(MINUTES);
  await main().locator('textarea').first().fill('Board minutes adopting an AI research ethics review procedure.');
  // An area with gaps at Stage 1 (Research and innovation), so the document can raise the score.
  await main().locator('label', { hasText: 'AIQIF-C7 (whole area)' }).locator('input[type=checkbox]').check();
  await clickAndWait(button('Submit evidence'), '/additional-evidence');
  await reload();
  await tab('Send a document we missed');
  await expectNoText('Nothing submitted yet.', 'the submission listed:');
});

await step('"Check answers now", then publish (close the follow-up stage)', async () => {
  await tab('Follow-up questions');
  if (await button('Check answers now').isVisible().catch(() => false)) {
    await button('Check answers now').click();
    await page.waitForLoadState('networkidle');
    await reload();
  }
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await button('Finish and publish the final result').click();
    await button('Yes, publish').click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
    const body = await text();
    if (/Judge evidence depth/.test(body) && /have not been judged yet/.test(body)) {
      await button('Judge evidence depth').click();   // depth answers must be judged before closing
      await page.waitForLoadState('networkidle');
      await reload();
      continue;
    }
    break;
  }
  await reload();
  await expectText(/follow-up stage is closed/i);
  await shot('questionnaire-closed');
});

await step('Overview and Results show the Final AI-READY Score and its tier band', async () => {
  await open('Overview');
  await expectText(/Final AI-READY Score/i);
  const finalScore = Number(((await text()).match(/(\d+(?:\.\d+)?)\s*\n?\s*AI-READY score \/ 100/) || [])[1]);
  if (!(finalScore > stageOne)) throw new Error(`the final score (${finalScore}) should be above Stage 1 (${stageOne}): both documents carry new evidence`);
  await open('Results');
  await expectText(/Final AI-READY Score/i);
  await expectText(/Tier: (none yet|Silver|Gold|Platinum|Diamond)/);
  await expectText('Silver 60, Gold 70, Platinum 80, Diamond 90');
  await shot('results-final');
});

await step('every report for both results downloads', async () => {
  await open('Reports');
  await expectText(/Final AI-READY Score/i);
  const reports = [];
  const listen = (r) => { if (/\/capability-runs\/[^/]+\/report/.test(r.url())) reports.push([r.url(), r.status()]); };
  page.on('response', listen);
  const buttons = main().locator('table').getByRole('button');
  // The page shows its empty state until the run detail (over 1 MB) arrives, so wait for the table itself.
  await buttons.nth(11).waitFor({ timeout: 30000 }).catch(() => {});
  const count = await buttons.count();
  if (count !== 12) throw new Error(`expected 12 report buttons (2 results x 2 audiences x 3 formats), found ${count}`);
  for (let i = 0; i < count; i += 1) {
    await buttons.nth(i).click();
    await page.waitForTimeout(700);
  }
  await page.waitForLoadState('networkidle');
  page.off('response', listen);
  const bad = reports.filter(([, s]) => s !== 200);
  if (reports.length < 12 || bad.length) throw new Error(`report downloads: ${reports.length} answered, failing: ${JSON.stringify(bad)}`);
  await shot('reports');
});

await step('plan evaluation on the final result', async () => {
  await open('Plan evaluation');
  await button('Compare a plan').click();
  await page.getByRole('dialog').locator('textarea').fill('Year 1: approve an AI policy and train 60 faculty. Year 2: an AI elective for all programmes.');
  await page.getByRole('button', { name: 'Compare (uses credits)' }).click();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  await reload();
  await expectText(/completed/i, 'a completed comparison:');
  await shot('plan-evaluation');
});

await browser.close();
console.log(`\nRehearsal passed. Screenshots: ${OUT}`);
