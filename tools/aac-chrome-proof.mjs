// Local research harness. Run with Node.js 24+ and a separate Chrome test profile.
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const url = new URL(process.argv[2] || 'http://127.0.0.1:18089/preview.html?autoplay=1');
if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1') throw new Error('Use the loopback research server.');
const output = process.argv[3] || 'work/aac-research/chrome-hls.json';
const fixtures = process.argv[4] || 'work/aac-research';
const wait = ms => new Promise(r => setTimeout(r, ms));
const profile = await mkdtemp(join(tmpdir(), 'metadata-chrome-test-'));
const child = spawn(process.env.METADATA_TEST_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless', '--no-first-run', '--disable-background-networking', '--disable-sync', '--no-default-browser-check',
  '--mute-audio', '--autoplay-policy=no-user-gesture-required', '--remote-debugging-port=0', '--user-data-dir=' + profile,
  url.href
], { stdio: 'ignore' });
let ws;
try {
  let port;
  for (let i = 0; i < 100 && !port; i++) {
    try { port = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; } catch { await wait(100); }
  }
  if (!port) throw new Error('Chrome did not start');
  const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
  const tabs = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const tab = tabs.find(t => t.type === 'page');
  ws = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); });
  let id = 0;
  const calls = new Map();
  ws.addEventListener('message', e => {
    const response = JSON.parse(e.data);
    calls.get(response.id)?.(response);
    calls.delete(response.id);
  });
  function evaluate(expression) {
    const key = ++id;
    return new Promise(resolve => {
      calls.set(key, resolve);
      ws.send(JSON.stringify({ id:key, method:'Runtime.evaluate', params:{ expression, returnByValue:true } }));
    }).then(r => r.result?.result?.value);
  }
  let result;
  for (let i = 0; i < 140; i++) {
    result = await evaluate('window.observation');
    if (result?.ended || result?.errors?.length) break;
    await wait(250);
  }
  const saved = { browser: version.Browser, hls: await evaluate('window.Hls?.version'), result };
  await writeFile(output, JSON.stringify(saved, null, 2));
  console.log(JSON.stringify(saved, null, 2));
  const rows = result?.displayed || [];
  let previous = -1;
  for (const label of ['A', 'B']) {
    const expected = createHash('sha256').update(await readFile(join(fixtures, `cover-${label}.png`))).digest('hex');
    previous = rows.findIndex((row, index) => index > previous && row.title === `Song ${label}` &&
      row.artist === `Artist ${label}` && row.album === `Album ${label}` &&
      !row.imageHidden && row.pictureSha256 === expected);
    if (previous < 0) throw new Error(`Did not display complete song ${label} with its original cover`);
  }
  if (!result?.ended || result?.errors?.length || !rows.some((row, index) => index > previous &&
    !row.title && !row.artist && !row.album && row.imageHidden)) throw new Error('Playback or metadata clearing did not pass');
} finally {
  ws?.close();
  child.kill('SIGTERM');
  await wait(700);
  await rm(profile, { recursive: true, force: true });
}
