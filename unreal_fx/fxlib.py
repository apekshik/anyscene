"""Thin synchronous wrapper over Epic's experimental NiagaraToolsets (unreal.ToolsetRegistry.execute_tool), used by
fx_pack.py to author the AnySceneFX templates headlessly (UnrealEditor-Cmd -run=pythonscript)."""
import json

import unreal

TS = "NiagaraToolsets.NiagaraToolset_System"
LOG = []


def call(tool, args, toolset=TS, check=True):
    unreal.log("FXCALL " + tool + " " + json.dumps(args)[:200])
    r = unreal.ToolsetRegistry.execute_tool(toolset, tool, json.dumps(args))
    if not r.get_editor_property("is_complete"):
        LOG.append(f"{tool} not complete synchronously")
    err = r.get_editor_property("error")
    if err:
        LOG.append(f"{tool} ERROR {err}")
        if check:
            raise RuntimeError(f"{tool}: {err}\nargs={json.dumps(args)[:1500]}")
        return None
    v = r.get_value_as_json_string()
    try:
        while isinstance(v, str) and v[:1] in "{[\"":
            v = json.loads(v)
    except Exception:
        pass
    if isinstance(v, dict) and set(v) == {"returnValue"}:
        v = v["returnValue"]
        while isinstance(v, str) and v[:1] in "{[":
            v = json.loads(v)
    return v


def ref(path):
    return {"refPath": path}


def item(system, emitter="", script="", module="", renderer=-1, inputs=()):
    return {"system": ref(system), "emitterName": emitter, "scriptName": script, "moduleName": module,
            "rendererIndex": renderer, "inputNameStack": list(inputs)}
