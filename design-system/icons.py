import json, os
def circ(cx, cy, r):
    return f"M{cx+r} {cy}a{r} {r} 0 1 1 {-2*r} 0a{r} {r} 0 1 1 {2*r} 0"
I = {
 "play":    "M7 4.5l12 7.5-12 7.5z",
 "pause":   "M8 5v14M16 5v14",
 "stop":    "M6 6h12v12H6z",
 "step":    "M5 5l9 7-9 7zM18 5v14",
 "reset":   "M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4 3.5V8h4.5",
 "home":    "M3.5 11.5L12 4l8.5 7.5M6 10v10h12V10M10 20v-5h4v5",
 "estop":   "M8.3 3h7.4L21 8.3v7.4L15.7 21H8.3L3 15.7V8.3zM8 12h8",
 "robot":   "M4 21h10M6 21v-2.5h6V21M9 18.5L7 11M7 11l7.5-4M14.5 7l3.5 3.5M18 10.5l2.5-1M18 10.5l1 2.5" + circ(7,11,1.6) + circ(14.5,7,1.6),
 "gripper": "M12 2.5V7M6 7h12M7 7v6l3 4v4.5M17 7v6l-3 4v4.5",
 "jog":     "M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3",
 "axes":    "M5 19V5M5 19h14M5 19l8-8M3 7l2-2 2 2M17 17l2 2-2 2",
 "cube":    "M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5",
 "target":  circ(12,12,8) + circ(12,12,3) + "M12 1.5V5M12 19v3.5M1.5 12H5M19 12h3.5",
 "camera":  "M3 8h4l2-3h6l2 3h4v11H3z" + circ(12,13,3.5),
 "eye":     "M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z" + circ(12,12,2.75),
 "layers":  "M12 3l9 5-9 5-9-5zM3 12.5l9 5 9-5M3 16.5l9 5 9-5",
 "program": "M9 6h11M9 12h11M9 18h11M4 6h1.5M4 12h1.5M4 18h1.5",
 "shield":  "M12 3l7.5 3v6c0 4.6-3.2 7.7-7.5 9-4.3-1.3-7.5-4.4-7.5-9V6zM8.5 12l2.5 2.5 4.5-5",
 "policy":  circ(6,6,2) + circ(18,6,2) + circ(12,12,2) + circ(6,18,2) + circ(18,18,2) + "M7.5 7.5l3 3M16.5 7.5l-3 3M7.5 16.5l3-3M16.5 16.5l-3-3",
 "train":   "M3 17l5.5-5.5 4 4L21 7M15 7h6v6",
 "chart":   "M4 4v16h16M7.5 15l3.5-4.5 3 3 5-6.5",
 "terminal":"M3 4.5h18v15H3zM7 9l3 3-3 3M12.5 15H17",
 "sliders": "M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1" + circ(15,6,2) + circ(9,12,2) + circ(17,18,2),
 "warning": "M12 3.5l9.5 17h-19zM12 10v4.5M12 17.5v.5",
 "check":   "M4.5 12.5l5 5 10-11",
 "lock":    "M5.5 11h13v10h-13zM8 11V7.5a4 4 0 0 1 8 0V11",
 "chevron": "M9 5.5l6.5 6.5L9 18.5",
}
INK = "#14181d"
for k, d in I.items():
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
           f'stroke="{INK}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="{d}"/></svg>\n')
    open(f"project/assets/Icons/{k}.svg", "w").write(svg)
json.dump(I, open("icons.json", "w"))
print(len(I), "icons")
