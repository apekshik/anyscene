"""The scene plan: the editable layout the /plan call returns and /build consumes. See docs/ENDPOINT.md.

Metres, Z up. Origin = floor at the room's front-left corner seen from the entrance: X right along the front wall,
Y into the room. Walls: front (y=0), back (y=depth), left (x=0), right (x=width). rot 0 = object faces -Y.
"""

from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["reference", "invented"]
Wall = Literal["front", "back", "left", "right"]


class Room(BaseModel):
    width: float = Field(description="Extent along X in metres (the front wall).")
    depth: float = Field(description="Extent along Y in metres (into the space).")
    height: float = Field(description="Ceiling or awning height in metres.")


class Opening(BaseModel):
    wall: Wall
    kind: Literal["door", "window", "shopfront", "opening"]
    center: float = Field(description="Centre position along the wall in metres: the X coordinate for front/back "
                                      "walls, the Y coordinate for left/right walls.")
    width: float
    height: float
    sill: float = Field(0.0, description="Height of the bottom edge above the floor.")


class SceneObject(BaseModel):
    id: str = Field(description="snake_case, unique, e.g. kitchen_cart, stool_red_3.")
    label: str = Field(description="Short human description.")
    asset: str = Field("", description="snake_case asset key. Identical objects (a set of chairs, a row of stools, matching "
                                       "mugs) share one key and are generated once; give every distinct design its own.")
    category: Literal["structure", "furniture", "fixture", "prop", "clutter", "decal", "signage"]
    x: float = Field(description="Footprint centre X.")
    y: float = Field(description="Footprint centre Y.")
    z: float = Field(0.0, description="Height of the object's base (0 = on the floor; a counter-top prop sits higher).")
    w: float = Field(description="Size along the object's own X (width) in metres.")
    d: float = Field(description="Size along the object's own Y (depth) in metres.")
    h: float = Field(description="Height in metres.")
    rot: float = Field(0.0, description="Rotation about Z in degrees; 0 = faces -Y (the entrance).")
    source: Source
    generate: bool = Field(description="True if this object should be generated as a 3D mesh; False for simple "
                                        "geometry built by script (walls, counters, shelves, boxes, paper).")
    prompt: str = Field("", description="For generated objects: one-object description with condition and materials, "
                                       "no brand names.")
    material: str = Field("", description="For objects that are NOT generated (counters, walls, shelves, panels, boxes): "
                                         "the surface as a texture description, e.g. \"scuffed beige enamelled steel\". "
                                         "Empty for generated objects.")
    crop: list[float] | None = Field(None, description="Where the object appears in reference image 0, as normalised "
                                                       "[x0, y0, x1, y1]; null if not visible.")


class Light(BaseModel):
    id: str
    kind: Literal["practical", "neon", "window", "street", "screen", "fire", "fill"]
    x: float
    y: float
    z: float
    color: str = Field(description="Hex colour, e.g. #ffb46b.")
    power: Literal["low", "medium", "high"]
    attached_to: str = Field("", description="Object id the light belongs to, if any.")
    source: Source


class Camera(BaseModel):
    position: list[float] = Field(description="[x, y, z] in metres.")
    look_at: list[float] = Field(description="[x, y, z] point the camera aims at.")
    lens_mm: float = Field(description="Focal length on a 36 mm-wide sensor.")


class Plan(BaseModel):
    name: str = Field(description="kebab-case scene name, e.g. hk-dai-pai-dong.")
    summary: str
    setting: Literal["interior", "semi_outdoor", "exterior"]
    time_of_day: str
    mood: list[str]
    palette: list[str] = Field(description="3-6 hex colours that define the look.")
    room: Room
    openings: list[Opening]
    objects: list[SceneObject]
    lights: list[Light]
    reference_camera: Camera = Field(description="Best estimate of where the camera stood for reference image 0.")
    notes: list[str] = Field(description="What was invented beyond the reference, and any assumptions.")
