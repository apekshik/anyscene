"""Writes assets.json (the prop manifest). Edit here, re-run: python scenes/hk-dai-pai-dong/scripts/manifest.py"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
# id, h (m), dims [x,y,z] or None, tier, prompt
P = [
    # ---- hero: the kitchen
    ("hk_kitchen_cart", 1.0, [1.9, 0.85, 1.0], "hero", "A battered Hong Kong dai pai dong street-food kitchen cart: a long low steel cabinet painted dark green with peeling chipped paint, rust streaks and dents, hinged side doors with padlock hasps, a stainless-steel counter top with greasy stains and a raised back splash, small wheels."),
    ("hk_wok_range", 0.85, [1.5, 0.85, 0.85], "hero", "A Chinese commercial two-hole wok range: a stainless-steel cabinet with two deep cast-iron jet burner rings in round wok wells, a swing water faucet and a gutter along the front, gas valves with long lever handles, heavily blackened, grease-streaked and heat-discoloured."),
    ("hk_wok_a", 0.2, None, "hero", "A large round-bottomed blackened carbon-steel Cantonese wok, about 45 cm across, with two small riveted loop handles, seasoned and charred outside, glossy oily patina inside."),
    ("hk_wok_rice", 0.22, None, "hero", "A blackened carbon-steel wok with fried rice with egg, green onion and char siu tossed in it and a long-handled steel wok ladle resting inside, glistening with oil."),
    ("hk_wok_tools", 0.42, None, "mid", "A Cantonese wok ladle and a wok spatula with long steel shafts and wooden grips, plus a bamboo wok brush, lying together, greasy and worn."),
    ("hk_spider_strainer", 0.45, None, "mid", "A large wire-mesh spider strainer with a long bamboo handle, brass wire basket darkened with oil."),
    ("hk_stockpot", 0.45, None, "hero", "A large heavily used aluminium stockpot about 45 cm tall with riveted handles, dented sides, soot and heat discolouration, a warped lid half on."),
    ("hk_stockpot_small", 0.26, None, "mid", "A medium dented aluminium saucepot with a long handle and a battered lid, soot stains."),
    ("hk_steamer_stack", 0.32, None, "mid", "A stack of three round bamboo dim sum steamer baskets with a lid, darkened and stained from years of use."),
    ("hk_claypot", 0.16, None, "mid", "A small glazed Chinese claypot with a lid and a wire handle frame, charred black bottom, for claypot rice."),
    ("hk_rice_cooker", 0.42, None, "mid", "A big commercial electric rice cooker, dented aluminium body with a domed lid and a side lever, no logo, grimy."),
    ("hk_tea_urn", 0.55, None, "mid", "A stainless-steel hot water urn with a tap at the front and a domed lid, water stains, plain with no logo."),
    ("hk_cleaver_block", 0.16, None, "mid", "A thick round tree-trunk chopping block, scarred and concave from use, with a Chinese rectangular cleaver lying on it."),
    ("hk_hanging_utensils", 0.7, [0.9, 0.12, 0.7], "mid", "A greasy steel rod with S-hooks holding hanging kitchen tools: two ladles, a perforated skimmer, a wire spider strainer, a pair of long bamboo chopsticks and a wok brush."),
    ("hk_sauce_shelf", 0.42, [0.9, 0.25, 0.42], "mid", "A small greasy two-tier steel wall shelf crowded with sauce bottles and jars: soy sauce, oyster sauce, chili oil, Shaoxing wine, sesame oil, tins of salt, all with plain hand-lettered Chinese paper labels, grimy."),
    ("hk_oil_tin", 0.34, None, "mid", "A large square tin of cooking oil with a pour spout, dented and oily, label in faded red Chinese text of a fictional brand."),
    ("hk_lpg_cylinder", 0.75, None, "hero", "A tall grey steel LPG gas cylinder with a valve guard collar, a regulator and an orange rubber gas hose, scuffed and rusty at the base, no brand."),
    ("hk_veg_basket", 0.24, None, "mid", "A red plastic basket heaped with fresh choy sum greens and spring onions, water drops."),
    ("hk_prawn_tray", 0.07, None, "mid", "A stainless-steel tray of raw grey prawns and sliced squid on ice."),
    ("hk_aromatics_bowls", 0.1, None, "mid", "Three small stainless bowls of chopped garlic, sliced ginger and red chilli, a wet spoon."),
    ("hk_bowl_stack", 0.3, None, "mid", "A tall stack of white Chinese melamine rice bowls with a thin blue rim pattern, slightly scratched."),
    ("hk_plate_stack", 0.22, None, "mid", "A stack of oval white melamine serving plates with a red border pattern, scratched."),
    ("hk_dish_rack", 0.45, None, "mid", "A stainless wire dish drying rack full of wet white bowls and plates and a cluster of chopsticks."),
    ("hk_wash_basin", 0.3, None, "mid", "A big round red plastic wash basin full of soapy water and dirty bowls and plates."),
    ("hk_tub_blue", 0.3, None, "mid", "A large blue plastic storage tub with a loose lid, scuffed."),
    ("hk_crate_stack", 0.6, None, "mid", "Two stacked worn plastic bread crates, one blue and one red, holding cabbages and bags of bean sprouts."),
    ("hk_styrofoam_box", 0.3, None, "mid", "A white styrofoam cooler box with a lid, taped with brown tape, dirty and dented, handwritten Chinese marker on the side."),
    ("hk_rice_sack", 0.55, None, "mid", "A woven white polypropylene 25 kg rice sack, slumped, printed with a fictional red Chinese rice brand and a green field emblem."),
    ("hk_cardboard_boxes", 0.6, None, "mid", "A stack of three worn wet-cornered cardboard produce boxes printed with fictional Chinese supplier names."),
    ("hk_jars_preserved", 0.25, None, "mid", "Three big glass jars of preserved vegetables and pickled chillies with red plastic lids."),
    ("hk_thermos", 0.36, None, "mid", "A vintage Chinese tin thermos flask painted red with a peony flower pattern and a cork stopper, chipped paint."),
    ("hk_takeaway_boxes", 0.22, None, "clutter", "A stack of white foam takeaway clamshell boxes and a roll of thin red-and-white striped plastic bags."),
    ("hk_fan", 0.55, None, "mid", "An old oscillating electric table fan with a cream metal cage and grime on the blades, no logo."),
    ("hk_radio", 0.16, None, "clutter", "A small old transistor radio with a silver telescopic antenna, cracked plastic case, fictional brand name."),
    ("hk_fire_extinguisher", 0.55, None, "mid", "A red dry-powder fire extinguisher with a black hose and a Chinese instruction label, dusty."),
    ("hk_menu_board_a", 0.9, [0.6, 0.03, 0.9], "mid", "A weathered wooden menu board painted cream with red and black hand-brushed Chinese dish names and prices in vertical columns, rain-stained."),
    ("hk_menu_board_b", 0.5, [0.8, 0.03, 0.5], "mid", "A faded yellow plastic menu sign with handwritten red Chinese dish names and prices in marker, curling tape at the corners."),
    ("hk_enamel_shade", 0.18, None, "mid", "A dark green enamel industrial lamp shade with a bare tungsten bulb and a cloth-covered cord, chipped enamel, rust."),
    ("hk_fluoro_fitting", 0.08, [1.25, 0.12, 0.08], "mid", "A bare single fluorescent tube light fitting with a white metal batten, dusty and spotted with grease."),
    # ---- seating & tables
    ("hk_table_round", 0.74, [0.95, 0.95, 0.74], "hero", "A Hong Kong folding round dining table with a scratched stainless-steel top and a thin rolled rim, folding steel tube legs, worn and wet with raindrops."),
    ("hk_table_square", 0.72, [0.75, 0.75, 0.72], "mid", "A small square folding table with a green laminated top with chipped edges and folding steel legs, wet."),
    ("hk_stool_red", 0.45, None, "hero", "A classic red plastic stool with a round seat with a hand hole in the middle and four splayed legs, scuffed and slightly faded, raindrops."),
    ("hk_stool_stack", 0.95, None, "mid", "A leaning stack of six red plastic stools, scuffed, wet."),
    ("hk_stool_blue", 0.45, None, "mid", "A blue plastic square stool with a perforated seat, scuffed and faded."),
    # ---- on the tables
    ("hk_enamel_teapot", 0.2, None, "hero", "A white enamel teapot with a red peony flower pattern, chipped black edges and a bail handle, tea stains."),
    ("hk_tea_cups", 0.08, None, "mid", "Four small thick white restaurant tea cups and a plastic bowl of hot water for rinsing chopsticks."),
    ("hk_condiment_caddy", 0.2, None, "hero", "A small stainless steel condiment caddy holding a soy sauce bottle, a chilli oil jar with a spoon, a white pepper shaker and a toothpick holder, greasy, plain labels."),
    ("hk_soy_bottles", 0.24, None, "mid", "Two glass sauce dispenser bottles with red plastic caps, one with dark soy sauce, one with red vinegar, smeared."),
    ("hk_chopstick_cup", 0.24, None, "mid", "A dented stainless-steel cylinder cup full of bamboo chopsticks and a few white plastic soup spoons."),
    ("hk_toilet_roll", 0.12, None, "clutter", "A roll of pink toilet paper used as napkins sitting in a plastic holder, slightly damp."),
    ("hk_newspaper", 0.03, None, "mid", "A folded Chinese-language racing newspaper with horse racing tables and photos, creased, a pen lying on it, fictional masthead."),
    ("hk_dish_fried_rice", 0.08, None, "mid", "An oval white plate of Yangzhou fried rice with shrimp, egg and char siu, half eaten, a porcelain spoon in it."),
    ("hk_dish_beef_hofun", 0.08, None, "mid", "An oval plate of dry-fried beef ho fun flat rice noodles with bean sprouts and spring onion, glossy dark."),
    ("hk_dish_clams", 0.08, None, "mid", "A plate of stir-fried clams in black bean and chilli sauce, shells open, glistening."),
    ("hk_dish_greens", 0.06, None, "mid", "A plate of blanched choy sum greens with oyster sauce drizzled over."),
    ("hk_dish_salt_squid", 0.08, None, "mid", "A plate of salt and pepper fried squid with fried garlic and red chilli."),
    ("hk_milk_tea", 0.14, None, "clutter", "A thick white Hong Kong cha chaan teng mug of milk tea, tan colour, on a saucer."),
    ("hk_lemon_tea", 0.17, None, "clutter", "A tall glass of iced lemon tea with lemon slices, ice and a straw, condensation."),
    ("hk_beer_bottles", 0.3, None, "mid", "Two large green beer bottles with a fictional label reading 金龍啤酒 and a short glass of beer with foam."),
    ("hk_beer_crate", 0.32, None, "mid", "A yellow plastic beer crate holding twelve empty green bottles with fictional labels."),
    ("hk_ashtray", 0.04, None, "clutter", "A crushed tin ashtray with cigarette butts and ash."),
    ("hk_bowl_congee", 0.1, None, "clutter", "A white melamine bowl of congee with century egg and green onion and a plastic spoon."),
    # ---- street
    ("hk_street_lamp", 8.5, None, "hero", "A tall grey steel Hong Kong street lamp post with a long curved outreach arm and a flat rectangular lantern head, rust streaks, small numbered plate."),
    ("hk_guard_railing", 1.0, [2.0, 0.1, 1.0], "mid", "A section of Hong Kong roadside pedestrian guard railing: grey painted steel tube railing with vertical bars between two posts, chipped paint, rust."),
    ("hk_water_barrier", 0.8, [1.3, 0.45, 0.8], "mid", "A plastic water-filled road barrier, alternating red and white, dirty, scuffed, rain wet."),
    ("hk_traffic_cone", 0.7, None, "clutter", "An orange traffic cone with reflective white bands, dirty and scuffed."),
    ("hk_parked_car", 1.45, [1.75, 4.4, 1.45], "hero", "A generic 1990s boxy four-door saloon car in dark red, rain-wet, no badges, no logos, no number plate text, dirt on the sills."),
    ("hk_scooter", 1.15, None, "mid", "A small generic delivery motor scooter with a delivery box on the back, no logos, wet, scuffed."),
    ("hk_hand_trolley", 1.1, None, "mid", "A steel two-wheel hand trolley loaded with flattened cardboard and a crate, straps, worn."),
    ("hk_trash_bin", 0.95, None, "mid", "A large green plastic wheelie rubbish bin with the lid half open, a black bag poking out, grimy."),
    ("hk_bin_bags", 0.6, None, "clutter", "Three tied black rubbish bags in a heap, wet and glossy."),
    ("hk_umbrella", 0.9, None, "clutter", "A closed wet black folding umbrella leaning, slightly crumpled."),
    ("hk_shrine", 0.5, None, "mid", "A small red Chinese street shrine box for the earth god on the ground with a gold inscription, incense sticks in a pot, oranges and a small cup, burnt candle wax."),
    ("hk_aircon_unit", 0.4, [0.66, 0.6, 0.4], "mid", "An old window air conditioner unit, beige metal case with rust stains and a grille, dripping water, no logo."),
    ("hk_electric_box", 0.55, [0.45, 0.2, 0.55], "mid", "A grey steel electrical meter box on a wall with conduits coming out, rusty, a few stickers with Chinese text, no brand."),
    ("hk_mop_bucket", 0.7, None, "clutter", "A grey mop leaning in a battered red plastic bucket."),
    ("hk_plastic_bag_hang", 0.4, None, "clutter", "A red-and-white striped thin plastic shopping bag hanging from a hook with something heavy inside."),
    ("hk_bird_cage", 0.45, None, "clutter", "A round bamboo bird cage with a cloth cover partly lifted, hanging hook on top."),
    ("hk_water_bucket", 0.32, None, "clutter", "A battered aluminium bucket half full of water."),
]

TEX = [
    ("hk_tex_skyline", "landscape_16_9", "Wide night photograph across a harbour toward a dense high-rise city skyline on the far shore, very soft and out of focus as if shot through rain with a long lens, lights reduced to soft blurred bokeh, low clouds glowing orange and magenta from the city lights, misty, no recognisable landmark towers, no readable text."),
    ("hk_tex_facade_a", "portrait_16_9", "Straight-on orthographic elevation photograph of an old 1960s Hong Kong tenement building facade at night, six floors of windows with rusty metal grilles, a few warm lit windows, laundry poles, air conditioner units, mould stains on grey-green mosaic tiles, flat front view, no perspective, no signs, no text."),
    ("hk_tex_facade_b", "portrait_16_9", "Straight-on orthographic elevation photograph of an old Hong Kong residential tenement facade at night, cream painted concrete stained with black rain streaks, rows of aluminium windows with security grilles, potted plants on ledges, two lit windows with fluorescent light, flat front view, no perspective, no signs, no text."),
    ("hk_tex_facade_c", "portrait_16_9", "Straight-on orthographic elevation photograph of a narrow old Hong Kong tenement at night with enclosed balconies with metal cages, faded pink paint, water stains, a few lit windows, hanging laundry, flat front view, no perspective, no signs, no text."),
    ("hk_tex_shutter_a", "landscape_4_3", "Flat straight-on photo of a closed corrugated steel roller shutter of a Hong Kong shop at night, grey, dented, rust streaks, a small padlock at the bottom, flat lit, fills the frame, no readable shop name."),
    ("hk_tex_shutter_b", "landscape_4_3", "Flat straight-on photo of a closed green-painted roller shutter of a Hong Kong hardware shop, peeling paint, old paper notices taped on it with handwritten Chinese, rust, fills the frame."),
    ("hk_tex_stall_sign", "landscape_16_9", "Flat front view of a weathered painted shop sign board for a Hong Kong street-food stall: cream background, large red brush-calligraphy Chinese characters 旺記小炒 on the left and smaller black vertical columns of dish names on the right, rust stains, grease, chipped edges, fills the frame exactly, fictional business."),
    ("hk_tex_posters", "square_hd", "Flat lay of six weathered torn paper posters and notices on a white background, spaced apart: a Chinese opera performance poster with fictional names, a handwritten room-for-rent notice 吉房出租, a plumbing service sticker with a phone number, a faded movie poster with a fictional title, a missing cat notice, a lucky red paper with gold characters. Fictional text only."),
    ("hk_tex_menu_strips", "landscape_16_9", "Flat front view of a row of twelve vertical red and yellow paper menu strips with hand-brushed black Chinese dish names and prices like 豉椒炒蜆 $68 and 乾炒牛河 $62, taped side by side on a wall, grease spots, fills the frame."),
    ("hk_tex_lightbox_a", "portrait_4_3", "Flat front view of a vertical Hong Kong shop lightbox sign, white panel with large red Chinese characters 長發飯店 and a thin green border, slightly dirty, evenly backlit, fills the frame, fictional business, no other text."),
    ("hk_tex_lightbox_b", "portrait_4_3", "Flat front view of a vertical Hong Kong lightbox sign, yellow panel with large black Chinese characters 和興五金 and a red stripe, dirty, evenly backlit, fills the frame, fictional business."),
    ("hk_tex_lightbox_c", "portrait_4_3", "Flat front view of a vertical Hong Kong lightbox sign, blue panel with white Chinese characters 美珍冰室 and a painted coffee cup icon, dirty, evenly backlit, fills the frame, fictional business."),
    ("hk_tex_asphalt", "square_hd", "Top-down seamless texture of wet old asphalt road surface with dark puddles, oil sheen, cracks and patched areas, overcast flat lighting, no markings."),
    ("hk_tex_pavement", "square_hd", "Top-down seamless texture of Hong Kong pavement made of small square grey and red concrete paving bricks, wet, worn, stained, chewing gum spots, flat lighting."),
]


# De-branded regenerations: the reference of the original showed a brand (checked on the ref sheet).
NB_REGEN = {
    "hk_beer_crate": "A yellow plastic beer crate holding twelve empty green beer bottles, the crate moulded with the fictional Chinese brewery name 金龍啤酒 only, no English text, scuffed and dirty.",
}

NB = "No real-world brand names or logos."
SCAN = NB + " Product reference photograph for 3D scanning. The entire object fully visible and centered, three-quarter front view from slightly above, plain seamless light-grey background, soft even diffuse studio lighting, no harsh shadows, no other objects, no hands, realistic used and worn condition, sharp focus, true-to-life materials."

# Lying-flat props: size by their longest dimension ("m"), not their height.
M_SIZE = {"hk_wok_tools": 0.5, "hk_spider_strainer": 0.55, "hk_umbrella": 0.95}
gen = []
for pid, h, dims, tier, prompt in P:
    e = {"id": pid, "h": h, "tier": tier, "prompt": prompt}
    if pid in M_SIZE:
        e.pop("h")
        e["m"] = M_SIZE[pid]
    if dims:
        e["dims"] = dims
    gen.append(e)
for pid, prompt in NB_REGEN.items():
    base = next(e for e in gen if e["id"] == pid)
    gen.append({**base, "id": pid + "_nb", "replaces": pid, "prompt": prompt})
out = {
    "room": {"kind": "street", "width_x": 13.6, "depth_y": 50, "height_z": 22,
             "note": "Semi-outdoor. Street along +Y. Stall-side facade x=-4, pavement x -4..0 (z 0), kerb x=0, road x 0..7.4 (z -0.15), far pavement to x 9.6, far facade x 9.6. See brief.md."},
    "scan_template": SCAN,
    "generate": gen,
    "textures": [{"id": i, "size": s, "prompt": p + " " + NB} for i, s, p in TEX],
    "direct": ["street/road/kerb/pavement", "tenement facades, windows, balconies", "awning frame + corrugated tarp", "steel shelves",
               "bare bulbs + cords", "neon text (msjh.ttc text objects)", "drains, puddles", "wok flames", "cables"],
}
if __name__ == "__main__":
    json.dump(out, open(os.path.join(HERE, "..", "assets.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(len(gen), "props,", len(TEX), "textures")
