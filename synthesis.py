#geminidがやった
import numpy as np
import pyworld as pw
import soundfile as sf
import json

import tkinter.filedialog as fd
import os

from pathlib import Path

import time


open_path = "" #fd.askopenfilename(title="プロジェクトファイルを選択", filetypes=[("YJS Project Files", "*.yjsp")])
output_file = ""
warnings = []

my_path = os.path.dirname(os.path.abspath(__file__))

#プロジェクトファイルからの情報(いったん定義)
start_note = 0
end_note = 0
number_of_notes = 0
duration_sec = 0 #何秒か
total_samples = 0 #fs * duration_sec
#固定
fs = 44100
buffer_size = 512

sound = np.array([]) #これに付け足す

is_pre_render = False

_synth_cache = {
    True: None,
    False: None
}
last_singer_path = ""


def load_projectfile(open_path):
    global start_note, end_note, number_of_notes, duration_sec, total_samples, lines, fs, buffer_size, singer_path, output_file, texts, tones, warnings, texts_builtin
    warnings = [] #リセット
    number_of_notes = 0
    p = open(open_path, "r", encoding="utf-8")
    lines = p.readlines()

    lines_val = 0
    for line in lines:
        if line.startswith("sound_source_dir: "):
            singer_path = line[18:].strip() # singer: を除いてstripで空白削除
        elif line.startswith("output_dir: "):
            if is_pre_render:
                if line[12:].strip() != "":
                    out_dir = os.path.dirname(line[12:].strip())
                    if os.path.basename(out_dir) == "bounced":
                        out_dir = os.path.dirname(out_dir)
                    output_file = os.path.join(out_dir, "pre_render.wav")
                    # replace backward slash for consistency if we want but os.path is better
                    output_file = output_file.replace("\\", "/") # keep path style unified
                else:
                    output_file = "pre_render.wav"
            else:
                if line[12:].strip() != "":
                    output_file = line[12:].strip() # output_dir: を除いてstripで空白削除
                else:
                    output_file = lines[0][6:].strip() + "_MixDown_auto_named.wav"
        elif line.startswith("buffer_size: "):
            buffer_size = int(line[13:].strip())
        elif line.startswith("notes:"):
            start_note = lines_val
        elif line.startswith("duration:"):
            total_samples = int(line[9:].strip()) #duration:を除いてstripで空白削除
            duration_sec = total_samples / fs
        elif line.startswith("end:"):
            end_note = lines_val

        if line.startswith("- "):
            number_of_notes += 1
        lines_val += 1

    #print("number_of_notes: " + str(number_of_notes))

    if Path(singer_path + "/settings/音素片表.json").exists():
        with open(singer_path + "/settings/音素片表.json", "r", encoding="utf-8") as f:
            texts = json.load(f)
    else:
        with open(my_path + "/settings/音素片表.json", "r", encoding="utf-8") as f:
            texts = json.load(f)
            
    if Path(singer_path + "/settings/音階hz表.json").exists():
        with open(singer_path + "/settings/音階hz表.json", "r", encoding="utf-8") as f:
            tones = json.load(f)
    else:
        with open(my_path + "/settings/音階hz表.json", "r", encoding="utf-8") as f:
            tones = json.load(f)

    with open(my_path + "/settings/音素片表.json", "r", encoding="utf-8") as f:
        texts_builtin = json.load(f)


def find_pitch_period(x, fs=44100):
    min_lag = int(fs / 1000)
    max_lag = int(fs / 70)
    
    if len(x) < max_lag * 2:
        return fs // 200 # 適当なフォールバック
        
    analyze_len = int(min(len(x), max_lag * 4))
    corr_part = x[-analyze_len:]
    
    corr = np.correlate(corr_part, corr_part, mode='full')
    corr = corr[len(corr)//2:]
    
    if len(corr) <= max_lag:
        max_lag = len(corr) - 1
        
    if min_lag >= max_lag:
        return max_lag
        
    lengths = len(corr_part) - np.arange(len(corr))
    lengths[lengths <= 0] = 1 
    corr_norm = corr / lengths
    
    valid_corr = corr_norm[min_lag:max_lag]
    best_lag = min_lag + np.argmax(valid_corr)
    
    return best_lag


def extend_audio_with_crossfade(x, duration, buffer_size, fs=44100):
    if len(x) >= duration:
        return x[:duration]
        
    if len(x) < 3:
        repeat_num = duration // len(x) + 1
        return np.tile(x, repeat_num)[:duration]
        
    period = find_pitch_period(x, fs)
    
    # フェード50ms、ループ150msを基本とする。波形のピッチに正確に合わせることでノイズを防ぐ
    fade_len = max(1, int(0.05 * fs) // period) * period
    loop_len = max(2, int(0.15 * fs) // period) * period
    
    while loop_len + fade_len > len(x):
        if fade_len > period:
            fade_len -= period
        else:
            loop_len -= period
            
        if loop_len <= fade_len or loop_len <= 0:
            fade_len = len(x) // 3
            loop_len = len(x) - fade_len
            break
            
    loop_part = x[-loop_len:]
    
    fade_in = np.linspace(0, 1, fade_len)
    fade_out = np.linspace(1, 0, fade_len)
    
    result = np.zeros(duration + loop_len, dtype=np.float64)
    result[:len(x)] = x
    
    write_pos = len(x) - fade_len
    
    while write_pos < duration:
        result[write_pos : write_pos + fade_len] = \
            result[write_pos : write_pos + fade_len] * fade_out + \
            loop_part[:fade_len] * fade_in
            
        rest_len = loop_len - fade_len
        result[write_pos + fade_len : write_pos + loop_len] = loop_part[fade_len:]
        
        write_pos += rest_len
        
    return result[:duration]


def get_note(i, lines_array, start_n):
    base = start_n + i * 6 + 2
    position = int(lines_array[base][12:])
    duration = int(lines_array[base + 1][12:])
    pitch_str = lines_array[base + 2][8:].strip()
    lyric = lines_array[base + 3][9:].strip()
    bend_first = float(lines_array[base + 4][13:])
    bend_second = float(lines_array[base + 5][14:])
    pitch = tones[pitch_str] if pitch_str in tones else 440.0
    return {
        'position': position,
        'duration': duration,
        'pitch': pitch,
        'pitch_str': pitch_str,
        'lyric': lyric,
        'bend_first': bend_first,
        'bend_second': bend_second
    }


#convertに移した(全部ではない)
"""
def get_phoneme(lyric, duration):
    if lyric in texts:
        input_file = singer_path + "/単独音/" + texts[lyric] + ".wav"
    elif lyric in texts_builtin:
        input_file = singer_path + "/単独音/" + texts_builtin[lyric] + ".wav"
    elif lyric + ".wav" in os.listdir(singer_path + "/単独音/"):
        input_file = singer_path + "/単独音/" + lyric + ".wav"
    else:
        input_file = singer_path + "/単独音/a.wav"
        warnings.append(f"Warning: Lyric '{lyric}' not found in texts or as a wav file. Using 'a' as default.")

    x, file_fs = sf.read(input_file)
    x = x.astype(np.float64)
    return extend_audio_with_crossfade(x, duration, buffer_size)
"""


def connect_phonemes_list(notes):
    sound_list = []
    for n in notes:
        x, file_fs = sf.read(n["lyric"])
        x = x.astype(np.float64)
        x = extend_audio_with_crossfade(x, n["duration"], buffer_size)
        sound_list.append(x)
    return np.concatenate(sound_list) if sound_list else np.array([], dtype=np.float64)


def synthesize_chunk(sound_chunk, notes_chunk, chunk_start_sample, frame_period):
    if len(sound_chunk) == 0:
        return np.array([], dtype=np.float64)
    
    f0_chunk, t_arr = pw.dio(sound_chunk, fs, frame_period=frame_period)
    f0_chunk = pw.stonemask(sound_chunk, f0_chunk, t_arr, fs)
    sp_chunk = pw.cheaptrick(sound_chunk, f0_chunk, t_arr, fs)
    ap_chunk = pw.d4c(sound_chunk, f0_chunk, t_arr, fs)
    
    blocky_f0 = np.copy(f0_chunk)
    boundaries = set()
    note_mask = np.zeros(len(blocky_f0), dtype=bool)
    
    bend_first_map = {}
    bend_second_map = {}
    intervals = []
    
    for n in notes_chunk:
        rel_pos = n['position'] - chunk_start_sample
        s_idx = int(rel_pos / (fs * frame_period / 1000))
        e_idx = int((rel_pos + n['duration']) / (fs * frame_period / 1000))
        
        is_note = False if n["lyric"].split("/")[-1] == "r.wav" else True
        
        vis_s_idx = max(0, s_idx)
        vis_e_idx = min(len(blocky_f0), e_idx)
        if vis_s_idx < vis_e_idx:
            blocky_f0[vis_s_idx:vis_e_idx] = n['pitch']
            note_mask[vis_s_idx:vis_e_idx] = is_note
            
        intervals.append((s_idx, e_idx, n['pitch'], is_note))
        
        boundaries.add(s_idx)
        bend_second_map[s_idx] = n.get('bend_second', 0.05)
        
        boundaries.add(e_idx)
        bend_first_map[e_idx] = n.get('bend_first', 0.05)
                
    smoothed_f0 = np.copy(blocky_f0)
    
    def get_pitch_and_mask(idx):
        for s, e, p, is_n in intervals:
            if s <= idx < e:
                return p, is_n
        return 0.0, False
    
    for b_idx in sorted(list(boundaries)):
        v1, is_note1 = get_pitch_and_mask(b_idx - 1)
        v2, is_note2 = get_pitch_and_mask(b_idx)
        
        if not (is_note1 and is_note2):
            continue
            
        diff = v2 - v1
        if diff == 0:
            continue
            
        bend_first = bend_first_map.get(b_idx, 0.05)
        bend_second = bend_second_map.get(b_idx, 0.05)
        
        frames_before = int(max(0, bend_first * 1000 / frame_period))
        frames_after = int(max(0, bend_second * 1000 / frame_period))
        trans_frames = frames_before + frames_after
        
        if trans_frames == 0:
            continue
            
        sig_curve = 1 / (1 + np.exp(-np.linspace(-5, 5, trans_frames)))
        
        start = b_idx - frames_before
        end = b_idx + frames_after
        
        vis_start = max(0, start)
        vis_end = min(len(blocky_f0), end)
        
        if vis_start < vis_end:
            idx_range = np.arange(vis_start, vis_end)
            sig_idx = idx_range - start
            
            mask_less = idx_range < b_idx
            mask_greater_eq = idx_range >= b_idx
            
            if np.any(mask_less):
                smoothed_f0[idx_range[mask_less]] += diff * sig_curve[sig_idx[mask_less]]
            if np.any(mask_greater_eq):
                smoothed_f0[idx_range[mask_greater_eq]] += diff * (sig_curve[sig_idx[mask_greater_eq]] - 1.0)
                
    f0_chunk[:] = smoothed_f0[:]
            
    return pw.synthesize(f0_chunk, sp_chunk, ap_chunk, fs, frame_period=frame_period)


def synthesis(open_path, pre_render, bend_changed):
    global is_pre_render, y, output_file, sound, last_singer_path, singer_path
    is_pre_render = pre_render
    
    load_projectfile(open_path)
    
    notes = [get_note(i, lines, start_note) for i in range(number_of_notes)]
    
    cache = _synth_cache[pre_render]
    #frame_period = 10.0 if pre_render else 5.0
    frame_period = 10.0 #謎のノイズ対策でとりあえずいつでも10
    
    if cache is None or cache['open_path'] != open_path or len(notes) == 0 or last_singer_path != singer_path:
        # Full synthesis
        sound = connect_phonemes_list(notes)
        y = synthesize_chunk(sound, notes, 0, frame_period)
        last_singer_path = singer_path
    else:
        prev_notes = cache['notes']
        prev_sound = cache['sound']
        prev_y = cache['y']
        
        # Diff notes
        left = 0
        min_len = min(len(notes), len(prev_notes))
        #左から違うところまで
        while left < min_len and notes[left] == prev_notes[left]:
            left += 1
            
        if left == len(notes) and left == len(prev_notes):
            # No changes
            y = prev_y
            output_file = os.path.abspath(output_file)
            sf.write(output_file, y, fs)
            if pre_render:
                return output_file, warnings
            return output_file
            
        # 変更が見つかった場合、曲線ずれ対策で一つ左のノートから再合成する
        if left > 1:
            left -= 2
        elif left > 0:
            left -= 1
            
        right_new = len(notes) - 1
        right_prev = len(prev_notes) - 1
        #右から違うところまで
        while right_new >= left and right_prev >= left and notes[right_new] == prev_notes[right_prev]:
            right_new -= 1
            right_prev -= 1
            
        # 曲線ずれ対策で一つ右のノートまで再合成する
        if right_new < len(notes) - 2:
            right_new += 2
        elif right_new < len(notes) - 1:
            right_new += 1
        if right_prev < len(prev_notes) - 2:
            right_prev += 2
        elif right_new < len(prev_notes) - 1:
            right_prev +=1
            
        start_sample = notes[left]['position'] if left < len(notes) else total_samples
        if right_new >= left:
            end_sample = notes[right_new]['position'] + notes[right_new]['duration']
        else:
            end_sample = start_sample
            
        old_start_sample = prev_notes[left]['position'] if left < len(prev_notes) else cache['total_samples']
        if right_prev >= left:
            old_end_sample = prev_notes[right_prev]['position'] + prev_notes[right_prev]['duration']
        else:
            old_end_sample = old_start_sample
            
        # Rebuild sound for changed part
        changed_notes = notes[left : right_new + 1]
        changed_sound = connect_phonemes_list(changed_notes)
        
        #合成
        sound = np.concatenate((
            prev_sound[:start_sample],
            changed_sound,
            prev_sound[old_end_sample:]
        ))
        
        pad_left = min(start_sample, int(0.1 * fs))
        analyze_start = start_sample - pad_left
        
        # WORLDのフレームグリッド(10ms = 441サンプル)に揃えることでピッチ変更のタイミングズレを防ぐ
        grid_size = int(fs * 10 / 1000)
        analyze_start = int(analyze_start / grid_size) * grid_size
        pad_left = start_sample - analyze_start
        
        pad_right_new = min(total_samples - end_sample, int(0.1 * fs))
        pad_right_old = min(cache['total_samples'] - old_end_sample, int(0.1 * fs))
        
        analyze_end = end_sample + pad_right_new
        
        analysis_pad_samples = int(0.1 * fs)
        actual_analyze_start = max(0, analyze_start - analysis_pad_samples)
        actual_analyze_start = int(actual_analyze_start / grid_size) * grid_size
        extra_left = analyze_start - actual_analyze_start
        
        actual_analyze_end = min(len(sound), analyze_end + analysis_pad_samples)
        extra_right = actual_analyze_end - analyze_end
        extra_right = int(extra_right / grid_size) * grid_size
        actual_analyze_end = analyze_end + extra_right
        
        sound_chunk = sound[actual_analyze_start : actual_analyze_end]
        y_chunk_full = synthesize_chunk(sound_chunk, notes, actual_analyze_start, frame_period)
        
        if extra_left > 0 and extra_right > 0:
            y_chunk = y_chunk_full[extra_left : -extra_right]
        elif extra_left > 0:
            y_chunk = y_chunk_full[extra_left:]
        elif extra_right > 0:
            y_chunk = y_chunk_full[:-extra_right]
        else:
            y_chunk = y_chunk_full
        
        # Splice y_chunk into prev_y
        new_y_list = []
        y_chunk_core = y_chunk
        
        if analyze_start > 0:
            new_y_list.append(prev_y[:analyze_start])
            
        if pad_left > 0:
            fade_out = np.linspace(1, 0, pad_left)
            fade_in = np.linspace(0, 1, pad_left)
            old_part = prev_y[analyze_start : analyze_start + pad_left]
            new_part = y_chunk_core[:pad_left]
            
            min_len_pad = min(len(old_part), len(new_part))
            if min_len_pad > 0:
                cf = old_part[:min_len_pad] * fade_out[:min_len_pad] + new_part[:min_len_pad] * fade_in[:min_len_pad]
                new_y_list.append(cf)
                y_chunk_core = y_chunk_core[min_len_pad:]
            
        if pad_right_new > 0:
            cf_len = min(pad_right_new, len(y_chunk_core))
            new_part = y_chunk_core[-cf_len:] if cf_len > 0 else np.array([])
            y_chunk_core = y_chunk_core[:-cf_len] if cf_len > 0 else y_chunk_core
            
            old_part = prev_y[old_end_sample : old_end_sample + pad_right_old]
            min_len_pad = min(len(old_part), len(new_part))
            
            if min_len_pad > 0:
                fade_out = np.linspace(1, 0, min_len_pad)
                fade_in = np.linspace(0, 1, min_len_pad)
                cf = new_part[:min_len_pad] * fade_out[:min_len_pad] + old_part[:min_len_pad] * fade_in[:min_len_pad]
                
                new_y_list.append(y_chunk_core)
                new_y_list.append(cf)
            else:
                new_y_list.append(y_chunk_core)
        else:
            new_y_list.append(y_chunk_core)
            
        if old_end_sample + pad_right_old < len(prev_y):
            new_y_list.append(prev_y[old_end_sample + pad_right_old :])
            
        y = np.concatenate(new_y_list) if new_y_list else np.array([], dtype=np.float64)

    output_file = os.path.abspath(output_file)
    sf.write(output_file, y, fs)
    
    _synth_cache[pre_render] = {
        'open_path': open_path,
        'notes': notes,
        'sound': sound.copy(),
        'y': y.copy(),
        'duration_sec': duration_sec,
        'total_samples': total_samples
    }
    
    if pre_render:
        return output_file, warnings
    return output_file