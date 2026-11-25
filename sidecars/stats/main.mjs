// Standalone sidecar backend for the "Phân tích Session" Antigravity panel.
// Reads only the currently open conversation's transcript.jsonl on demand,
// caching results by file mtime:size (zero background polling, zero extra ports).

import { execFile } from 'node:child_process';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Response, SidecarApp } from 'sidecar_sdk';

const HERE = dirname(fileURLToPath(import.meta.url));
const ANALYZER = join(HERE, 'session_analyzer.py');
const HTML_PATH = join(HERE, 'index.html');
const GEMINI_DIR = process.env.ANTIGRAVITY_GEMINI_DIR || join(homedir(), '.gemini');
const BRAIN_DIRS = [
  join(GEMINI_DIR, 'antigravity', 'brain'),
  join(GEMINI_DIR, 'antigravity-cli', 'brain'),
];
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const PYTHON_CANDIDATES = process.platform === 'win32'
  ? [['python', []], ['py', ['-3']], ['python3', []]]
  : [['python3', []], ['python', []]];

let pythonBin = null;
const cache = new Map(); // conversationId -> { stamp, data }

function runExec(cmd, args, timeout = 15000) {
  return new Promise((resolve, reject) => {
    execFile(cmd, args, {
      timeout,
      maxBuffer: 16 * 1024 * 1024,
      env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
      windowsHide: true,
    }, (err, stdout, stderr) => (err ? reject(new Error((stderr || err.message).trim())) : resolve(stdout)));
  });
}

async function findPython() {
  if (pythonBin) return pythonBin;
  for (const [cmd, pre] of PYTHON_CANDIDATES) {
    try {
      const out = await runExec(cmd, [...pre, '--version'], 5000);
      if (/^Python 3\./.test(out.trim())) {
        pythonBin = { cmd, pre };
        return pythonBin;
      }
    } catch { /* try next */ }
  }
  throw new Error('Không tìm thấy Python 3 trong PATH.');
}

function findTranscript(conversationId) {
  for (const bdir of BRAIN_DIRS) {
    const candidate = join(bdir, conversationId, '.system_generated', 'logs', 'transcript.jsonl');
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

function fileStamp(filePath) {
  try {
    const s = statSync(filePath);
    return `${s.mtimeMs}:${s.size}`;
  } catch {
    return '-';
  }
}

async function getSessionReport(conversationId) {
  if (!UUID_RE.test(conversationId || '')) {
    return { error: 'no-conversation' };
  }
  const transcriptPath = findTranscript(conversationId);
  if (!transcriptPath) {
    return { error: 'no-transcript', session_id: conversationId };
  }
  const stamp = fileStamp(transcriptPath);
  const cached = cache.get(conversationId);
  if (cached && cached.stamp === stamp) {
    return cached.data;
  }

  const { cmd, pre } = await findPython();
  const out = await runExec(cmd, [...pre, ANALYZER, '--transcript', transcriptPath, '--session-id', conversationId]);
  const data = { ...JSON.parse(out), updated_at: new Date().toISOString() };
  cache.set(conversationId, { stamp, data });
  // Keep cache bounded to 20 most recent conversations
  if (cache.size > 20) {
    cache.delete(cache.keys().next().value);
  }
  return data;
}

const app = new SidecarApp();

app.page('/', () => new Response(readFileSync(HTML_PATH, 'utf8'), {
  contentType: 'text/html; charset=utf-8',
  headers: { 'Cache-Control': 'no-store' },
}));

app.api('/api/session', async (data) => {
  try {
    return await getSessionReport(data.conversationId);
  } catch (err) {
    return { error: 'failed', message: err.message };
  }
}, 'GET');

app.run();
