import { useMemo, useState } from 'react';
import { Calculator, CheckCircle2, RadioTower, Search } from 'lucide-react';
import { SectionHeading } from '../components/SectionHeading.jsx';
import { walletApi } from '../services/api.js';

const exampleOperation = {
  sender: '0x1111111111111111111111111111111111111111',
  nonce: '0x0',
  initCode: '0x',
  callData: '0x',
  accountGasLimits: `0x${'0'.repeat(64)}`,
  preVerificationGas: '0x0',
  gasFees: `0x${'0'.repeat(64)}`,
  paymasterAndData: '0x',
  signature: `0x${'1'.repeat(130)}`,
};

function formatError(error) {
  return error instanceof Error ? error.message : 'Unknown request failure';
}

export function Relay() {
  const [operationText, setOperationText] = useState(() => JSON.stringify(exampleOperation, null, 2));
  const [receiptHash, setReceiptHash] = useState('');
  const [state, setState] = useState({ status: 'idle', title: '', payload: null });
  const busy = state.status === 'loading';
  const parsed = useMemo(() => {
    try { return { value: JSON.parse(operationText), error: null }; }
    catch (error) { return { value: null, error: formatError(error) }; }
  }, [operationText]);

  const run = async (title, action) => {
    setState({ status: 'loading', title, payload: null });
    try {
      const payload = await action();
      setState({ status: 'success', title, payload });
      if (payload?.user_operation_hash) setReceiptHash(payload.user_operation_hash);
    } catch (error) {
      setState({ status: 'error', title, payload: formatError(error) });
    }
  };

  return <><SectionHeading title="UserOperation relay" subtitle="Estimate, submit, and inspect a signed ERC-4337 v0.7 UserOperation through the backend."/><div className="relay-layout"><section className="panel relay-editor"><div className="panel-heading"><div><h2>Signed UserOperation</h2><p>JSON fields follow the packed v0.7 bundler format.</p></div><span className="eyebrow-pill pill-blue"><span/> BACKEND API</span></div><label className="json-field"><span>Request body</span><textarea aria-label="UserOperation JSON" spellCheck="false" value={operationText} onChange={(event) => setOperationText(event.target.value)}/></label>{parsed.error && <p className="form-error">Invalid JSON: {parsed.error}</p>}<div className="relay-actions"><button className="button button-secondary" disabled={busy || Boolean(parsed.error)} onClick={() => void run('Gas estimate', () => walletApi.estimateUserOperation(parsed.value))}><Calculator size={14}/> Estimate gas</button><button className="button button-primary" disabled={busy || Boolean(parsed.error)} onClick={() => void run('Submission', () => walletApi.submitUserOperation(parsed.value))}><RadioTower size={14}/> Submit signed operation</button></div></section><aside className="panel relay-result"><h2>Bundler response</h2><p>The backend validates all Ethereum field encodings before forwarding a request.</p><label className="hash-field"><span>UserOperation hash</span><input value={receiptHash} onChange={(event) => setReceiptHash(event.target.value)} placeholder="0x…"/></label><button className="button button-secondary" disabled={busy || !receiptHash} onClick={() => void run('Receipt lookup', () => walletApi.getUserOperationReceipt(receiptHash))}><Search size={14}/> Check receipt</button><div className={`response-box response-${state.status}`}>{state.status === 'idle' ? 'No request sent yet.' : state.status === 'loading' ? 'Waiting for the backend…' : <><strong>{state.status === 'success' && <CheckCircle2 size={14}/>} {state.title}</strong><pre>{typeof state.payload === 'string' ? state.payload : JSON.stringify(state.payload, null, 2)}</pre></>}</div></aside></div></>;
}
