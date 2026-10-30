// Search the fal model catalog: node generate/models.mjs <query>...
const KEY = process.env.FAL_KEY || process.env.FAL_API_KEY;
for (const q of process.argv.slice(2)) {
  const r = await fetch(`https://api.fal.ai/v1/models?q=${encodeURIComponent(q)}&limit=40`, { headers: { authorization: `Key ${KEY}` } });
  const j = await r.json();
  console.log(`## ${q} (${r.status})`);
  for (const m of j.models ?? []) console.log(m.endpoint_id, '|', m.metadata?.display_name, '|', m.metadata?.status, '|', m.metadata?.updated_at?.slice(0, 10));
}
