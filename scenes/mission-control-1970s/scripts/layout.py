"""Shared layout constants for the mission-control room (metres; x across, y back door -> wall display, z up)."""
W, D, H = 11.0, 13.0, 3.6
T = 0.2  # wall thickness
# tiers: (floor z, y0, y1); tier 0 is the front (display end)
TIERS = [(0.0, 7.5, D), (0.35, 4.5, 7.5), (0.7, 0.0, 4.5)]
WIN_Y0, WIN_Y1, WIN_Z0, WIN_Z1 = 1.2, 9.6, 1.3, 3.1  # left-wall window band
DOOR_X0, DOOR_X1, DOOR_Z1 = 4.9, 6.1, 2.85
AISLE_L = (0.3, 1.7)  # step x-range, window aisle
AISLE_R = (9.35, 10.2)  # step x-range, right aisle

# console rows: name, floor z, front (operator-side) y of the consoles, x start, bay list (left -> right)
# bays: console prop ids; placard text per bay (None = no placard)
ROWS = [
    ("A", 0.0, 9.6, 1.95, ["mc_console_end", "mc_console_crt", "mc_console_twin", "mc_console_scope", "mc_console_crt",
                           "mc_console_comms", "mc_console_end"],
     [None, "GUIDANCE", "TRAJECTORY", "ORBITAL ANALYSIS", "TELEMETRY", "COMMS", None]),
    ("B", 0.35, 6.5, 2.6, ["mc_console_end", "mc_console_lamps", "mc_console_twin", "mc_console_crt", "mc_console_comms",
                           "mc_console_end"],
     [None, "POWER", "LIFE SUPPORT", "PROPULSION", "NETWORK", None]),
    ("C", 0.7, 3.5, 3.25, ["mc_console_end", "mc_console_crt", "mc_console_lamps", "mc_console_twin", "mc_console_end"],
     [None, "RECOVERY", "FLIGHT DIRECTOR", "MISSION OPS", None]),
]
BAY_W = {"mc_console_end": 0.45}
DEFAULT_BAY_W = 1.25
CONSOLE_D = 1.0


def tier_z(y):
    for z, y0, y1 in TIERS:
        if y0 <= y <= y1:
            return z
    return 0.0


def bays(row):
    """Yield (prop id, placard, x centre, x0, x1) for a row."""
    name, z, y, x, ids, labels = row
    for pid, lab in zip(ids, labels):
        w = BAY_W.get(pid, DEFAULT_BAY_W)
        yield pid, lab, x + w / 2, x, x + w
        x += w


# wall display on the front wall (y = D): panels (name, x0, x1), shared z range
DISP_Z0, DISP_Z1 = 1.05, 3.15
DISP_PANELS = [("wall_left", 1.3, 3.4), ("wall_map", 3.65, 7.85), ("wall_right", 8.1, 10.2)]
