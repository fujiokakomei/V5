#notes[]からyjspへの変換モジュール
import os
from datetime import datetime
import json
from pathlib import Path

def convert_notes_to_yjsp(notes, file_path, singer_path, bpm, grid_width, user_named, user_named_output_path):
    #未実装のやつら
    comment = ""
    sampling_rate = 44100 #固定
    buffer_size = 512 #固定
    beat_per_bar = 4 #固定
    warnings = []

    my_path = Path(__file__).resolve().parent

    if file_path is not None:
        name = Path(file_path).name
        file_path = Path(file_path) / "notes.json"
        output_path = file_path.with_name(f"{name}.yjsp")
        output_dir = file_path.parent / "bounced" / f"{name}.wav"
    else:
        name = "output_auto_saved"
        file_path = Path("notes.json")
        output_path = Path(f"{name}.yjsp")
        output_dir = Path(f"{name}.wav")

    if user_named_output_path is not None:
        if not user_named_output_path.endswith(".wav"):
            user_named_output_path = f"{user_named_output_path}.wav"
        user_named_output_path = Path(user_named_output_path).expanduser().resolve()

    #絶対パスに一応変換
    file_path = file_path.resolve()
    output_path = output_path.resolve()
    output_dir = output_dir.resolve()

    #bouncedフォルダがなければ作る
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    #output_dirがあったら
    if output_dir.exists():
        output_dir = output_dir.with_name(f"{output_dir.stem}_{datetime.now().strftime('%Y-%m%d-%H-%M-%S')}{output_dir.suffix}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"name: {name}\n")
        f.write(f"sound_source_dir: {singer_path}\n")
        f.write(f"output_dir: {output_dir if not user_named else user_named_output_path}\n")
        f.write(f"comment: {comment}\n")
        f.write(f"sampling_rate: {sampling_rate}\n")
        f.write(f"buffer_size: {buffer_size}\n")
        f.write(f"bpm: {bpm}\n")
        f.write(f"beat_per_bar: {beat_per_bar}\n")

        f.write("\n")

        f.write("notes:\n")
        #duration計算 grid_widthから
        duration = int((60 / bpm *(grid_width / 40)) * sampling_rate)
        f.write(f"duration: {duration}\n")

        #時間方向に被ってるノートを削除
        #ノートの開始時間でソート
        notes.sort(key=lambda x: x["x"])
        last_note_end = -1
        notes_to_write = []
        for note in notes:
            note_start= note["x"]
            note_end = note["x"] + note["w"]
            if note_start >= last_note_end:
                notes_to_write.append(note)
                last_note_end = note_end
        deleted = len(notes) - len(notes_to_write)
        if deleted > 0:
            warnings.append(f"Deleted {deleted} notes due to overlap.")

        #x+wが次のノートのxより小さい場合、間にrを入れる
        for i in range(len(notes_to_write)-2, -1, -1):
            note=notes_to_write[i]
            next_note=notes_to_write[i+1]
            if note["x"] + note["w"] < next_note["x"]:
                rest_note = {
                    "x": note["x"] + note["w"],
                    "y": 0,
                    "w": next_note["x"] - (note["x"] + note["w"]),
                    "h": 20,
                    "lyric": "r",
                    "bend_first": 0,
                    "bend_second": 0
                }
                notes_to_write.insert(i+1, rest_note)
        #先頭ノートのxが0でない場合、先頭にrを入れる
        if len(notes_to_write) > 0 and notes_to_write[0]["x"] > 0:
            rest_note = {
                "x": 0,
                "y": 0,
                "w": notes_to_write[0]["x"],
                "h": 20,
                "lyric": "r",
                "bend_first": 0,
                "bend_second": 0
            }
            notes_to_write.insert(0, rest_note)
        #最後のノートのx+wがgrid_widthより小さい場合、最後にrを入れる
        if len(notes_to_write) > 0 and notes_to_write[-1]["x"] + notes_to_write[-1]["w"] < grid_width:
            rest_note = {
                "x": notes_to_write[-1]["x"] + notes_to_write[-1]["w"],
                "y": 0,
                "w": grid_width - (notes_to_write[-1]["x"] + notes_to_write[-1]["w"]),
                "h": 20,
                "lyric": "r",
                "bend_first": 0,
                "bend_second": 0
            }
            notes_to_write.append(rest_note)


        singer_texts_path = Path(singer_path) / "settings" / "音素片表.json"
        #builtin_texts_path = my_path / "settings" / "音素片表.json"
        if singer_texts_path.exists():
            with open(singer_texts_path, "r", encoding="utf-8") as f1:
                texts = json.load(f1)
        """
        else:
            with open(builtin_texts_path, "r", encoding="utf-8") as f1:
                texts = json.load(f1)
        with open(builtin_texts_path, "r", encoding="utf-8") as f2:
            texts_builtin = json.load(f2)
        """

        
        #一拍が何サンプルか計算
        samples_per_beat = (60 / bpm) * sampling_rate


        voice_dir = Path(singer_path) / "単独音"
        have_oto_ini = False
        oto_ini_path = voice_dir / "oto.ini"
        if oto_ini_path.exists():
            with open(oto_ini_path, "r", encoding="utf-8") as oto_ini:
                oto_ini_lines = oto_ini.readlines()
            have_oto_ini = True
        else:
            warnings.append("Warning: oto.ini not found in singer's 単独音 directory.")

        note_number = 0
        for note in notes_to_write:
            #positionの計算
            #一拍は40px
            position = (note["x"] / 40) * samples_per_beat

            #durationの計算
            duration = (note["w"] / 40) * samples_per_beat

            #toneの計算
            tone = 84 - note["y"] // 20


            #発音タイミング修正
            lyric = note['lyric']
            lyric_path = ""
            if lyric in texts:
                lyric_path = voice_dir / f"{texts[lyric]}.wav"
            #elif lyric in texts_builtin:
            #    lyric_path = voice_dir / f"{texts_builtin[lyric]}.wav"
            elif (voice_dir / f"{lyric}.wav").exists():
                lyric_path = voice_dir / f"{lyric}.wav"
            else:
                lyric_path = voice_dir / "a.wav"
                warnings.append(f"Warning: Lyric '{lyric}' not found in texts or as a wav file. Using 'a' as default.")
            
            lyric_path.resolve()

            lyric_wav_name = lyric_path.name
            if have_oto_ini:
                for line in oto_ini_lines:
                    if line.startswith(lyric_wav_name + "="):
                        this_line_offset = line.strip().split("=")[1].split(",")[1] #単位はミリ秒
                        #positionから引く
                        position -= int(float(this_line_offset) / 1000.0 * sampling_rate)
                        position = max(0, position)
                        #durationに足す
                        duration += int(float(this_line_offset) / 1000.0 * sampling_rate)
                        #次のノートのoffset分だけdurationを削る
                        if note_number < len(notes_to_write) - 1:
                            next_note = notes_to_write[note_number+1]
                            next_lyric = next_note['lyric']
                            next_lyric_path = ""
                            if next_lyric in texts:
                                next_lyric_path = voice_dir / f"{texts[next_lyric]}.wav"
                            #elif next_lyric in texts_builtin:
                            #    next_lyric_path = voice_dir / f"{texts_builtin[next_lyric]}.wav"
                            elif (voice_dir / f"{next_lyric}.wav").exists():
                                next_lyric_path = voice_dir / f"{next_lyric}.wav"
                            else:
                                next_lyric_path = voice_dir / "a.wav"
                                warnings.append(f"Warning: Lyric '{next_lyric}' not found in texts or as a wav file. Using 'a' as default.")
                            
                            next_lyric_wav_name = next_lyric_path.name
                            for line2 in oto_ini_lines:
                                if line2.startswith(next_lyric_wav_name + "="):
                                    next_line_offset = line2.strip().split("=")[1].split(",")[1] #単位はミリ秒
                                    duration -= int(float(next_line_offset) / 1000.0 * sampling_rate)
                                    duration = max(0, duration)
                                    break
                        break
                    


            f.write(f"- position: {int(position)}\n")
            f.write(f"  duration: {int(duration)}\n")
            f.write(f"  tone: {int(tone)}\n")
            #f.write(f"  lyric: {note['lyric']}\n")
            #synthesisのget_phonemeをこっちに移す
            #下の塊を上に持ってきてduration書き込みの時点でlyricのpathを見れるようにしてduration書き込み時にoto.iniを確認して発音を早める場合durationをいじる
            f.write(f"  lyric: {lyric_path}\n")
            
            f.write(f"  bend_first: {note['bend_first']}\n")
            f.write(f"  bend_second: {note['bend_second']}\n")
            """
            lyric = note['lyric']
            lyric_path = ""
            if lyric in texts:
                f.write(f"  lyric: {singer_path}/単独音/{texts[lyric]}.wav\n")
            elif lyric in texts_builtin:
                f.write(f"  lyric: {singer_path}/単独音/{texts_builtin[lyric]}.wav\n")
            elif lyric + ".wav" in os.listdir(singer_path + "/単独音/"):
                f.write(f"  lyric: {singer_path}/単独音/{lyric}.wav\n")
            else:
                f.write(f"  lyric: {singer_path}/単独音/a.wav\n")
                warnings.append(f"Warning: Lyric '{lyric}' not found in texts or as a wav file. Using 'a' as default.")
            """
            note_number += 1


        f.write("end:\n")

    return output_path, warnings
