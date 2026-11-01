"""Copy the code AnyScene shares with AnyShot from a sibling AnyShot checkout (github.com/apekshik/anyshot).

    python scripts/sync_from_anyshot.py [path/to/anyshot]      (default: ../anyshot next to this repo)

AnyShot is the home of these files; edit them there, then run this. Each copy gets a one-line header naming its source.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# anyscene path: anyshot path
FILES = {
    "builder/blender_gpu.py": "agent/blender_gpu.py",
    "camera/camrig.py": "camera/camrig.py",
    "camera/shoot.py": "camera/shoot.py",
    "camera/README.md": "camera/README.md",
    "farm/app.py": "farm/app.py",
    "pipeline/env.sh": "pipeline/env.sh",
    "pipeline/gpu_run.sh": "pipeline/gpu_run.sh",
}


def header(src_rel):
    text = f"synced from github.com/apekshik/anyshot {src_rel}"
    return f"<!-- {text} -->" if src_rel.endswith(".md") else f"# {text}"


def main():
    src_root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "..", "anyshot"))
    if not os.path.exists(os.path.join(src_root, "agent", "director.py")):
        sys.exit(f"not an AnyShot checkout: {src_root}")
    for dst_rel, src_rel in FILES.items():
        lines = open(os.path.join(src_root, src_rel), encoding="utf-8").read().splitlines(keepends=True)
        at = 1 if lines and lines[0].startswith("#!") else 0  # keep a shebang first
        lines.insert(at, header(src_rel) + "\n")
        dst = os.path.join(REPO, dst_rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        old = open(dst, encoding="utf-8").read() if os.path.exists(dst) else None
        new = "".join(lines)
        if new != old:
            with open(dst, "w", encoding="utf-8", newline="\n") as f:
                f.write(new)
        print(f"{'updated' if new != old else 'same   '} {dst_rel}  <-  {src_rel}")


if __name__ == "__main__":
    main()
