// Prove Precept end to end on GenLayer Asimov.
//
//   AT=0x... PADV=<padv pw> PPUB=<ppub pw> node scripts/prove.mjs
//
// padv opens a space with a rule; ppub posts into it. A post that breaks the rule is
// removed on report; an on-topic post is left listed; the author's appeal is judged
// against the same rule; an unreadable post is UNCLEAR and changes nothing. History is
// preserved across every report and appeal.
import { Wallet } from 'ethers';
import { createClient, createAccount } from 'genlayer-js';
import { testnetAsimov } from 'genlayer-js/chains';
import fs from 'fs';
import os from 'os';
import path from 'path';
import url from 'url';

const AT = process.env.AT;
const PADV = process.env.PADV || '';
const PPUB = process.env.PPUB || '';
if (!AT || !PADV || !PPUB) { console.error('set AT, PADV and PPUB'); process.exit(1); }

const ROOT = path.join(path.dirname(url.fileURLToPath(import.meta.url)), '..');
const KS = path.join(os.homedir(), '.genlayer', 'keystores');
async function acct(file, pw) {
  const w = await Wallet.fromEncryptedJson(fs.readFileSync(path.join(KS, file), 'utf8'), pw);
  return { addr: w.address.toLowerCase(), client: createClient({ chain: testnetAsimov, account: createAccount(w.privateKey) }) };
}
const padv = await acct('padv.json', PADV);   // moderator + reporter
const ppub = await acct('ppub.json', PPUB);    // author
const anybody = createClient({ chain: testnetAsimov });

const RAW = 'https://raw.githubusercontent.com/JspIIV/precept/master/docs/';
const RULE = 'No advertising, promotional offers, or solicitations; on-topic discussion only.';
const SPAM = RAW + 'spam-post.txt';
const ONTOPIC = RAW + 'ontopic-post.txt';
const UNREADABLE = RAW + 'no-such-post-9f2c.txt';

const out = [];
const say = l => { console.log(l); out.push(l); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const transient = e => /-32005|-32006|-32029|-32603|at capacity|rate limit|gas rate|reverted.*consensus|consensus.*reverted|backpressure|fetch failed|timeout|502|503|429|ECONNRESET|ENOTFOUND|EAI_AGAIN|getaddrinfo|resource not found/i
  .test(String(e?.details || e?.shortMessage || e?.message || e) + ' ' + String(e?.cause?.cause?.code || e?.cause?.code || ''));

async function read(fn, args = []) {
  for (let a = 1; ; a++) {
    try { return JSON.parse(await anybody.readContract({ address: AT, functionName: fn, args })); }
    catch (e) { if (!transient(e) || a >= 14) throw e; await sleep(5000 * a); }
  }
}
async function write(who, fn, args) {
  for (let a = 1; ; a++) {
    try { return await who.client.writeContract({ address: AT, functionName: fn, args, value: 0n }); }
    catch (e) { if (!transient(e) || a >= 14) throw e; say(`  (${fn} transient, wait ${8 * a}s)`); await sleep(8000 * a); }
  }
}
async function openSpace() {
  const n = (await read('size')).spaces;
  for (let attempt = 1; attempt <= 3; attempt++) {
    await write(padv, 'open_space', ['Town Square', RULE]);
    for (let i = 0; i < 30; i++) { const s = await read('size'); if (s.spaces > n) return String(s.spaces - 1); await sleep(5000); }
  }
  throw new Error('space not opened');
}
async function postItem(sid, url) {
  const n = (await read('size')).posts;
  for (let attempt = 1; attempt <= 3; attempt++) {
    await write(ppub, 'post', [sid, url]);
    for (let i = 0; i < 30; i++) { const s = await read('size'); if (s.posts > n) return String(s.posts - 1); await sleep(5000); }
  }
  throw new Error('post not made');
}
async function moderateUntil(who, fn, id, counter, label) {
  const before = Number((await read('item', [id]))[counter] || 0);
  for (let attempt = 1; attempt <= 4; attempt++) {
    try { await write(who, fn, [id]); } catch (e) { say(`  ${label} err ${String(e.message).slice(0, 50)}`); }
    for (let i = 0; i < 36; i++) {
      await sleep(15000);
      const g = await read('item', [id]);
      if (Number(g[counter] || 0) > before) { say(`  ${label}: ${g.status} v=${g.last_verdict} (${(i + 1) * 15}s)`); return g; }
    }
    say(`  ${label}: not settled after poll, retrying`);
  }
  return await read('item', [id]);
}

say('Precept, proven on GenLayer Asimov');
say('  contract ' + AT);
say('  moderator(padv) ' + padv.addr + '  author(ppub) ' + ppub.addr);
say('');

const baseRec = await read('record', [ppub.addr]);
const baseSize = await read('size');

const sid = await openSpace();
say('padv opened space #' + sid + ' with the rule: ' + RULE);
const spam = await postItem(sid, SPAM);
say('ppub posted #' + spam + ' (an advertisement)');
const ontopic = await postItem(sid, ONTOPIC);
say('ppub posted #' + ontopic + ' (an on-topic comment)');
const clean = await postItem(sid, UNREADABLE);
say('ppub posted #' + clean + ' (an unreadable source)');
say('');

say('reporting the ad #' + spam + '...');
const rSpam = await moderateUntil(padv, 'report', spam, 'reports', 'report-ad');
say('  #' + spam + ' status ' + rSpam.status + ' | ' + (rSpam.reason || ''));
const recAfterRemove = await read('record', [ppub.addr]);

say('reporting the on-topic post #' + ontopic + '...');
const rOn = await moderateUntil(padv, 'report', ontopic, 'reports', 'report-ontopic');
say('  #' + ontopic + ' status ' + rOn.status + ' | ' + (rOn.reason || ''));

say('reporting the unreadable post #' + clean + '...');
const rClean = await moderateUntil(padv, 'report', clean, 'reports', 'report-unreadable');
say('  #' + clean + ' status ' + rClean.status + ' | verdict ' + rClean.last_verdict);

say('the author appeals the removed ad #' + spam + '...');
const aSpam = await moderateUntil(ppub, 'appeal', spam, 'appeals', 'appeal-ad');
say('  #' + spam + ' status ' + aSpam.status + ' | ' + (aSpam.reason || ''));
say('');

const hist = await read('history', [spam]);
const rec = await read('record', [ppub.addr]);
const size = await read('size');
say('ad #' + spam + ' log: [' + hist.log.map(e => e.kind + ':' + e.verdict).join(', ') + ']');
say('author record ' + JSON.stringify(baseRec) + ' -> ' + JSON.stringify(rec));
say('book: ' + JSON.stringify(size));

const checks = [
  ['a post that breaks the rule is REMOVED on report', rSpam.status === 'REMOVED' && rSpam.last_verdict === 'VIOLATES'],
  ["the removal marks the author's record", recAfterRemove.removed - baseRec.removed === 1],
  ['an on-topic post is judged ALLOWED and stays LISTED', rOn.status === 'LISTED' && rOn.last_verdict === 'ALLOWED'],
  ['an unreadable post is UNCLEAR and stays LISTED', rClean.status === 'LISTED' && rClean.last_verdict === 'UNCLEAR'],
  ["the author's appeal is judged against the same rule and, still violating, is upheld", aSpam.status === 'REMOVED'],
  ['every report and appeal is preserved in the log, oldest first',
    hist.log.length >= 2 && hist.log[0].kind === 'report' && hist.log[hist.log.length - 1].kind === 'appeal'],
  ['this run adds one removed post to the book', size.removed - baseSize.removed === 1],
];
say('');
for (const [label, ok] of checks) say((ok ? '  ok   ' : ' FAIL  ') + label);
const failed = checks.filter(([, ok]) => !ok);
say('');
say(failed.length ? `${failed.length} of ${checks.length} checks failed` : `${checks.length} checks. One public rule, applied evenly, with a removal, a dismissal, and an appeal on the record.`);

fs.mkdirSync(path.join(ROOT, 'results'), { recursive: true });
fs.writeFileSync(path.join(ROOT, 'results', 'proved.json'), JSON.stringify({
  proved_at: new Date().toISOString(), network: 'genlayer testnet asimov', contract: AT,
  removed: rSpam, allowed: rOn, unreadable: rClean, appeal: aSpam, history: hist,
  record: rec, size, checks: checks.map(([label, ok]) => ({ label, ok })), transcript: out,
}, null, 2));
say('Written to results/proved.json');
process.exit(failed.length ? 1 : 0);
