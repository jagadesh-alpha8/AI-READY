import { Link } from 'react-router-dom';
import { PageHeading, Panel, Pill, Stat, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useReviewMode } from '../hooks/useReviewMode';
import { NAV_GROUPS, pathOf } from '../navigation';
import { PAGE_API_STATUS, PENDING, STATUS_LABEL, STATUS_MARK, STATUS_MEANING, STATUS_TONE, type ApiStatus } from '../utils/apiStatus';

const ORDER: ApiStatus[] = ['live', 'partial', 'decision'];

/** Every screen with its backend status and what it waits for (codes as in the backend API requests PDF). */
export function BackendStatus() {
  const { canSee } = useAccess();
  const [review, setReview] = useReviewMode();
  const screens = NAV_GROUPS.flatMap((g) => g.items.filter((i) => i.key !== 'apistatus' && canSee(i.key)).map((i) => ({ group: g.label, ...i, ...PAGE_API_STATUS[i.key] })));
  const count = (s: ApiStatus) => screens.filter((x) => x.status === s).length;
  const used = Object.keys(PENDING).filter((code) => screens.some((x) => x.pending.some((p) => p.code === code)));

  return (
    <>
      <PageHeading page="apistatus" actions={(
        <button className={review ? 'primary-action' : 'secondary-button'} onClick={() => setReview(!review)}>{review ? 'Turn Review mode off' : 'Turn Review mode on'}</button>
      )} />
      <div className="stat-grid">
        {ORDER.map((s) => <Stat key={s} label={`${STATUS_MARK[s]} ${STATUS_LABEL[s]}`} value={count(s)} note={STATUS_MEANING[s]} />)}
        <Stat label="Items with the backend" value={used.length} note="R-xx APIs and D-xx decisions" />
      </div>
      <Table columns={['Screen', 'Menu group', 'Status', 'Waiting for']}>
        {[...screens].sort((a, b) => ORDER.indexOf(b.status) - ORDER.indexOf(a.status)).map((x) => (
          <tr key={x.key}>
            <td><Link to={pathOf(x.key)}><strong>{x.label}</strong></Link></td>
            <td>{x.group}</td>
            <td><Pill tone={STATUS_TONE[x.status]} label={`${STATUS_MARK[x.status]} ${STATUS_LABEL[x.status]}`} /></td>
            <td>{x.pending.length === 0 ? <span className="muted">Nothing</span> : x.pending.map((p) => <div key={p.code}><b>{p.code}</b> {p.text}</div>)}</td>
          </tr>
        ))}
      </Table>
      <Panel title="Backend items" sub="As listed in Backend_API_Requests_A2.pdf (frontend-new/docs)">
        <Table columns={['Code', 'Item', 'Screens']}>
          {used.map((code) => (
            <tr key={code}>
              <td><b>{code}</b></td>
              <td>{PENDING[code]}</td>
              <td>{screens.filter((x) => x.pending.some((p) => p.code === code)).map((x) => x.label).join(', ')}</td>
            </tr>
          ))}
        </Table>
      </Panel>
      <p className="muted">
        In Review mode every menu carries its mark ({ORDER.map((s) => `${STATUS_MARK[s]} ${STATUS_LABEL[s].toLowerCase()}`).join(', ')}), every screen opens with
        its status, and every sample block shows the code it waits for.
      </p>
    </>
  );
}
