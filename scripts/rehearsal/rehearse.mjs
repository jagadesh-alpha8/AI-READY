// End-to-end rehearsal of frontend-new's production build against scripts/rehearsal/standin_server.py.
//
// Drives the college's whole flow in a real browser, in the workspace design (23 Nov): the Stage 1 assessment, the
// overview and results with the level and stars ("so far"), follow-up questions (an answer with an upload, "I need to
// check", a Skip), a document we missed, publishing (closing the follow-up stage), the final result, the leadership
// and detailed reports and the technical appendix for both results, actions, paces, and plan evaluation. Stops at
// the first step that doesn't show what it should, and leaves a screenshot of it.
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
// The workspace's pages by address (the sidebar names sections; the pages are tabs within them).
async function open(path) {
  await page.goto(`${BASE}${path}`);
  await page.waitForLoadState('networkidle');
}
const scoreOnPage = async () => Number(((await page.locator('[aria-label*="out of 100"]').first().getAttribute('aria-label')) || '').match(/score (\d+) out of 100/)?.[1]);
const OLD_WORDS = /\b(Silver|Gold|Platinum|Diamond|Tier:|AIQIF-C\d)/;
async function reload() { await page.reload(); await page.waitForLoadState('networkidle'); }
const button = (name, exact = false) => main().getByRole('button', { name, exact }).first();
async function tab(name) { await main().getByRole('tablist', { name: 'Questionnaire' }).getByRole('tab', { name }).click(); await page.waitForLoadState('networkidle'); }
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
  await open('/assessment');
  await expectText('Run your assessment');
  await button('Run the assessment', true).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Run the assessment' }).click();
  // The stand-in runs the assessment inside the request, so the dialog stays until it has finished.
  await page.getByRole('dialog').waitFor({ state: 'detached', timeout: 300000 });
  await page.waitForLoadState('networkidle');
  // The page polls the run list every few seconds and then loads the result.
  await main().getByText('Your Stage 1 result').first().waitFor({ timeout: 60000 }).catch(() => {});
  await expectText('Your Stage 1 result', 'the Stage 1 result on the Assessment page:');
  await expectText(/so far/);
  await shot('assessment-stage-1');
});

await step('Overview and Results show the Stage 1 level, in words and stars, with no old tier names', async () => {
  await open('/');
  await expectText(/Stage 1 · from your documents/i);
  stageOne = await scoreOnPage();
  if (!Number.isFinite(stageOne)) throw new Error('no Stage 1 score on the overview');
  await expectText(/Starting out|Getting there|Prepared|Advanced|Leading/);
  await expectNoText(OLD_WORDS, 'an old tier name or a code:');
  await shot('overview-stage-1');
  await open('/cri');
  await expectText(/Starting out|Getting there|Prepared|Advanced|Leading/);
  await expectNoText(OLD_WORDS, 'an old tier name or a code on Results:');
  await open('/areas');
  await expectText('What to show next');
  await shot('results-stage-1');
});

await step('plan the follow-up questions', async () => {
  await open('/questionnaire');
  await expectText('Before you start');
  await button('Plan follow-up questions').click();
  await page.waitForTimeout(1500);
  await reload();
  await expectText(/Question 1 of \d+/i);
});

await step('answer "Yes" with an uploaded document', async () => {
  await main().locator('label.choice', { hasText: 'Yes, with supporting evidence' }).click();
  await main().locator('textarea').first().fill('Item 1: 85 of 120 faculty completed the accredited programme; the register is attached.');
  await main().locator('input[type=file]').first().setInputFiles(REGISTER);
  await clickAndWait(button('Save & continue'), '/responses');
  await page.waitForTimeout(1500);
  await reload();
  if ((await text()).includes('One follow-up')) {   // the check asked one follow-up: Skip it
    await clickAndWait(button('Skip this question'), '/follow-up');
    await reload();
  }
  await expectText(/Questions answered\s*\n?\s*1\s*\/\s*\d+/, 'one question answered:');
});

await step('"I need to check" saves the question for later', async () => {
  await main().getByText(/Question \d+ of \d+/i).first().waitFor();
  await main().locator('label.choice', { hasText: 'I need to check' }).click();
  await clickAndWait(button('Save for later'), '/to-check');
  await reload();
  await expectText(/Questions answered\s*\n?\s*1\s*\/\s*\d+/, 'still one answered (a mark is not an answer):');
});

await step('Skip a question', async () => {
  await main().getByText(/Question \d+ of \d+/i).first().waitFor();
  await clickAndWait(button('Skip this question'), '/responses');
  await reload();
  await expectText(/Questions answered\s*\n?\s*2\s*\/\s*\d+/, 'two questions answered:');
  await shot('questionnaire-answered');
});

await step('send a document we missed (areas by name, not code)', async () => {
  await tab('Send a document we missed');
  await main().locator('input[type=file]').first().setInputFiles(MINUTES);
  await main().locator('textarea').first().fill('Board minutes adopting an AI research ethics review procedure.');
  // An area with gaps at Stage 1 (Research and innovation), so the document can raise the score.
  await main().locator('label', { hasText: 'Research and innovation' }).first().locator('input[type=checkbox]').check();
  await clickAndWait(button('Submit evidence'), '/additional-evidence');
  await reload();
  await tab('Send a document we missed');
  await expectNoText('Nothing submitted yet.', 'the submission listed:');
});

await step('publish the final result (close the follow-up stage)', async () => {
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
    if (/Check how far the evidence goes/.test(body) && /have not been judged yet/.test(body)) {
      await button('Check how far the evidence goes').click();   // depth answers must be judged before closing
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

await step('Overview, Results and Assessment show the final result', async () => {
  await open('/');
  await expectText('Final result');
  const finalScore = await scoreOnPage();
  if (!(finalScore > stageOne)) throw new Error(`the final score (${finalScore}) should be above Stage 1 (${stageOne}): both documents carry new evidence`);
  await expectNoText(OLD_WORDS, 'an old tier name or a code:');
  await open('/cri');
  await expectNoText(OLD_WORDS, 'an old tier name or a code on Results:');
  await shot('results-final');
  await open('/assessment');
  await expectText('Your final result');
});

await step('the leadership and detailed reports and the technical appendix download for both results', async () => {
  await open('/reports');
  await expectText('Final result');
  await expectText('Leadership report');
  const reports = [];
  const listen = (r) => { if (/\/capability-runs\/[^/]+\/report/.test(r.url())) reports.push([r.url(), r.status()]); };
  page.on('response', listen);
  const pdfs = main().getByRole('button', { name: 'Download PDF' });
  await pdfs.nth(3).waitFor({ timeout: 30000 });
  for (let i = 0; i < 4; i += 1) { await pdfs.nth(i).click(); await page.waitForTimeout(900); }
  const [tabPage] = await Promise.all([page.context().waitForEvent('page'), main().getByRole('button', { name: 'Open', exact: true }).first().click()]);
  await tabPage.waitForURL(/^blob:/, { timeout: 60000 });   // the tab opens first, then the report arrives
  await tabPage.waitForLoadState();
  if (!/AI readiness report/.test(await tabPage.title())) throw new Error(`the opened report's title: ${await tabPage.title()}`);
  await tabPage.close();
  for (const details of await main().locator('details.ws-technical').all()) {
    await details.locator('summary').click();
    const buttons = details.getByRole('button');
    for (let i = 0; i < await buttons.count(); i += 1) { await buttons.nth(i).click(); await page.waitForTimeout(500); }
  }
  await page.waitForLoadState('networkidle');
  page.off('response', listen);
  const bad = reports.filter(([, s]) => s !== 200);
  // 4 PDFs + 1 opened page + 2 results x 6 technical files.
  if (reports.length < 17 || bad.length) throw new Error(`report downloads: ${reports.length} answered, failing: ${JSON.stringify(bad)}`);
  await shot('reports');
});

await step('actions, paces and pathway read in plain words', async () => {
  await open('/actions');
  await expectText('largest gain first');
  await expectNoText(OLD_WORDS, 'an old tier name or a code on Actions:');
  await open('/plan');
  await expectText('Suits most colleges');
  await expectNoText(OLD_WORDS, 'an old tier name or a code on the paces:');
  await open('/pathway');
  await expectText('Five levels of AI readiness');
  await shot('pathway');
});

await step('check your own plan against the final result', async () => {
  await open('/plancompare');
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
