import os
import json

def convert_yjsp_to_project(yjsp_path, output_project_dir):
    with open(yjsp_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    header = {}
    notes_data = []
    
    in_notes = False
    current_note = {}

    for line in lines:
        line = line.rstrip('\n')
        if not line:
            continue
            
        if line == "notes:":
            in_notes = True
            continue
        if line == "end:":
            if current_note:
                notes_data.append(current_note)
                current_note = {}
            break
            
        if not in_notes:
            if ": " in line:
                key, val = line.split(": ", 1)
                header[key.strip()] = val.strip()
        else:
            if line.startswith("- position: "):
                if current_note:
                    notes_data.append(current_note)
                current_note = {}
                current_note["position"] = int(line.split(": ")[1])
            elif ": " in line:
                key, val = line.split(": ", 1)
                key = key.strip()
                val = val.strip()
                if key in ["duration", "tone", "bend_first", "bend_second"]:
                    try:
                        current_note[key] = int(val)
                    except ValueError:
                        try:
                            current_note[key] = float(val)
                        except:
                            current_note[key] = val
                else:
                    current_note[key] = val

    if current_note:
        notes_data.append(current_note)

    bpm = float(header.get("bpm", 120))
    sampling_rate = int(header.get("sampling_rate", 44100))
    singer_path = header.get("sound_source_dir", "")
    
    samples_per_beat = (60.0 / bpm) * sampling_rate

    # Load reverse lookup for lyrics
    reverse_texts = {}
    my_path = os.path.dirname(os.path.abspath(__file__))
    
    # Try user defined phonetic mapping
    """
    try:
        if os.path.exists(os.path.join(singer_path, "settings", "音素片表.json")):
            with open(os.path.join(singer_path, "settings", "音素片表.json"), "r", encoding="utf-8") as f:
                texts = json.load(f)
                for k, v in texts.items():
                    reverse_texts[v] = k
    except Exception as e:
        print(f"Failed to load user phonetics mapping: {e}")
        
    # Try built-in phonetic mapping
    try:
        if os.path.exists(os.path.join(my_path, "settings", "音素片表.json")):
            with open(os.path.join(my_path, "settings", "音素片表.json"), "r", encoding="utf-8") as f:
                texts_builtin = json.load(f)
                for k, v in texts_builtin.items():
                    if v not in reverse_texts:
                        reverse_texts[v] = k
    except Exception as e:
        print(f"Failed to load builtin phonetics mapping: {e}")
    """

    out_notes = []
    
    for n in notes_data:
        # Calculate x and w
        pos_samples = n.get("position", 0)
        dur_samples = n.get("duration", 0)
        
        # Rounding to nearest int since x and w are usually pixel coordinates in UI
        x = round((pos_samples / samples_per_beat) * 40)
        w = round((dur_samples / samples_per_beat) * 40)
        
        tone = n.get("tone", 60)
        y = (84 - tone) * 20
        
        lyric_path = n.get("lyric", "")
        # extract filename without extension
        filename = os.path.basename(lyric_path)
        if filename.endswith(".wav"):
            filename = filename[:-4]
            
        lyric = reverse_texts.get(filename, filename)
        
        # skip rest notes created by convert.py
        if lyric == "r":
            continue 
            
        out_notes.append({
            "x": x,
            "y": y,
            "w": w,
            "h": 20,
            "lyric": lyric,
            "bend_first": n.get("bend_first", 0),
            "bend_second": n.get("bend_second", 0)
        })

    # create project dir if needed
    os.makedirs(output_project_dir, exist_ok=True)
    
    with open(os.path.join(output_project_dir, "notes.json"), "w", encoding="utf-8") as f:
        json.dump({"notes": out_notes}, f, indent=4, ensure_ascii=False)
        
    locator_R = 0
    if out_notes:
        last_note = max(out_notes, key=lambda n: n["x"] + n["w"])
        locator_R = last_note["x"] + last_note["w"] + 100

    others_data = {
        "bpm": bpm,
        "singer": singer_path,
        "locator_right": locator_R,
        "locator_left": 0
    }
    
    with open(os.path.join(output_project_dir, "others.json"), "w", encoding="utf-8") as f:
        json.dump(others_data, f, indent=4, ensure_ascii=False)

    print(f"Successfully converted {yjsp_path} to project files at {output_project_dir}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python yjsp_to_project.py <input.yjsp> <output_project_dir>")
    else:
        convert_yjsp_to_project(sys.argv[1], sys.argv[2])
