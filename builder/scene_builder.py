"""AnyScene scene builder: one Claude agent builds the whole scene from reference images, the way SKILL.md describes.

    uv run --python 3.13 --with claude-agent-sdk --with anthropic --with pydantic --with pillow \
        python builder/scene_builder.py <reference.png> [...] --work <dir> [--prompt "..."] [--effort medium]

The agent (Claude Code via the Agent SDK, Opus 5.5, effort medium by default, fast mode) works in a fresh workspace holding SKILL.md,
CRAFT.md and the shared tools. On top of its own tools (Bash, Read, Write, Edit...) it gets:
  report(stage, message, image)   a stage event for the live UI (ANYSCENE_STAGE lines, out/events.jsonl)
  critique(stills)                an independent critic: reference vs stills, scores and ranked fixes
Every tool call is also streamed as a short log event (PostToolUse hook). There is no time budget: a Stop hook keeps
the agent working until the deliverables exist and the critic passes, unless three critic rounds in a row bring no
improvement.
"""

import argparse
import asyncio
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import time

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, HookMatcher, ResultMessage,
                              TextBlock, ToolUseBlock, create_sdk_mcp_server, tool)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "endpoint"))
import planner  # noqa: E402  (the critic's Claude client; imported here so fal bundles it with this module)
PREFIX = "ANYSCENE_STAGE "
# fal ends a request at 7200 s; warn the agent, then stop it with time left to package and upload
CAP_WARN_S = 95 * 60
# most critic rounds a build gets; after the last one the builder finishes its deliverables and delivers
MAX_CRITIC_ROUNDS = 8
CAP_STOP_S = 110 * 60
MODEL = "anthropic/claude-opus-5.5"  # through OpenRouter (OPENROUTER_API_KEY)
DIRECT_MODEL = "claude-opus-5-5"  # the same model on the Anthropic API (ANTHROPIC_API_KEY)


def user_env(name):
    if os.environ.get(name):
        return os.environ[name]
    if sys.platform == "win32":
        parts = subprocess.run(["reg", "query", r"HKCU\Environment", "/v", name], capture_output=True, text=True).stdout.split()
        if name in parts:
            return parts[parts.index(name) + 2]
    return None


# ---------------------------------------------------------------- workspace
TOOLKIT_DIRS = ("generate", "pipeline", "camera", "docs")
SKIP = (".png", ".jpg", ".mp4", ".pyc", "spend.jsonl", "r2.mjs", "lan_gallery.py", "_page.mjs")


def toolkit_files():
    """Everything the builder's workspace starts with, as {relative path: text}: SKILL.md, CRAFT.md, the prompt and the
    shared tools. No example scenes. Collected at deploy time so the fal app carries it."""
    files = {"SKILL.md": open(os.path.join(REPO, "SKILL.md"), encoding="utf-8").read(),
             "CRAFT.md": open(os.path.join(HERE, "CRAFT.md"), encoding="utf-8").read(),
             ".builder/PROMPT.md": open(os.path.join(HERE, "PROMPT.md"), encoding="utf-8").read(),
             ".builder/SHOTS.md": open(os.path.join(HERE, "SHOTS.md"), encoding="utf-8").read(),
             "endpoint/refine_blender.py": open(os.path.join(REPO, "endpoint", "refine_blender.py"), encoding="utf-8").read()}
    for d in TOOLKIT_DIRS:
        for root, dirs, names in os.walk(os.path.join(REPO, d)):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for n in names:
                if not n.endswith(SKIP):
                    path = os.path.join(root, n)
                    files[os.path.relpath(path, REPO).replace(os.sep, "/")] = open(path, encoding="utf-8").read()
    return files


def make_workspace(work, refs, prompt, scene, files, dials=None):
    os.makedirs(work, exist_ok=True)
    for rel, text in files.items():
        path = os.path.join(work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        if rel.endswith(".sh"):
            os.chmod(path, 0o755)
    inp = os.path.join(work, "input")
    os.makedirs(inp, exist_ok=True)
    for i, r in enumerate(refs):
        shutil.copy(r, os.path.join(inp, f"reference_{i + 1}.png"))
    with open(os.path.join(inp, "dials.json"), "w", encoding="utf-8") as f:
        json.dump(dials or {}, f, indent=1)
    with open(os.path.join(inp, "brief.md"), "w", encoding="utf-8") as f:
        f.write(prompt or "(no prompt: match the reference)\n")
    for d in (f"scenes/{scene}/scripts", "out/stills", "out/critique"):
        os.makedirs(os.path.join(work, d), exist_ok=True)
    open(os.path.join(work, "generate", "spend.jsonl"), "a").close()


# ---------------------------------------------------------------- critic
CRITIC = """You review 3D sets for a service that turns reference images into production-ready Blender sets. The
FIRST image is the customer's reference; the others are renders of the set built from it. The reference is a starting
point, not a target to copy: the set must clearly be the same KIND of place (its world, era, contents, materials and
level of detail), but the camera views, the exact lighting, the grade and the arrangement are the builder's own
choices and must NOT be marked down for differing from the reference.

The bar is a production-ready starting point: a set a studio would accept as the base an artist then refines and
art-directs. Judge it as a whole, from normal viewing distance. Do NOT nitpick: no points off for framing that
differs from the reference, light that differs from the reference's light, a case that could hold more pastries, a
surface that is a little CG on close inspection, or anything an artist would tweak in ten minutes.

Score each category 1-10 (7 = a solid, usable production set; 9 = exceptional):
- layout: a believable space of the reference's kind, sensibly arranged;
- props: the reference's notable objects are there and recognisable; nothing broken, blobby or melted;
- screens_signage: signs, screens and labels read cleanly; no real brands; no garbled text on hero signage;
- materials: surfaces read as real materials with fitting wear; nothing untextured or flat grey;
- lighting: designed, motivated light that suits the place; not flat, muddy or blown out;
- atmosphere: depth and a deliberate grade; haze where it helps;
- plausibility: nothing floating, intersecting, impossible or stacked wrongly;
- composition: the shots are well composed (any angles; they don't need to match the reference).

Then list at most FIVE fixes, most damaging first: only problems that would stop a studio from using the set as a
base (something broken, missing, wrong-world, unreadable or ugly at normal viewing distance). If the set is already a
good base, say so and list fewer or none. Pass when the set is a good production base: no category below 6 and an
average of 7 or more."""


def critic_schema():
    from pydantic import BaseModel, Field

    class Scores(BaseModel):
        layout: int
        props: int
        screens_signage: int
        materials: int
        lighting: int
        atmosphere: int
        plausibility: int
        composition: int

    class Critique(BaseModel):
        scores: Scores
        fixes: list[str] = Field(description="Most damaging first.")
        summary: str
    return Critique


def _jpeg(path, size=1600):
    from PIL import Image
    img = Image.open(path).convert("RGB")
    img.thumbnail((size, size))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return base64.standard_b64encode(buf.getvalue()).decode()


def run_critic(refs, stills):
    Critique = critic_schema()
    client, model, extra = planner._client()
    content = []
    for p in list(refs) + list(stills):
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _jpeg(p)}})
    content.append({"type": "text", "text": CRITIC})
    with client.beta.messages.stream(model=model, max_tokens=16000, thinking={"type": "adaptive"},
                                     output_config={"effort": "high", "format": {"type": "json_schema",
                                                                                 "schema": planner.strict_schema(Critique)}},
                                     messages=[{"role": "user", "content": content}], **extra) as s:
        msg = s.get_final_message()
    c = Critique.model_validate_json(next(b.text for b in msg.content if b.type == "text"))
    d = c.model_dump()
    v = list(d["scores"].values())
    d["passed"] = min(v) >= 6 and sum(v) / len(v) >= 7  # a good production base, not a copy of the reference
    return d


# ---------------------------------------------------------------- run
class SceneBuilder:
    # what a subclass changes for another job on the same workspace (see shots.py)
    PROMPT_FILE = "PROMPT.md"  # under .builder/
    ASK = "Build the scene from the reference in input/. Start by reading SKILL.md."

    def __init__(self, work, refs, scene, uploader=None, emit=None, effort="medium", out_rel="out"):
        self.effort = effort
        self.work, self.refs, self.scene = work, refs, scene
        self.out = os.path.join(work, out_rel)
        os.makedirs(self.out, exist_ok=True)
        self.t0 = time.time()
        self.upload = uploader or (lambda p: p)
        self.events = open(os.path.join(self.out, "events.jsonl"), "a", encoding="utf-8")
        self.log = open(os.path.join(self.out, "builder.log"), "a", encoding="utf-8")
        self.critiques = []
        self.milestones = []  # every milestone so far, repeated in each heartbeat so a late watcher can backfill
        self.working = None  # (description, started) of the tool call in progress
        self.cap_warned = False
        self.capped = False  # stopped at the platform's 2-hour limit: let it end without a pass
        self.warned = False
        self._emit_hook = emit

    # elapsed / remaining
    def elapsed(self):
        return time.time() - self.t0

    def emit(self, stage, status="running", message="", image=None, **extra):
        ev = {"t": round(self.elapsed(), 1), "stage": stage, "status": status, "message": message, **extra}
        if image:
            path = image if os.path.isabs(image) else os.path.join(self.work, image)
            if os.path.exists(path):
                ev["preview_url"] = self.upload(path)
        if stage not in ("log", "thinking", "heartbeat", "received", "error", "critique", "done", "packaged"):
            self.milestones.append({k: ev[k] for k in ("t", "stage", "status", "message", "preview_url") if k in ev})
        print(PREFIX + json.dumps(ev), flush=True)
        self.events.write(json.dumps(ev) + "\n")
        self.events.flush()
        if self._emit_hook:
            self._emit_hook(ev)

    def note(self, text):
        self.log.write(f"[{self.elapsed() / 60:6.1f}m] {text}\n")
        self.log.flush()

    # ---- MCP tools
    def tools(self):
        d = self

        @tool("report", "Post a stage event to the customer's live log, optionally with a rendered image.",
              {"stage": str, "message": str, "image": str})
        async def report(args):
            d.emit(args["stage"], "running", args.get("message", ""), args.get("image") or None)
            return {"content": [{"type": "text", "text": "reported"}]}

        @tool("critique", "Independent critic: compares the reference with your stills (paths relative to the workspace "
                          "or absolute). Returns scores 1-10 per category, up to five fixes that matter, and "
                          "whether it passes (no category below 6, average 7+).",
              {"type": "object", "properties": {"stills": {"type": "array", "items": {"type": "string"}}},
               "required": ["stills"]})
        async def critique(args):
            if len(d.critiques) >= MAX_CRITIC_ROUNDS:
                return {"content": [{"type": "text", "text": (
                    f"The critic has had its {MAX_CRITIC_ROUNDS} rounds; no more reviews. Stop iterating on the look: "
                    "finish every remaining deliverable (previews, shots.json, panoramas, scene.glb, dials.json, "
                    "NOTES.md, the packed scene.blend) and deliver.")}]}
            paths = [p if os.path.isabs(p) else os.path.join(d.work, p) for p in args["stills"]]
            missing = [p for p in paths if not os.path.exists(p)]
            if missing:
                return {"content": [{"type": "text", "text": f"missing: {missing}"}], "is_error": True}
            d.emit("critique", "running", f"critic is looking at {len(paths)} stills")
            res = await asyncio.to_thread(run_critic, d.refs, paths[:6])
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

    # ---- hooks
    @staticmethod
    def describe(name, ti, work):
        if name == "Bash":
            return ti.get("description") or ti.get("command", "")[:120]
        if name in ("Write", "Edit"):
            return f"{'writing' if name == 'Write' else 'editing'} {os.path.relpath(ti.get('file_path', ''), work)}"
        if name == "Read":
            p = ti.get("file_path", "")
            return f"{'looking at' if p.lower().endswith(('.png', '.jpg', '.jpeg')) else 'reading'} {os.path.relpath(p, work)}"
        return name

    async def pre_tool(self, inp, tool_use_id, ctx):
        self.working = (self.describe(inp.get("tool_name", ""), inp.get("tool_input") or {}, self.work), time.time())
        if self.elapsed() > CAP_WARN_S and not self.cap_warned:
            self.cap_warned = True
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": (
                "The platform ends this request at 120 minutes and the build is now past 95. Before anything else, make "
                "sure out/ holds your best current versions of every deliverable (scene.blend, stills, previews, "
                "shots.json, dials.json, plan.json), then keep improving.")}}
        return {}

    async def heartbeat(self):
        """Every 20 s: what is running and for how long, plus the milestones so far. Long renders otherwise look idle,
        and a page that attaches late (fal's status call returns only the recent log) can fill in its schedule."""
        while True:
            await asyncio.sleep(20)
            w = self.working
            self.emit("heartbeat", "running", f"{self.elapsed() / 60:.0f} min in",
                      working=w[0] if w else None, working_s=round(time.time() - w[1]) if w else None,
                      milestones=self.milestones[-20:], critique_rounds=len(self.critiques))

    async def post_tool(self, inp, tool_use_id, ctx):
        self.working = None
        name = inp.get("tool_name", "")
        ti = inp.get("tool_input") or {}
        quiet = name.startswith("mcp__scene__") or name in ("ToolSearch", "TodoWrite")
        msg = None if quiet else self.describe(name, ti, self.work)
        if msg:
            # an image the agent opens is shown to the customer too (its test renders, sheets, plans), so the live view
            # follows what it is looking at; the customer's own reference is left out
            p = ti.get("file_path", "") if name == "Read" else ""
            image = p if p.lower().endswith((".png", ".jpg", ".jpeg")) and "/input/" not in p.replace("\\", "/") else None
            self.emit("log", "running", msg, image if image and os.path.exists(image) else None, tool=name)
        self.note(f"{name}: {json.dumps(ti)[:400]}")
        return {}

    def missing(self):
        out = os.path.join(self.work, "out")
        miss = []
        stills = [f for f in os.listdir(os.path.join(out, "stills")) if f.lower().endswith(".png")]
        if len(stills) < 3:
            miss.append(f"out/stills has {len(stills)} stills (need 3+)")
        pdir = os.path.join(out, "previews")
        previews = [f for f in os.listdir(pdir) if f.lower().endswith(".png")] if os.path.isdir(pdir) else []
        if len(previews) < 8:
            miss.append(f"out/previews has {len(previews)} previews (need 8+)")
        for f in ("scene.blend", "shots.json", "plan.json", "dials.json"):
            if not os.path.exists(os.path.join(out, f)):
                miss.append(f"out/{f}")
        if not self.critiques:
            miss.append("no critique yet")
        elif not self.critiques[-1]["passed"] and len(self.critiques) < MAX_CRITIC_ROUNDS:
            miss.append("the last critique did not pass")
        return miss

    def stalled(self):
        """Three critic rounds in a row without beating the best total so far: the builder is going in circles."""
        totals = [sum(c["scores"].values()) for c in self.critiques]
        return len(totals) >= 4 and max(totals[-3:]) <= max(totals[:-3])

    async def on_stop(self, inp, tool_use_id, ctx):
        miss = self.missing()
        if miss and not self.stalled() and not self.capped:
            self.note(f"STOP blocked: {miss}")
            return {"decision": "block", "reason": "Not done: " + "; ".join(miss) + ". Keep going."}
        return {}

    def format_prompt(self, text):
        return text.replace("{scene}", self.scene)

    async def run(self, env):
        prompt = open(os.path.join(self.work, ".builder", self.PROMPT_FILE), encoding="utf-8").read()
        prompt = self.format_prompt(prompt)
        server = create_sdk_mcp_server("scene", tools=self.tools())
        beat = asyncio.create_task(self.heartbeat())
        self.emit("received", "running", "scene builder starting")
        result, session_id, attempt = None, None, 0
        ask = self.ASK
        while True:
            opts = ClaudeAgentOptions(
                model=env.get("ANTHROPIC_MODEL") or MODEL, effort=self.effort, permission_mode="bypassPermissions",
                cwd=self.work,
                system_prompt={"type": "preset", "preset": "claude_code", "append": prompt},
                mcp_servers={"scene": server}, setting_sources=[], settings='{"fastMode": true}',
                hooks={"PreToolUse": [HookMatcher(hooks=[self.pre_tool])], "PostToolUse": [HookMatcher(hooks=[self.post_tool])],
                       "Stop": [HookMatcher(hooks=[self.on_stop])]},
                # tool results come back to us as single JSON lines; a full-size render read as an image is several
                # MB, and the default 1 MB buffer kills the session
                max_buffer_size=256 * 1024 * 1024, resume=session_id,
                env=env, stderr=lambda l: self.note("STDERR " + l[:300]))
            try:
                async with ClaudeSDKClient(opts) as client:
                    async def cap_guard():
                        # fal kills the request at 2 h with nothing returned; stop the agent first so the endpoint can
                        # still package and return what is in out/
                        while self.elapsed() < CAP_STOP_S:
                            await asyncio.sleep(15)
                        self.capped = True
                        self.emit("error", "running", "stopping the builder before the platform's 2-hour limit; "
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
            except Exception as e:  # the session broke (SDK or CLI error): pick the same session back up
                import traceback
                if self.capped:
                    break
                attempt += 1
                self.note("SESSION ERROR " + traceback.format_exc()[-3000:])
                self.emit("error", "running", f"agent session error ({type(e).__name__}: {str(e)[:200]}); "
                          f"{'resuming' if attempt <= 3 and session_id else 'giving up'}")
                if attempt > 3 or not session_id:
                    raise
                ask = ("The previous turn was cut off by a harness error, not by you. Continue the build from where "
                       "you were; check the state of the workspace first.")
        beat.cancel()
        cost = getattr(result, "total_cost_usd", None)
        self.emit("done", "done", f"scene builder finished after {self.elapsed() / 60:.0f} min"
                  + (f", agent cost ${cost:.2f}" if cost else ""), missing=self.missing(),
                  critiques=len(self.critiques))
        return result


def agent_env():
    """The agent's environment. Keys come only from the environment (fal secrets on a worker): OPENROUTER_API_KEY
    (Claude through OpenRouter, the default) or, without it, ANTHROPIC_API_KEY (the Anthropic API directly). FAL_KEY is
    passed through for the generate/ tools. ANTHROPIC_MODEL in the result is the model id for that provider."""
    key = user_env("OPENROUTER_API_KEY")
    direct = None if key else user_env("ANTHROPIC_API_KEY")
    if not key and not direct:
        raise RuntimeError("set OPENROUTER_API_KEY or ANTHROPIC_API_KEY (a fal secret on the app)")
    fal = user_env("FAL_KEY") or os.environ.get("FAL_KEY") or ""
    common = {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "BASH_MAX_TIMEOUT_MS": "600000", "FAL_KEY": fal,
              "IS_SANDBOX": "1"}  # the fal worker runs as root in its own container; Claude Code needs this to skip prompts
    if direct:
        os.environ["ANTHROPIC_API_KEY"] = direct  # the critic (planner._client) then talks to Anthropic directly
        return {**common, "ANTHROPIC_BASE_URL": "https://api.anthropic.com", "ANTHROPIC_API_KEY": direct,
                "ANTHROPIC_MODEL": DIRECT_MODEL}
    env = {**common, "ANTHROPIC_BASE_URL": "https://openrouter.ai/api", "ANTHROPIC_AUTH_TOKEN": key, "ANTHROPIC_API_KEY": "",
           "ANTHROPIC_MODEL": MODEL, "ANTHROPIC_DEFAULT_OPUS_MODEL": MODEL,
           "ANTHROPIC_DEFAULT_SONNET_MODEL": "anthropic/claude-sonnet-5.5",
           "ANTHROPIC_DEFAULT_HAIKU_MODEL": "anthropic/claude-haiku-5.5", "OPENROUTER_API_KEY": key}
    os.environ["OPENROUTER_API_KEY"] = key  # the critic (planner._client) reads it
    os.environ.pop("ANTHROPIC_API_KEY", None)
    return env


def main():
    p = argparse.ArgumentParser()
    p.add_argument("refs", nargs="+")
    p.add_argument("--work", required=True)
    p.add_argument("--prompt", default="")
    p.add_argument("--scene", default="scene")
    p.add_argument("--effort", default="medium")
    a = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    work = os.path.abspath(a.work)
    if not os.path.exists(os.path.join(work, "SKILL.md")):
        make_workspace(work, a.refs, a.prompt, a.scene, toolkit_files())
    refs = sorted(os.path.join(work, "input", f) for f in os.listdir(os.path.join(work, "input")) if f.startswith("reference_"))
    d = SceneBuilder(work, refs, a.scene, effort=a.effort)
    asyncio.run(d.run(agent_env()))


if __name__ == "__main__":
    main()
