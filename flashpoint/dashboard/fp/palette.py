"""Chart palette (validated with the dataviz six-checks validator, light + dark).

Color follows the entity everywhere in the app:
  camera/luminance = blue, audio/thunder = orange, met/weather = aqua.
Fires use the reserved status-critical red (always with icon + label), strike
estimates use ink/gray geometry, never a series hue.
"""

# categorical series (fixed assignment, never cycled)
CAMERA = "#2a78d6"   # slot 1 blue  — image luminance, camera entities
AUDIO = "#eb6834"    # slot 2 orange — audio energy, thunder entities
MET = "#1baf7a"      # slot 3 aqua  — weather/met entities

# status (reserved; icon + label always accompany)
FIRE = "#d03b3b"       # critical — wildfire incidents
FLASH = "#fab219"      # warning  — flash-candidate markers (⚡ glyph + rule)

# chrome
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"

# map layers (RGBA lists for pydeck)
MAP_NODE = [42, 120, 214, 210]        # blue
MAP_NODE_DIM = [137, 135, 129, 140]   # muted gray for context nodes
MAP_FIRE = [208, 59, 59, 220]         # critical red
MAP_STRIKE = [250, 178, 25, 235]      # warning yellow
MAP_RING = [235, 104, 52, 200]        # audio orange (range ring from thunder)
MAP_ELLIPSE = [11, 11, 11, 60]        # ink wash for uncertainty
