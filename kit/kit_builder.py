"""AnyKit: one Claude agent builds a cohesive kit of static 3D props from style reference image(s).

Same machinery as the scene builder (builder/scene_builder.py): an Agent SDK session (Opus 5.5, fast mode, OpenRouter),
report/critique MCP tools, PreToolUse/PostToolUse/Stop hooks, a heartbeat, the 2-hour cap guard and resume on session
errors. What differs: the workspace (kit prompt, KIT.md, kit tools), the critic's rubric (kit cohesion, not a set), and
what "done" means (out/kit.json, per-item GLB + LOD1 + thumbnail, out/kit.blend, out/renders/lineup.png, a passing
critique).

    uv run --python 3.13 --with claude-agent-sdk --with anthropic --with pydantic --with pillow \
        python kit/kit_builder.py <reference.png> [...] --work <dir> [--prompt "..."] [--items "a,b,c"]
"""

import argparse
import asyncio
import json
import os
import sys

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, HookMatcher, ResultMessage,
                              TextBlock, create_sdk_mcp_server, tool)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "builder"))
sys.path.insert(0, os.path.join(REPO, "endpoint"))
import planner  # noqa: E402  (the critic's Claude client; module level so fal bundles it)
import scene_builder  # noqa: E402
from scene_builder import CAP_STOP_S, CAP_WARN_S, MAX_CRITIC_ROUNDS, MODEL, PREFIX, agent_env, user_env  # noqa: E402,F401

DIALS = ("count", "variety", "detail", "wear", "wetness", "warmth", "look")


# ---------------------------------------------------------------- workspace
def toolkit_files():
    """The scene builder's toolkit (SKILL.md, generate/, pipeline/, camera/, docs/) with the kit's prompt, KIT.md and
    kit tools on top. Read at deploy time so the fal app carries it."""
    files = {k: v for k, v in scene_builder.toolkit_files().items() if not k.startswith(".builder/")}
    files[".builder/PROMPT.md"] = open(os.path.join(HERE, "PROMPT.md"), encoding="utf-8").read()
    files["KIT.md"] = open(os.path.join(HERE, "KIT.md"), encoding="utf-8").read()
    files["kit/gen.mjs"] = open(os.path.join(HERE, "gen.mjs"), encoding="utf-8").read()
    for n in sorted(os.listdir(os.path.join(HERE, "tools"))):
        if n.endswith(".py"):
            files[f"kit/tools/{n}"] = open(os.path.join(HERE, "tools", n), encoding="utf-8").read()
    return files


def make_workspace(work, refs, prompt, files, dials=None, items=None, ref_urls=None):
    scene_builder.make_workspace(work, refs, prompt, "kit", files, dials)
    inp = os.path.join(work, "input")
    with open(os.path.join(inp, "items.json"), "w", encoding="utf-8") as f:
        json.dump(items or [], f, indent=1)
    with open(os.path.join(inp, "style_urls.json"), "w", encoding="utf-8") as f:
        json.dump(ref_urls or [], f, indent=1)
    for d in ("out/items", "out/renders/thumbs", "refs/kit"):
        os.makedirs(os.path.join(work, d), exist_ok=True)
    # the scene builder's stills dir is not part of a kit
    try:
        os.rmdir(os.path.join(work, "out", "stills"))
    except OSError:
        pass


# ---------------------------------------------------------------- critic
CRITIC = """You review 3D prop kits for a service that turns style reference images into production-ready asset kits.
The first {n_refs} image(s) are the customer's STYLE REFERENCE. They asked for: {brief}

The remaining images are the delivered kit: first a lineup render (every item side by side on a neutral ground, with
a scale bar; its label under each item), then per-item thumbnails. The kit's manifest:
{manifest}

The reference is a starting point for the world, not a target to copy: the kit must clearly belong to the same world
(era, materials, palette, design language), but which items were chosen, their exact designs and the presentation
are the builder's own choices and must NOT be marked down for differing from the reference.

The bar is a production-ready base: a kit a studio would accept as the starting point its artists then refine. Judge
it as a whole, from normal viewing distance. Do NOT nitpick: no points off for a creative choice that differs from
the reference, a surface that is a little CG on close inspection, or anything an artist would tweak in ten minutes.

Score each category 1-10 (7 = a solid, usable production kit; 9 = exceptional):
- cohesion: the items read as one set: shared palette, material language, era, wear and level of detail;
- reference_fidelity: the kit belongs in the reference's world;
- brief: the items are what the customer asked for (prompt, item list, count), nothing off-topic;
- mesh_quality: clean recognisable shapes; nothing broken, blobby or melted;
- texture_quality: believable textured surfaces; nothing untextured, smeared or flat grey;
- assembly: parts that belong together are physically connected and seated: cords and cables plugged in at
  both ends, handsets on their cradles, lamp heads on their arms, lids on their hinges, nothing hovering or
  intersecting;
- scale: each item's real-world size (manifest dims, scale bar) is right, alone and relative to the others;
- labels: no real brands; no garbled text on hero labels.

Then list at most FIVE fixes, most damaging first: only problems that would stop a studio from using the kit as a
base (an item broken, melted or with disconnected parts, garbled hero labels, wrong world, untextured, badly wrong
scale). If the kit is already a good base, say so and list fewer or none. Pass when the kit is a good production
base: no category below 6 and an average of 7 or more."""


def critic_schema():
    from pydantic import BaseModel, Field

    class Scores(BaseModel):
        cohesion: int
        reference_fidelity: int
        brief: int
        mesh_quality: int
        texture_quality: int
        assembly: int
        scale: int
        labels: int

    class Critique(BaseModel):
        scores: Scores
        fixes: list[str] = Field(description="At most five, most damaging first; may be empty.")
        summary: str
    return Critique


def manifest_text(work):
    try:
        kit = json.load(open(os.path.join(work, "out", "kit.json"), encoding="utf-8"))
    except Exception:
        return "(out/kit.json not written yet)"
    rows = []
    for it in kit.get("items", []):
        d = it.get("dims_m") or []
        dims = " x ".join(f"{v * 100:.0f}" for v in d) + " cm (w x d x h)" if len(d) == 3 else "?"
        rows.append(f"- {it.get('id')}: {it.get('label', '')}, {dims}, {it.get('tris', '?')} tris")
    return "\n".join(rows) or "(no items)"


def run_critic(refs, images, brief, manifest):
    Critique = critic_schema()
    client, model, extra = planner._client()
    content = []
    for p in list(refs) + list(images):
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": scene_builder._jpeg(p)}})
    content.append({"type": "text", "text": CRITIC.format(n_refs=len(refs), brief=brief, manifest=manifest)})
    with client.beta.messages.stream(model=model, max_tokens=16000, thinking={"type": "adaptive"},
                                     output_config={"effort": "high", "format": {"type": "json_schema",
                                                                                 "schema": planner.strict_schema(Critique)}},
                                     messages=[{"role": "user", "content": content}], **extra) as s:
        msg = s.get_final_message()
    c = Critique.model_validate_json(next(b.text for b in msg.content if b.type == "text"))
    d = c.model_dump()
    v = list(d["scores"].values())
    d["passed"] = min(v) >= 6 and sum(v) / len(v) >= 7  # a good production base, same rule as the scene critic
    return d


# ---------------------------------------------------------------- run
class KitBuilder(scene_builder.SceneBuilder):
    """The scene builder's session, hooks, heartbeat and cap guard, with the kit's tools, critic and definition of done."""

    ASK = "Build the kit from the style reference in input/. Start by reading KIT.md, then SKILL.md steps 3-6."

    def __init__(self, work, refs, uploader=None, emit=None, effort="medium"):
        super().__init__(work, refs, "kit", uploader=uploader, emit=emit, effort=effort)

    def brief(self):
        txt = open(os.path.join(self.work, "input", "brief.md"), encoding="utf-8").read().strip()
        items = json.load(open(os.path.join(self.work, "input", "items.json"), encoding="utf-8"))
        dials = json.load(open(os.path.join(self.work, "input", "dials.json"), encoding="utf-8"))
        return (txt + (f"\nItems requested: {', '.join(items)}" if items else "")
                + (f"\nDials: {json.dumps(dials)}" if dials else ""))

    def tools(self):
        d = self

        @tool("report", "Post a stage event to the customer's live log, optionally with a rendered image.",
              {"stage": str, "message": str, "image": str})
        async def report(args):
            d.emit(args["stage"], "running", args.get("message", ""), args.get("image") or None)
            return {"content": [{"type": "text", "text": "reported"}]}

        @tool("critique", "Independent kit critic: compares the style reference with your lineup and thumbnails "
                          "(paths relative to the workspace or absolute; the lineup FIRST, then up to 10 thumbnails). "
                          "It also reads out/kit.json for dims. Returns scores 1-10 per category, up to five fixes that "
                          "matter, and whether it passes (no category below 6, average 7+). At most "
                          f"{MAX_CRITIC_ROUNDS} rounds.",
              {"type": "object", "properties": {"images": {"type": "array", "items": {"type": "string"}}},
               "required": ["images"]})
        async def critique(args):
            if len(d.critiques) >= MAX_CRITIC_ROUNDS:
                return {"content": [{"type": "text", "text": (
                    f"The critic has had its {MAX_CRITIC_ROUNDS} rounds; no more reviews. Stop iterating on the look: "
                    "finish every remaining deliverable (items/<id>/<id>.glb and _lod1.glb, renders/lineup.png, "
                    "renders/thumbs/, kit.json, kit.blend, dials.json, NOTES.md) and deliver.")}]}
            paths = [p if os.path.isabs(p) else os.path.join(d.work, p) for p in args["images"]]
            missing = [p for p in paths if not os.path.exists(p)]
            if missing:
                return {"content": [{"type": "text", "text": f"missing: {missing}"}], "is_error": True}
            d.emit("critique", "running", f"critic is looking at the lineup and {len(paths) - 1} item renders")
            res = await asyncio.to_thread(run_critic, d.refs, paths[:11], d.brief(), manifest_text(d.work))
            res["round"] = len(d.critiques) + 1
            res["stills"] = paths
            d.critiques.append(res)
            json.dump(res, open(os.path.join(d.work, "out", "critique", f"round_{res['round']}.json"), "w"), indent=1)
            sc = res["scores"]
            d.emit("critique", "done" if res["passed"] else "running",
                   f"round {res['round']}: {'PASS' if res['passed'] else 'not yet'} - "
                   + ", ".join(f"{k} {v}" for k, v in sc.items()), paths[0], critique=res)
            return {"content": [{"type": "text", "text": json.dumps(res, indent=1)}]}

        return [report, critique]

    async def pre_tool(self, inp, tool_use_id, ctx):
        import time
        self.working = (self.describe(inp.get("tool_name", ""), inp.get("tool_input") or {}, self.work), time.time())
        if self.elapsed() > CAP_WARN_S and not self.cap_warned:
            self.cap_warned = True
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": (
                "The platform ends this request at 120 minutes and the kit is now past 95. Before anything else, make "
                "sure out/ holds your best current version of every deliverable (kit.json, items/<id>/<id>.glb and "
                "_lod1.glb, renders/lineup.png, renders/thumbs/, kit.blend, dials.json), then keep improving.")}}
        return {}

    def kit(self):
        try:
            return json.load(open(os.path.join(self.work, "out", "kit.json"), encoding="utf-8"))
        except Exception:
            return None

    def missing(self):
        out = os.path.join(self.work, "out")
        miss = []
        kit = self.kit()
        if not kit or not kit.get("items"):
            miss.append("out/kit.json with an items list")
        else:
            for it in kit["items"]:
                i = it.get("id", "?")
                for rel in (f"items/{i}/{i}.glb", f"items/{i}/{i}_lod1.glb", f"renders/thumbs/{i}.png"):
                    if not os.path.exists(os.path.join(out, rel)):
                        miss.append(f"out/{rel}")
                for k in ("label", "dims_m", "tris", "generator", "why"):
                    if k not in it:
                        miss.append(f"kit.json item {i} has no {k}")
        for f in ("kit.blend", "renders/lineup.png", "dials.json"):
            if not os.path.exists(os.path.join(out, f)):
                miss.append(f"out/{f}")
        if not self.critiques:
            miss.append("no critique yet")
        elif not self.critiques[-1]["passed"] and len(self.critiques) < MAX_CRITIC_ROUNDS:
            miss.append("the last critique did not pass")
        return miss

    async def run(self, env):
        prompt = open(os.path.join(self.work, ".builder", "PROMPT.md"), encoding="utf-8").read()
        server = create_sdk_mcp_server("scene", tools=self.tools())  # "scene": the base post_tool quiets mcp__scene__*
        beat = asyncio.create_task(self.heartbeat())
        self.emit("received", "running", "kit builder starting")
        result, session_id, attempt = None, None, 0
        ask = self.ASK
        while True:
            opts = ClaudeAgentOptions(
                model=env.get("ANTHROPIC_MODEL") or MODEL, effort=self.effort, permission_mode="bypassPermissions",
                cwd=self.work,
                system_prompt={"type": "preset", "preset": "claude_code", "append": prompt},
                mcp_servers={"scene": server}, setting_sources=[], settings='{"fastMode": true}',
                hooks={"PreToolUse": [HookMatcher(hooks=[self.pre_tool])],
                       "PostToolUse": [HookMatcher(hooks=[self.post_tool])],
                       "Stop": [HookMatcher(hooks=[self.on_stop])]},
                max_buffer_size=256 * 1024 * 1024, resume=session_id,
                env=env, stderr=lambda l: self.note("STDERR " + l[:300]))
            try:
                async with ClaudeSDKClient(opts) as client:
                    async def cap_guard():
                        while self.elapsed() < CAP_STOP_S:
                            await asyncio.sleep(15)
                        self.capped = True
                        self.emit("error", "running", "stopping the kit builder before the platform's 2-hour limit; "
                                  "packaging what it has")
                        await client.interrupt()
                    guard = asyncio.create_task(cap_guard())
                    try:
                        await client.query(ask)
                        async for m in client.receive_response():
                            session_id = getattr(m, "session_id", None) \
                                or (getattr(m, "data", None) or {}).get("session_id") or session_id
                            if isinstance(m, AssistantMessage):
                                for b in m.content:
                                    if isinstance(b, TextBlock) and b.text.strip():
                                        self.note("SAY " + b.text.strip()[:2000])
                                        self.emit("thinking", "running", b.text.strip()[:400])
                            elif isinstance(m, ResultMessage):
                                result = m
                    finally:
                        guard.cancel()
                break
            except Exception as e:
                import traceback
                if self.capped:
                    break
                attempt += 1
                self.note("SESSION ERROR " + traceback.format_exc()[-3000:])
                self.emit("error", "running", f"agent session error ({type(e).__name__}: {str(e)[:200]}); "
                          f"{'resuming' if attempt <= 3 and session_id else 'giving up'}")
                if attempt > 3 or not session_id:
                    raise
                ask = ("The previous turn was cut off by a harness error, not by you. Continue the kit from where "
                       "you were; check the state of the workspace first.")
        beat.cancel()
        cost = getattr(result, "total_cost_usd", None)
        self.emit("done", "done", f"kit builder finished after {self.elapsed() / 60:.0f} min"
                  + (f", agent cost ${cost:.2f}" if cost else ""), missing=self.missing(),
                  critiques=len(self.critiques))
        return result


def generation_spend(work):
    try:
        rows = [json.loads(l) for l in open(os.path.join(work, "generate", "spend.jsonl"), encoding="utf-8") if l.strip()]
    except OSError:
        return 0.0
    return round(sum(r.get("est_usd", 0) for r in rows), 2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("refs", nargs="+")
    p.add_argument("--work", required=True)
    p.add_argument("--prompt", default="")
    p.add_argument("--items", default="")
    p.add_argument("--effort", default="medium")
    a = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    work = os.path.abspath(a.work)
    if not os.path.exists(os.path.join(work, "KIT.md")):
        make_workspace(work, a.refs, a.prompt, toolkit_files(), items=[s for s in a.items.split(",") if s])
    refs = sorted(os.path.join(work, "input", f) for f in os.listdir(os.path.join(work, "input")) if f.startswith("reference_")
                  and f.endswith(".png"))
    asyncio.run(KitBuilder(work, refs, effort=a.effort).run(agent_env()))


if __name__ == "__main__":
    main()
