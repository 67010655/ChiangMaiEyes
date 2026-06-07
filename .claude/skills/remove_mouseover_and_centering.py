import re

map_path = r"c:\Users\User\Desktop\ChiangMaiEyes\frontend\src\components\DashboardMap.tsx"

with open(map_path, "r", encoding="utf-8") as f:
    content = f.read()

# Normalize CRLF
content_norm = content.replace("\r\n", "\n")

# 1. Remove .on('mouseover', ...) that updates selection for community forests, hotspots, pm2.5, landmarks, etc.
# We will look for .on('mouseover', ...) blocks and remove them.
# Let's inspect the specific mouseover handlers in the file:

# For Community Forest circles:
# .on('mouseover', () => {
#   if (!isPinningRef.current) onSelChangeRef.current(selected);
# })
content_norm = content_norm.replace(
    ".on('mouseover', () => {\n\n          if (!isPinningRef.current) onSelChangeRef.current(selected);\n\n        })",
    ""
)
content_norm = content_norm.replace(
    ".on('mouseover', () => {\n          if (!isPinningRef.current) onSelChangeRef.current(selected);\n        })",
    ""
)

# For Community Forest markers:
# .on('mouseover', () => {
#   if (!isPinningRef.current) onSelChangeRef.current(selected);
# })
# (This is identical, let's make sure both are removed if found)

# Let's write a regex that matches .on('mouseover', () => { ... }) where it calls onSelChangeRef.current
# or sets selection, and deletes it.
# The pattern should look for: .on('mouseover', ... onSelChangeRef.current ... )
pattern_mouseover = re.compile(r"\.on\('mouseover',\s*\(\)\s*=>\s*\{\s*if\s*\(!isPinningRef\.current\)\s*onSelChangeRef\.current\(.*?\);\s*\}\)", re.DOTALL)
content_norm, count1 = pattern_mouseover.subn("", content_norm)
print(f"Removed {count1} mouseover handlers using pattern 1.")

# Let's also check for other mouseover handlers that call onSelChangeRef.current
# E.g. hotspots, PM2.5, landmarks:
# .on('mouseover', () => {
#   if (!isPinningRef.current) {
#     onSelChangeRef.current(...);
#   }
# })
pattern_mouseover2 = re.compile(r"\.on\('mouseover',\s*\(\)\s*=>\s*\{\s*if\s*\(!isPinningRef\.current\)\s*\{\s*onSelChangeRef\.current\(.*?\);\s*\}\s*\}\)", re.DOTALL)
content_norm, count2 = pattern_mouseover2.subn("", content_norm)
print(f"Removed {count2} mouseover handlers using pattern 2.")

# Let's do a search for any remaining .on('mouseover', ...) that call onSelChangeRef.current:
pattern_mouseover_generic = re.compile(r"\.on\('mouseover',\s*\(\)\s*=>\s*\{\s*(?:if\s*\(!isPinningRef\.current\)\s*)?onSelChangeRef\.current\(.*?\);\s*\}?\)", re.DOTALL)
content_norm, count3 = pattern_mouseover_generic.subn("", content_norm)
print(f"Removed {count3} mouseover handlers using generic pattern.")

# Let's check for mouseover inside the Dry Forest Zone (NDVI):
# .on('mouseover', () => {
#   if (isPinningRef.current) return;
#   ...
#   onSelChangeRef.current(...);
# })
pattern_mouseover_ndvi = re.compile(r"\.on\('mouseover',\s*\(\)\s*=>\s*\{\s*if\s*\(isPinningRef\.current\)\s*return;\s*.*?\s*onSelChangeRef\.current\(.*?\);\s*\}\)", re.DOTALL)
content_norm, count4 = pattern_mouseover_ndvi.subn("", content_norm)
print(f"Removed {count4} mouseover handlers for NDVI using regex.")

# 2. Update the selection useEffect to completely remove map.setView and highlightMarker
old_effect_body = """    if (lat !== undefined && lng !== undefined) {

      isTransitioningRef.current = true;

      // Pan map to selection, zooming in if currently zoomed out

      const targetZoom = Math.max(map.getZoom(), 11);

      map.setView([lat, lng], targetZoom, { animate: true });

      const pulseIcon = L.divIcon({

        html: `<div class="selected-marker-focus-container">

                 <div class="selected-marker-focus-glow"></div>

                 <div class="selected-marker-pulse">

                   <div class="pulse-ring-selected"></div>

                 </div>

               </div>`,

        className: 'lf-selection-pulse-wrap',

        iconSize: [40, 40],

        iconAnchor: [20, 20],

      });

      const highlightMarker = L.marker([lat, lng], {

        icon: pulseIcon,

        zIndexOffset: 10000,

        interactive: false

      }).addTo(map);

      selectionHighlightRef.current = highlightMarker;

      // Programmatically open the Leaflet popup at the focused coordinates

      const popupContent = createPopupHtml(

        selection.eyebrow || 'ข้อมูล',

        selection.title,

        selection.detail || '',

        selection.stats || [],

        selection.mapUrl,

        selection.sourceLabel,

        selection.sourceUrl

      );

      const popup = L.popup({

        maxWidth: 340,

        minWidth: 300,

        className: 'map-custom-popup',

        closeOnClick: false,

      })

      .setLatLng([lat, lng])

      .setContent(popupContent);

      const timer = setTimeout(() => {

        popup.openOn(map);

        activePopupRef.current = popup;

        isTransitioningRef.current = false;

      }, 200);

      return () => {

        clearTimeout(timer);

      };

    }"""

new_effect_body = """    if (lat !== undefined && lng !== undefined) {
      // Programmatically open the Leaflet popup at the coordinates (e.g. when selected from sidebar)
      const currentPopup = activePopupRef.current;
      if (currentPopup && currentPopup.getLatLng()?.lat === lat && currentPopup.getLatLng()?.lng === lng) {
        return;
      }

      const popupContent = createPopupHtml(
        selection.eyebrow || 'ข้อมูล',
        selection.title,
        selection.detail || '',
        selection.stats || [],
        selection.mapUrl,
        selection.sourceLabel,
        selection.sourceUrl
      );

      const popup = L.popup({
        maxWidth: 340,
        minWidth: 300,
        className: 'map-custom-popup',
        closeOnClick: false,
      })
      .setLatLng([lat, lng])
      .setContent(popupContent);

      const timer = setTimeout(() => {
        popup.openOn(map);
        activePopupRef.current = popup;
      }, 200);

      return () => {
        clearTimeout(timer);
      };
    }"""

# Clean double spacing in target just in case
old_effect_body_clean = re.sub(r'\n+', '\n', old_effect_body)
content_norm_clean_effect = re.sub(r'\n+', '\n', content_norm)

if old_effect_body_clean in content_norm_clean_effect:
    # We replace using regex or index search
    # Let's locate using re.search
    pattern_effect = re.compile(r'if \(lat !== undefined && lng !== undefined\) \{.*?isTransitioningRef\.current = false;.*?clearTimeout\(timer\);.*?\}', re.DOTALL)
    content_norm, count_eff = pattern_effect.subn(new_effect_body, content_norm)
    print(f"SUCCESS: Updated selection useEffect block ({count_eff} matches replaced).")
else:
    print("Error: Could not match selection useEffect block!")
    exit(1)

# Write back with CRLF line endings
with open(map_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content_norm)

print("SUCCESS: DashboardMap.tsx interactions cleaned up!")
