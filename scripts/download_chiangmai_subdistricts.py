import urllib.request
import json
import os
import sys

URL = "https://raw.githubusercontent.com/chingchai/OpenGISData-Thailand/master/subdistricts.geojson"
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "public"))
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "chiangmai-subdistricts.json")

def main():
    print(f"Downloading Thailand subdistricts GeoJSON from: {URL}")
    try:
        # Fetch the file (could be large, e.g. 50MB)
        # To avoid loading the whole file if memory is tight, we fetch it. It's usually fine to read as raw string.
        response = urllib.request.urlopen(URL)
        data = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error downloading or parsing JSON: {e}", file=sys.stderr)
        return

    features = data.get("features", [])
    print(f"Total features loaded: {len(features)}")
    
    if not features:
        print("No features found in GeoJSON.", file=sys.stderr)
        return

    # Check the property keys of the first feature to see how province is named
    sample_properties = features[0].get("properties", {})
    print(f"Sample feature properties keys: {list(sample_properties.keys())}")
    print(f"Sample properties values: {sample_properties}")

    # Let's dynamically find the province key
    prov_key = None
    for key in sample_properties.keys():
        val = str(sample_properties[key])
        # Check if province value is Chiang Mai or in Thai
        if "เชียงใหม่" in val or "Chiang Mai" in val or val.startswith("50"): # 50 is Chiang Mai code
            prov_key = key
            print(f"Detected province key: {prov_key} (sample value: {val})")
            break
            
    # If not detected, check for common keys
    if not prov_key:
        for key in ["pro_th", "pv_th", "prov_namt", "PROV_NAMT", "province_name", "province"]:
            if key in sample_properties:
                prov_key = key
                break
                
    if not prov_key:
        prov_key = "pro_th" # fallback
        
    print(f"Using province key: '{prov_key}' to filter Chiang Mai subdistricts.")

    filtered_features = []
    for f in features:
        props = f.get("properties", {})
        prov_val = str(props.get(prov_key, ""))
        # Filter for Chiang Mai
        if "เชียงใหม่" in prov_val or "Chiang Mai" in prov_val or prov_val.startswith("50"):
            filtered_features.append(f)

    print(f"Filtered features for Chiang Mai: {len(filtered_features)}")

    if not filtered_features:
        # Fallback: maybe the first feature was not Chiang Mai so the key detection was off.
        # Let's search all features for any property containing "เชียงใหม่"
        print("No features matched. Attempting aggressive fallback search for 'เชียงใหม่' in any property value...")
        for f in features:
            props = f.get("properties", {})
            for key, val in props.items():
                if "เชียงใหม่" in str(val):
                    filtered_features.append(f)
                    break
        print(f"Aggressive fallback filtered features: {len(filtered_features)}")

    # Construct filtered GeoJSON
    filtered_geojson = {
        "type": "FeatureCollection",
        "features": filtered_features
    }

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(filtered_geojson, out, ensure_ascii=False, indent=2)

    print(f"Saved filtered Chiang Mai subdistricts to: {OUTPUT_FILE} (size: {os.path.getsize(OUTPUT_FILE) / 1024:.2f} KB)")

if __name__ == "__main__":
    main()
