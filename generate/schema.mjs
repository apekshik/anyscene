// Print input schema + price for fal endpoints.
const KEY = process.env.FAL_KEY || process.env.FAL_API_KEY;
const ids = process.argv.slice(2);
const pr = await fetch(`https://api.fal.ai/v1/models/pricing?${ids.map((i) => 'endpoint_id=' + encodeURIComponent(i)).join('&')}`, { headers: { authorization: `Key ${KEY}` } }).then((r) => r.json());
for (const p of pr.prices ?? []) console.log('PRICE', p.endpoint_id, p.unit_price, p.unit, p.currency);
for (const id of ids) {
  const j = await fetch(`https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=${encodeURIComponent(id)}`).then((r) => r.json());
  const schemas = j.components?.schemas ?? {};
  const inName = Object.keys(schemas).find((k) => /Input$/.test(k));
  const s = schemas[inName];
  console.log(`\n## ${id} (${inName}) required=${JSON.stringify(s?.required)}`);
  for (const [k, v] of Object.entries(s?.properties ?? {})) {
    const en = v.enum ?? v.anyOf?.flatMap((x) => x.enum ?? []) ?? (v.allOf?.[0]?.$ref ? schemas[v.allOf[0].$ref.split('/').pop()]?.enum : undefined);
    console.log(`  ${k}: ${v.type ?? ''} default=${JSON.stringify(v.default)}${en?.length ? ' enum=' + JSON.stringify(en) : ''} — ${(v.description ?? '').slice(0, 110)}`);
  }
}
