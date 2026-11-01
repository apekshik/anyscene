"""Reference images -> Plan, and Plan + edit -> Plan, with Claude (vision + structured output)."""

import base64
import json
import mimetypes
import os
import urllib.request

import anthropic

from schema import Plan

MODEL = "claude-opus-5-5"

SYSTEM = """You are the production designer for a photoreal Blender scene. From reference images you write a precise,
buildable layout plan for the whole space, in real-world metres.

Rules:
- Use the coordinate system in the schema: origin at the floor's front-left corner seen from the entrance, X right,
  Y into the space, Z up. rot 0 = the object faces -Y (towards the entrance).
- Real places are small and dense. Use true sizes (a bar stool seat is ~0.45 m high, a counter ~0.9-1.0 m, a door
  ~0.9 x 2.1 m). Density sells realism: plan 40-90 objects including clutter.
- Cover the whole space, not just what the image shows. Anything not visible in a reference is source "invented";
  invent it in the same style so a walk-through anywhere in the space looks right. Say what you invented in notes.
- Mark generate=true for objects with character (appliances, tools, crockery, signs with objects, furniture with
  detail). Use generate=false for walls, plain counters, shelves, boxes, paper and other simple geometry.
- Prompts describe one object, its condition and materials. Never name real brands; signage text must be fictional.
- Every object with generate=false gets a material: what its surface looks like in this scene, specific enough to
  generate a tileable texture from (colour, finish, wear), e.g. "nicotine-yellowed beige enamelled steel, scuffed".
- Give a crop for every object visible in reference image 0.
- Reuse assets: identical objects share one asset key (all the red stools are one asset). Repeats cost nothing, so
  build density from repeated assets with varied placement and rotation, and keep distinct designs for heroes.
- Place the reference camera so a render from it would reproduce reference image 0's framing.
- Objects must not overlap each other or the walls (except items resting on furniture, which use z > 0).
- The ground is implicit: never add the floor, street or pavement as an object. Awnings, canopies and signboards are
  thin (h 0.05-0.15 m) and sit at their real height (z). Building facades are thin slabs (d 0.2-0.4 m) at the edge.
- For interior settings the room walls are built from room + openings; do not add walls as objects."""


def _image_block(url: str) -> dict:
    """Send every image inline as a JPEG of at most 2000 px: it keeps requests under the image size limit and works the
    same whether the call goes to Anthropic directly or through OpenRouter."""
    import io

    from PIL import Image

    if url.startswith("http"):
        with urllib.request.urlopen(url, timeout=60) as r:
            raw = r.read()
    elif url.startswith("data:"):
        raw = base64.b64decode(url.split(",", 1)[1])
    else:
        with open(url, "rb") as f:
            raw = f.read()
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img.thumbnail((2000, 2000))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(buf.getvalue()).decode()}}


def strict_schema(model) -> dict:
    """Pydantic's JSON schema in the strict form structured outputs need: every object closed and fully required."""
    schema = model.model_json_schema()

    def walk(node):
        if isinstance(node, dict):
            node.pop("default", None)
            node.pop("title", None)
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


def _client() -> tuple[anthropic.Anthropic, str, dict]:
    """Anthropic directly when ANTHROPIC_API_KEY is set; otherwise OpenRouter's Anthropic-compatible endpoint with
    OPENROUTER_API_KEY. base_url is always explicit, because a stray ANTHROPIC_BASE_URL in the environment (Claude Code
    sets one) would otherwise redirect the SDK."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        extra = {"betas": ["server-side-fallback-2026-07-01", "fast-mode-2026-02-01"], "fallbacks": "default",
                 "speed": "fast"}
        return anthropic.Anthropic(base_url="https://api.anthropic.com"), MODEL, extra
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("set ANTHROPIC_API_KEY or OPENROUTER_API_KEY")
    # Fast mode passes through OpenRouter (checked: usage.speed == "fast", ~2.5x output speed); server-side fallbacks
    # are an Anthropic API feature, so through OpenRouter a refusal is reported as a failure.
    return (anthropic.Anthropic(base_url="https://openrouter.ai/api", auth_token=key, api_key=None),
            os.environ.get("OPENROUTER_MODEL", "anthropic/claude-opus-5.5"),
            {"betas": ["fast-mode-2026-02-01"], "speed": "fast"})


def _call(content: list[dict], effort: str = "high") -> Plan:
    client, model, extra = _client()
    with client.beta.messages.stream(
        model=model,
        max_tokens=64000,
        thinking={"type": "adaptive"},
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": strict_schema(Plan)}},
        system=SYSTEM,
        messages=[{"role": "user", "content": content}],
        **extra,
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"planning declined: {msg.stop_details}")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("plan was cut off (max_tokens)")
    text = next(b.text for b in msg.content if b.type == "text")
    return Plan.model_validate_json(text)


def make_plan(reference_urls: list[str], floor_plan_url: str | None = None, prompt: str = "",
              effort: str = "high") -> Plan:
    content = []
    for i, u in enumerate(reference_urls):
        content += [{"type": "text", "text": f"Reference image {i}:"}, _image_block(u)]
    if floor_plan_url:
        content += [{"type": "text", "text": "Floor plan provided by the user. Follow it for the room shape and where "
                                             "things go; use the reference images for the look and the props:"},
                    _image_block(floor_plan_url)]
    content.append({"type": "text", "text": "Write the plan." + (f"\n\nExtra direction: {prompt}" if prompt else "")})
    return _call(content, effort)


def edit_plan(plan: Plan, edit: str, reference_urls: list[str], effort: str = "high") -> Plan:
    content = []
    for i, u in enumerate(reference_urls):
        content += [{"type": "text", "text": f"Reference image {i}:"}, _image_block(u)]
    content.append({"type": "text", "text": "Current plan:\n" + json.dumps(plan.model_dump(), indent=1)
                    + f"\n\nApply this change and return the full revised plan. Keep everything else as it is.\n"
                      f"Change: {edit}"})
    return _call(content, effort)
