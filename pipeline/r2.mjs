// Cloudflare R2 (S3 API) uploads for scene packages and site media.
//   node pipeline/r2.mjs ls  [prefix]                 list objects (sizes, keys)
//   node pipeline/r2.mjs put <local file|dir> <key|prefix/>   upload; a directory uploads recursively,
//                                                       files already there with the same size are skipped
// Credentials come from the environment: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
// (anyscene-public for site media and free scenes, anyscene-packs for paid packs).
// On Windows they are read from the user environment in the registry, so shells opened earlier still see them.

import { execFileSync } from 'node:child_process';
import { createReadStream, readdirSync, statSync } from 'node:fs';
import { basename, extname, join, relative, sep } from 'node:path';
import { ListObjectsV2Command, S3Client } from '@aws-sdk/client-s3';
import { Upload } from '@aws-sdk/lib-storage';

function userEnv(name) {
  if (process.env[name]) return process.env[name];
  if (process.platform !== 'win32') return undefined;
  try {
    const out = execFileSync('reg', ['query', 'HKCU\\Environment', '/v', name], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
    return out.match(new RegExp(`${name}\\s+REG_\\w+\\s+(\\S+)`))?.[1];
  } catch {
    return undefined;
  }
}

const [ACCOUNT, KEY, SECRET, BUCKET] = ['R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET'].map(userEnv);
if (!ACCOUNT || !KEY || !SECRET || !BUCKET) throw new Error('set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_BUCKET');
const s3 = new S3Client({ region: 'auto', endpoint: `https://${ACCOUNT}.r2.cloudflarestorage.com`, credentials: { accessKeyId: KEY, secretAccessKey: SECRET } });

const TYPES = {
  '.mp4': 'video/mp4', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp',
  '.json': 'application/json', '.zip': 'application/zip', '.md': 'text/markdown; charset=utf-8', '.txt': 'text/plain; charset=utf-8',
  '.blend': 'application/octet-stream', '.glb': 'model/gltf-binary',
};

async function list(prefix = '') {
  const out = new Map();
  let token;
  do {
    const r = await s3.send(new ListObjectsV2Command({ Bucket: BUCKET, Prefix: prefix, ContinuationToken: token }));
    for (const o of r.Contents ?? []) out.set(o.Key, o.Size);
    token = r.IsTruncated ? r.NextContinuationToken : undefined;
  } while (token);
  return out;
}

const mb = (n) => `${(n / 1e6).toFixed(1)} MB`;

async function put(local, key) {
  const st = statSync(local);
  const files = st.isDirectory()
    ? readdirSync(local, { recursive: true }).map(String).filter((f) => statSync(join(local, f)).isFile())
        .map((f) => [join(local, f), key.replace(/\/?$/, '/') + f.split(sep).join('/')])
    : [[local, key.endsWith('/') ? key + basename(local) : key]];
  const have = await list(st.isDirectory() ? key : '');
  let sent = 0;
  for (const [file, k] of files) {
    const size = statSync(file).size;
    if (have.get(k) === size) { console.log(`skip ${k}`); continue; }
    const up = new Upload({
      client: s3, queueSize: 4, partSize: 32 * 1024 * 1024,
      params: { Bucket: BUCKET, Key: k, Body: createReadStream(file), ContentType: TYPES[extname(file).toLowerCase()] ?? 'application/octet-stream' },
    });
    await up.done();
    sent += size;
    console.log(`put  ${k} (${mb(size)})`);
  }
  console.log(`done: ${files.length} files, ${mb(sent)} uploaded`);
}

const [cmd, a, b] = process.argv.slice(2);
if (cmd === 'ls') {
  const objs = await list(a ?? '');
  let total = 0;
  for (const [k, s] of objs) { console.log(`${mb(s).padStart(10)}  ${k}`); total += s; }
  console.log(`${objs.size} objects, ${mb(total)}`);
} else if (cmd === 'put' && a && b) {
  await put(a, b);
} else {
  console.error('usage: node pipeline/r2.mjs ls [prefix] | put <file|dir> <key|prefix/>');
  process.exit(1);
}
