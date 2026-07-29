import dearpygui.dearpygui as dpg
import numpy as np
import json
import time
from PIL import Image
from pathlib import Path
import os
import sys
import subprocess
import platform
import sounddevice as sd
import soundfile as sf
import simpleaudio
import atexit
import copy
import threading
#自作モジュール
import convert
import synthesis




# notes_changed と is_saved を追加した関数など
# set_bpm()
# handle_input()のノート削除部分
# handle_input()のdragging_noteのresizing部分
# handle_input()のdragging_noteの移動部分(selected)
# handle_input()のdragging_noteの移動部分(selected else)
# handle_input()のノート追加部分
# change_lyric_callback()
# menu_new() is_savedはここではTrueにする
# open_file_callback() is_savedはここではTrueにする
# menu_undo()
# menu_redo()
# menu_delete()
# menu_paste()
# update()のif singer_changedのところ

# is_savedのみset_locator_R()とset_locator_L()
# is_savedのみhandle_input()のdragging_locator_R/Lのところ
# menu_save()とsave_file_callback()でis_saved=True




#=========================変数など=========================
#----------------UI----------------
#ピアノロール本体と再生コントロール
GRID_WIDTH = 1920 #時間方向
GRID_HEIGHT = 1680 #C1~B7
CELL_W = 40 #四分音符の幅
CELL_H = 20 #ノートの高さ
grid_w = CELL_W / 2.0 #現在のグリッド幅 デフォルト1/8
#その他ピアノロール関連
is_playing = False
playhead_x = 0.0
dragging_playhead = False
locator_R = 0.0
locator_L = 0.0
dragging_locator_R = False
dragging_locator_L = False
is_auto_scroll = False

resizing = False
zoom_x = 3.0
zoom_y = 1.0
dragging_note = None
offset_x = 0.0
editing_bend_first_note = None
editing_bend_second_note = None
editing_bend_first = False
editing_bend_second = False
bend_changed = False #応急処置

current_tool = "Select"

box_selecting = False
selection_start = (0, 0)
selection_end = (0, 0)

bpm = 120
last_time = 0.0

notes = []
clipboard = []
current_file_path = None

my_path = os.path.dirname(os.path.abspath(__file__))
UI_PREFS_PATH = Path(my_path) / "settings" / "ui_prefs.json"

# 表示言語（Preferences で変更） / バウンス範囲は内部フラグで保持（ラジオは言語依存のため）
ui_language = "ja"
bnc_range_is_full = True

LANG_COMBO_LABEL = {"ja": "日本語", "en": "English"}

VIEW_LAYER_NOTE = "note"
VIEW_LAYER_LYRIC = "lyric"
VIEW_LAYER_PITCH = "pitch"
VIEW_LAYERS = (VIEW_LAYER_NOTE, VIEW_LAYER_LYRIC, VIEW_LAYER_PITCH)

TOOL_INTERNAL = ("Select", "Pen", "Eraser", "Pitch Edit")

UI_STR = {}
with open(Path(my_path) / "locale" / "lang.json", "r", encoding="utf-8") as f:
    UI_STR = json.load(f)


def tr(key):
    return UI_STR.get(ui_language, UI_STR["ja"]).get(key) or UI_STR["ja"].get(key) or key


def load_ui_prefs():
    global ui_language
    try:
        p = Path(UI_PREFS_PATH)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            lang = data.get("display_language", "ja")
            if lang in UI_STR:
                ui_language = lang
    except Exception:
        pass


def save_ui_prefs():
    try:
        Path(UI_PREFS_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(UI_PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump({"display_language": ui_language}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def tool_combo_labels():
    return [tr("tool_select"), tr("tool_pen"), tr("tool_eraser"), tr("tool_pitch_edit")]


def tool_label_for_current():
    try:
        i = TOOL_INTERNAL.index(current_tool)
        return tool_combo_labels()[i]
    except ValueError:
        return tool_combo_labels()[0]


def tool_combo_callback(sender, app_data):
    labels = tool_combo_labels()
    try:
        idx = labels.index(app_data)
    except ValueError:
        return
    set_tool(None, TOOL_INTERNAL[idx])


def on_bnc_range_changed(sender, app_data):
    global bnc_range_is_full
    bnc_range_is_full = app_data == tr("bnc_whole")


def on_display_language_changed(sender, app_data):
    global ui_language
    for code, label in LANG_COMBO_LABEL.items():
        if label == app_data:
            ui_language = code
            break
    save_ui_prefs()
    apply_ui_language()


def fmt_path_line(path_val):
    if path_val:
        return f"{tr('path_prefix')}{path_val}"
    return tr("path_prefix_empty")


def build_view_layer_checkboxes():
    dpg.delete_item("draw_item_checkbox", children_only=True)
    labels = (tr("view_note"), tr("view_lyric"), tr("view_pitch_curve"))
    defaults = (is_notes_draw, is_lyric_draw, is_pitch_curve_draw)
    for layer, label, default in zip(VIEW_LAYERS, labels, defaults):
        dpg.add_spacer(parent="draw_item_checkbox")
        dpg.add_checkbox(label=label, callback=set_draw_items, user_data=layer, default_value=default, parent="draw_item_checkbox")


def apply_ui_language():
    global singer_path
    # メニュー
    for tag, key in (
        ("menu_file", "menu_file"), ("menu_edit", "menu_edit"), ("menu_view", "menu_view"), ("menu_tools", "menu_tools"), ("menu_window", "menu_window"),
        ("mi_new", "mi_new"), ("mi_open", "mi_open"), ("mi_save", "mi_save"), ("mi_save_as", "mi_save_as"), ("mi_export", "mi_export"), ("mi_quit", "mi_quit"),
        ("mi_undo", "mi_undo"), ("mi_redo", "mi_redo"), ("mi_cut", "mi_cut"), ("mi_copy", "mi_copy"), ("mi_paste", "mi_paste"), ("mi_delete", "mi_delete"),
        ("mi_controls", "mi_controls"), ("mi_piano_roll", "mi_piano_roll"), ("mi_export_view", "mi_export"), ("mi_singer_setting", "mi_singer_setting"),
        ("mi_singer", "mi_singer"), ("mi_preferences", "mi_preferences"),
        ("mi_maximize", "mi_maximize"), ("mi_minimize", "mi_minimize"), ("mi_fullscreen", "mi_fullscreen"),
    ):
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, label=tr(key))
    # ウィンドウ・子ウィンドウ
    for tag, key in (
        ("controls_drawlist", "child_controls"), ("Piano_Roll", "child_piano_roll"), ("history_child", "child_history"),
        ("singer_setting_window", "win_singer_setting"), ("lyric_input_window", "win_lyric_input"),
        ("rendering_window", "win_rendering"), ("output_path_window", "win_output_path"), ("bnc_window", "win_bnc"),
        ("lyrics_window", "win_lyrics"), ("close_app_window", "win_confirm"), ("new_app_window", "win_confirm"), ("open_app_window", "win_confirm"),
        ("preferences", "win_preferences"),
    ):
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, label=tr(key))
    if dpg.does_item_exist("main_window"):
        dpg.configure_item("main_window", label="Main Window")
    # コントロール部テキスト・ボタン
    if dpg.does_item_exist("info_text"):
        cur = dpg.get_value("info_text")
        if cur in (UI_STR["ja"]["info_no_selected"], UI_STR["en"]["info_no_selected"], "No selected"):
            dpg.set_value("info_text", tr("info_no_selected"))
    if dpg.does_item_exist("tooltip_text"):
        cur_t = dpg.get_value("tooltip_text")
        if cur_t in (UI_STR["ja"]["tip_no_singer"], UI_STR["en"]["tip_no_singer"], "No singer has been selected.\nPlease select a singer."):
            dpg.set_value("tooltip_text", tr("tip_no_singer"))
    for tag, key in (("btn_singer_setting", "btn_singer_setting"), ("btn_edit_lyrics", "btn_edit_lyrics"), ("play_btn", "btn_play"), ("stop_play_btn", "btn_stop")):
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, label=tr(key))
    for tag, key in (("lbl_locator", "lbl_locator"), ("lbl_l", "lbl_l"), ("lbl_r", "lbl_r"), ("lbl_volume", "lbl_volume"), ("lbl_bpm", "lbl_bpm"),
                     ("lbl_grid", "lbl_grid"), ("lbl_tool", "lbl_tool")):
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, tr(key))
    if dpg.does_item_exist("volume_tip_text"):
        dpg.set_value("volume_tip_text", tr("tip_volume"))
    if dpg.does_item_exist("tool_tip_text"):
        dpg.set_value("tool_tip_text", tr("tip_tools"))
    if dpg.does_item_exist("auto_scroll_chk"):
        dpg.configure_item("auto_scroll_chk", label=tr("chk_auto_scroll"))
    if dpg.does_item_exist("view_combo"):
        dpg.configure_item("view_combo", label=tr("btn_view_combo"))
    if dpg.does_item_exist("tool_combo"):
        dpg.configure_item("tool_combo", items=tool_combo_labels())
        dpg.set_value("tool_combo", tool_label_for_current())
    if dpg.does_item_exist("known_singers_hdr"):
        dpg.set_value("known_singers_hdr", tr("lbl_known_singers"))
    if dpg.does_item_exist("select_singer_main_btn"):
        dpg.configure_item("select_singer_main_btn", label=tr("btn_select_add_singer"))
    if dpg.does_item_exist("lyric_input"):
        dpg.configure_item("lyric_input", label=tr("lbl_lyric"), hint=tr("hint_lyric"))
    if dpg.does_item_exist("lyric_input_help"):
        dpg.set_value("lyric_input_help", tr("lyric_input_help"))
    if dpg.does_item_exist("lyric_cancel_btn"):
        dpg.configure_item("lyric_cancel_btn", label=tr("btn_cancel"))
    if dpg.does_item_exist("rendering_text"):
        dpg.set_value("rendering_text", tr("txt_rendering"))
    if dpg.does_item_exist("open_folder_btn"):
        dpg.configure_item("open_folder_btn", label=tr("btn_open_folder"))
    if dpg.does_item_exist("ok_btn"):
        dpg.configure_item("ok_btn", label=tr("btn_ok"))
    if dpg.does_item_exist("bnc_range"):
        sel = tr("bnc_whole") if bnc_range_is_full else tr("bnc_selection")
        dpg.configure_item("bnc_range", items=[tr("bnc_whole"), tr("bnc_selection")])
        dpg.set_value("bnc_range", sel)
    if dpg.does_item_exist("output_path_btn"):
        dpg.configure_item("output_path_btn", label=tr("btn_output_path"))
    if dpg.does_item_exist("bnc_btn"):
        dpg.configure_item("bnc_btn", label=tr("btn_bnc_export"))
    if dpg.does_item_exist("bnc_cancel_btn"):
        dpg.configure_item("bnc_cancel_btn", label=tr("btn_cancel"))
    if dpg.does_item_exist("lyrics_ok_btn"):
        dpg.configure_item("lyrics_ok_btn", label=tr("btn_ok"))
    if dpg.does_item_exist("lyrics_cancel_btn"):
        dpg.configure_item("lyrics_cancel_btn", label=tr("btn_cancel"))
    if dpg.does_item_exist("lyrics_hint_text"):
        dpg.set_value("lyrics_hint_text", tr("lyrics_hint"))
    for tag, key in (
        ("close_unsaved_text", "txt_unsaved"), ("new_unsaved_text", "txt_unsaved"), ("open_unsaved_text", "txt_unsaved"),
    ):
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, tr(key))
    for prefix in ("close", "new", "open"):
        for action, key in (("cancel", "btn_cancel"), ("save", "btn_save"), ("discard", "btn_discard")):
            t = f"{prefix}_{action}_btn"
            if dpg.does_item_exist(t):
                dpg.configure_item(t, label=tr(key))
    if dpg.does_item_exist("prefs_tab_playback"):
        dpg.configure_item("prefs_tab_playback", label=tr("prefs_tab_playback"))
    if dpg.does_item_exist("prefs_tab_display"):
        dpg.configure_item("prefs_tab_display", label=tr("prefs_tab_display"))
    if dpg.does_item_exist("output_device"):
        dpg.configure_item("output_device", label=tr("prefs_output_device"))
    if dpg.does_item_exist("prefs_lang_combo"):
        dpg.configure_item("prefs_lang_combo", label=tr("prefs_display_language"))
        dpg.set_value("prefs_lang_combo", LANG_COMBO_LABEL[ui_language])
    if dpg.does_item_exist("singer_path_text"):
        dpg.set_value("singer_path_text", fmt_path_line(singer_path))
    if dpg.does_item_exist("bnc_main_btn"):
        dpg.configure_item("bnc_main_btn", label=tr("btn_bnc"))
    if dpg.does_item_exist("draw_item_checkbox"):
        build_view_layer_checkboxes()
    # ファイルダイアログ
    if dpg.does_item_exist("open_file_dialog"):
        dpg.configure_item("open_file_dialog", label=tr("dlg_open_project"))
    if dpg.does_item_exist("save_file_dialog"):
        dpg.configure_item("save_file_dialog", label=tr("dlg_save_project"))
    if dpg.does_item_exist("select_singer_dialog"):
        dpg.configure_item("select_singer_dialog", label=tr("dlg_select_singer"))
    if dpg.does_item_exist("select_output_path"):
        dpg.configure_item("select_output_path", label=tr("dlg_select_wav"))


load_ui_prefs()

is_notes_draw = True
is_lyric_draw = True
is_pitch_curve_draw = True 
#音源などその他　合成はモジュールでやる
singer_path = None #デフォルトこれ
no_image_image = None
singer_changed = False
user_named = False
user_named_output_path = None
play_obj = None
pre_sound = None
changed_playhead = False #再生中に再生バー移動した時
notes_changed = False #ノート追加・削除・変更した時のみ再生前にレンダリング
is_saved = True #変更が保存されているか
is_opend = False #プロジェクトを開く、または新規作成した時にupdate()内のsinger_changedのとこのせいで未保存判定にされるのを防ぐ専用のフラグ
volume = 1
known_singers = [] #知っているシンガーのリスト
is_known_singer_added = False #知っているシンガーが追加されたか
#履歴　現在の状態を含める
notes_history = [[]] #ノートの履歴
setting_history = [[120, None, 0.0, 0.0]] #シンガーやbpmなどの設定の履歴
history_index = 0 #履歴(両方)のインデックス
history_notes_changed = False #履歴のノート変更フラグ
is_dragging_changed = False #ドラッグ等で変更があったか
previously_rendering = False #フレーム間の状態確認用

warnings = None

# バックグラウンドレンダリング用
is_rendering_background = False
pending_render = False
bg_pre_sound = None
bg_warnings_text = ""





#=========================関数など=========================
#----------------終了処理----------------
@atexit.register
def cleanup():
    global pre_sound
    if pre_sound and os.path.exists(pre_sound):
        os.remove(pre_sound)
        print(f"removed {pre_sound}")
        if os.path.exists(pre_sound.replace("pre_render.wav", "output_auto_saved.yjsp")):
            os.remove(pre_sound.replace("pre_render.wav", "output_auto_saved.yjsp"))
            print(f"removed {pre_sound.replace('pre_render.wav', 'output_auto_saved.yjsp')}")
    sd.stop()
#----------------ピアノロール関連----------------
def snap(value, grid):
    return int(value // grid) * grid

def set_zoom_x(sender, app_data):
    global zoom_x
    zoom_x = app_data

def set_zoom_y(sender, app_data):
    global zoom_y
    zoom_y = app_data

def set_quantize(sender, app_data):
    global grid_w
    if app_data == "1/4":
        grid_w = float(CELL_W)
    elif app_data == "1/8":
        grid_w = CELL_W / 2.0
    elif app_data == "1/16":
        grid_w = CELL_W / 4.0
    elif app_data == "1/32":
        grid_w = CELL_W / 8.0
    elif app_data == "1/64":
        grid_w = CELL_W / 16.0

def set_tool(sender, app_data):
    global current_tool
    current_tool = app_data

def add_measure(sender, app_data):
    global GRID_WIDTH
    GRID_WIDTH += CELL_W * 4

def remove_measure(sender, app_data):
    global GRID_WIDTH
    if GRID_WIDTH > CELL_W * 4:  # 最低1小節は残す
        GRID_WIDTH -= CELL_W * 4

#----------------再生コントロール関連----------------
def toggle_play(sender, app_data):
    global is_playing, last_time, pre_sound, playhead_x, notes_changed, singer_path, warnings
    if is_playing: return
    if dpg.does_item_exist("play_btn"):
        dpg.bind_item_theme("play_btn", "theme_play_active")

    if singer_path is None:
        dpg.set_value("output_path_text", tr("msg_please_select_singer"))
        resize_output_path_window()
        dpg.configure_item("output_path_window", show=True)
        dpg.configure_item("open_folder_btn", show=False)
        dpg.set_item_pos("ok_btn", (120, 100))
        if dpg.does_item_exist("play_btn"):
            dpg.bind_item_theme("play_btn", 0)
        return
    if not notes:
        dpg.set_value("output_path_text", tr("msg_no_notes"))
        resize_output_path_window()
        dpg.configure_item("output_path_window", show=True)
        dpg.configure_item("open_folder_btn", show=False)
        dpg.set_item_pos("ok_btn", (120, 100))
        if dpg.does_item_exist("play_btn"):
            dpg.bind_item_theme("play_btn", 0)
        return
    else:
        if is_rendering_background or pending_render or notes_changed:
            dpg.set_value("output_path_text", tr("msg_render_busy"))
            resize_output_path_window()
            dpg.configure_item("output_path_window", show=True)
            dpg.configure_item("open_folder_btn", show=False)
            dpg.set_item_pos("ok_btn", (120, 100))
            if dpg.does_item_exist("play_btn"):
                dpg.bind_item_theme("play_btn", 0)
            is_playing = False
            return
            
        samples_per_beat = (60 / bpm) * 44100
        start_sample = int(playhead_x / CELL_W * samples_per_beat)
        if pre_sound:
            try:
                sound, file_fs = sf.read(pre_sound)
                sound = sound.astype(np.float64)
                sound = sound * volume
                sd.play(sound[start_sample:], file_fs)
            except Exception as e:
                print(f"Play Error: {e}")
            
        is_playing = True
        last_time = time.time() # レンダリングに掛かった時間を無視するため、ここでリセット

def switch_auto_scroll():
    global is_auto_scroll
    is_auto_scroll = not is_auto_scroll
    #print(is_auto_scroll)


def stop_play(sender, app_data):
    global is_playing
    is_playing = False
    if dpg.does_item_exist("play_btn"):
        dpg.bind_item_theme("play_btn", 0)
    
    # 再生を停止
    sd.stop()

def rewind_play(sender, app_data):
    global playhead_x, changed_playhead
    playhead_x = 0.0
    changed_playhead = True

def set_bpm(sender, app_data):
    global bpm, notes_changed, history_notes_changed, is_saved
    bpm = app_data
    notes_changed = True
    history_notes_changed = True
    is_saved = False

def set_locator_R(sender, app_data):
    global locator_R, is_saved
    locator_R = app_data
    dpg.set_value("locator_r", locator_R)
    is_saved = False

def set_locator_L(sender, app_data):
    global locator_L, is_saved
    locator_L = app_data
    dpg.set_value("locator_l", locator_L)
    is_saved = False

def set_volume(sender, app_data):
    global volume
    volume = app_data

def set_draw_items(sender, app_data, user_data):
    global is_notes_draw, is_lyric_draw, is_pitch_curve_draw
    if user_data == VIEW_LAYER_NOTE:
        is_notes_draw = app_data
    elif user_data == VIEW_LAYER_LYRIC:
        is_lyric_draw = app_data
    elif user_data == VIEW_LAYER_PITCH:
        is_pitch_curve_draw = app_data

def set_view_combo(sender, app_data):
    #座標をセットして表示
    pos = dpg.get_item_rect_min("view_combo")
    height = dpg.get_item_rect_size("view_combo")[1]
    dpg.set_item_pos("draw_item_checkbox", [pos[0], pos[1] + height])
    dpg.configure_item("draw_item_checkbox", show=not dpg.is_item_shown("draw_item_checkbox"))

#----------------音源情報関連----------------
# 画像をDPG用のデータ形式に変換する関数
def get_image_data(file_path):
    img = Image.open(file_path).convert("RGBA")
    img = img.resize((50, 50), Image.Resampling.LANCZOS)
    return np.asarray(img, dtype=np.float32).flatten() / 255.0

#画像変更
def change_image_callback():
    # 新しい画像があったら読み込んでテクスチャを更新
    new_image = Path(singer_path) / "image.png"
    if new_image.exists():
        new_data = get_image_data(Path(singer_path) / "image.png")
    else:
        new_data = None
    if new_data is not None:
        dpg.set_value("singer_icon", new_data)
    else:
        dpg.set_value("singer_icon", get_image_data(Path(my_path) / "images" / "no_image.png"))

#音源変更関連
def singer_setting_callback():
    resize_singer_setting_window()
    dpg.show_item("singer_setting_window")
    #dpg.set_item_pos("singer_setting_window", dpg.get_mouse_pos())

def select_singer_button_callback(sender, app_data):
    dpg.show_item("select_singer_dialog")

def select_singer_callback(sender, app_data): #音源の新規追加(既存の音源かもしれないけど)時
    global singer_path, singer_changed, info_text, history_notes_changed, is_known_singer_added
    if "file_path_name" in app_data and app_data["file_path_name"]:
        singer_path = app_data["file_path_name"]
        dpg.set_value("singer_path_text", fmt_path_line(singer_path))
        singer_changed = True
        history_notes_changed = True
        add_known_singer_to_json(singer_path)
        is_known_singer_added = True #update内でset_known_singers_buttonsを呼び出すためのフラグ

def select_known_singer_callback(sender, app_data, user_data): #既知の音源を選択
    global singer_path, singer_changed, info_text, history_notes_changed
    singer_path = user_data
    dpg.set_value("singer_path_text", fmt_path_line(singer_path))
    singer_changed = True
    history_notes_changed = True


#既知の音源を追加
def add_known_singer(this_name, this_singer_path):
    if (Path(this_singer_path) / "image.png").exists():
        dpg.add_static_texture(width=50, height=50, default_value=get_image_data(Path(this_singer_path) / "image.png"), tag=f"known_singer_{this_name}", parent="known_singers_texture_registry")
    else:
        dpg.add_static_texture(width=50, height=50, default_value=get_image_data(Path(my_path) / "images" / "no_image.png"), tag=f"known_singer_{this_name}", parent="known_singers_texture_registry")
    #画像ボタンの下に名前
    dpg.add_group(horizontal=False, parent="known_singers_group", tag=f"known_singers_button_{this_name}")
    dpg.add_image_button(width=50, height=50, texture_tag=f"known_singer_{this_name}", callback=lambda s, a, u: select_known_singer_callback(s, a, u), user_data=this_singer_path, parent=f"known_singers_button_{this_name}")
    dpg.add_text(this_name, parent=f"known_singers_button_{this_name}")

def add_known_singer_to_json(this_singer_path):
    with open(Path(my_path) / "settings" / "singers.json", "r", encoding="utf-8") as f:
        known_singers_now = json.load(f) #音源の辞書 name: path
    this_name = "Unknown" #初期値
    if (Path(this_singer_path) / "character.txt").exists():
        with open(Path(this_singer_path) / "character.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > 0:
            for line in lines:
                if line.startswith("name="):
                    this_name = line[5:].strip()
                    break
            if this_name in known_singers_now:
                if this_name == "Unknown":
                    new_name = this_name + "_" + str(len(known_singers_now))
                    known_singers_now[new_name] = this_singer_path
                else:
                    return # すでに登録済み
            else:
                known_singers_now[this_name] = this_singer_path    
    else:
        new_name = this_name + "_" + str(len(known_singers_now))
        known_singers_now[new_name] = this_singer_path
    with open(Path(my_path) / "settings" / "singers.json", "w", encoding="utf-8") as f:
        json.dump(known_singers_now, f, ensure_ascii=False, indent=4)

def set_known_singers_buttons():
    global known_singers
    with open(Path(my_path) / "settings" / "singers.json", "r", encoding="utf-8") as f:
        known_singers = json.load(f) #音源の辞書 name: path
    dpg.delete_item("known_singers_texture_registry", children_only=True) #テクスチャも全消し
    dpg.delete_item("known_singers_group", children_only=True) #一旦全消し
    for name, path in known_singers.items():
        add_known_singer(name, path)

#レンダリング、再生関連(基本モジュール)
def show_bnc_window():
    resize_bnc_window()
    dpg.configure_item("bnc_window", show=True)

def rendering():
    global output_file, user_named, user_named_output_path
    if singer_path is None:
        dpg.set_value("output_path_text", tr("msg_please_select_singer"))
        resize_output_path_window()
        dpg.configure_item("output_path_window", show=True)
        dpg.configure_item("open_folder_btn", show=False)
        dpg.set_item_pos("ok_btn", (120, 100))
        return
    if not notes:
        dpg.set_value("output_path_text", tr("msg_no_notes"))
        resize_output_path_window()
        dpg.configure_item("output_path_window", show=True)
        dpg.configure_item("open_folder_btn", show=False)
        dpg.set_item_pos("ok_btn", (120, 100))
        return
    resize_rendering_window()
    dpg.configure_item("rendering_window", show=True)
    #warning1 = ""
    if bnc_range_is_full:
        yjsp_path, warning1 = convert.convert_notes_to_yjsp(notes, current_file_path, singer_path, bpm, GRID_WIDTH, user_named, user_named_output_path)
    else:
        render_notes = []
        true_l = min(locator_L, locator_R)
        true_r = max(locator_L, locator_R)
        for note in notes:
            if note["x"] >= true_l * 160 and note["x"] + note["w"] <= true_r * 160:
                render_notes.append(note.copy())
        for i in range(len(render_notes)):
            render_notes[i]["x"] -= true_l * 160
        yjsp_path, warning1 = convert.convert_notes_to_yjsp(render_notes, current_file_path, singer_path, bpm, (true_r - true_l) * 160, user_named, user_named_output_path)
    output_file = synthesis.synthesis(yjsp_path, pre_render=False, bend_changed = False) #応急処置
    dpg.configure_item("rendering_window", show=False)
    dpg.set_value("output_path_text", f"{tr('msg_output_to')}\n{output_file}")
    resize_output_path_window()
    dpg.configure_item("output_path_window", show=True)
    dpg.configure_item("open_folder_btn", show=True)
    dpg.set_item_pos("ok_btn", (170, 100))
    warning_text = "\n".join(warning1) if warning1 else ""
    if warning_text:
        dpg.set_value("warning_text", warning_text)
    user_named = False #とりあえずFalse
    

def bg_render_task(target_notes, target_bpm, target_grid, target_file_path, target_singer):
    global is_rendering_background, bg_pre_sound, bg_warnings_text, bend_changed
    
    try:
        #print("rendering")
        yjsp_path, warning = convert.convert_notes_to_yjsp(target_notes, target_file_path, target_singer, target_bpm, target_grid, False, None)#user_named, user_named_output_pathはなし
        output, warning2 = synthesis.synthesis(yjsp_path, pre_render=True, bend_changed = bend_changed) #応急処置
        #print(bend_changed)
        
        warnings_text = warning
        for w in warning2:
            warnings_text.append(w)
            
        bg_pre_sound = output
        bg_warnings_text = "\n".join(warnings_text) if warnings_text else ""
    except Exception as e:
        print(f"Background render error: {e}")
        bg_warnings_text = f"{tr('msg_bg_render_err')}{e}"
        
    is_rendering_background = False
    bend_changed = False #応急処置

def open_output_folder():
    global output_file
    if output_file:
        if platform.system() == "Windows":
            subprocess.run(["explorer", "/select,", output_file])
        elif platform.system() == "Darwin":  # macOS
            subprocess.run(["open", "-R", output_file])
        else:  # Linux and others
            subprocess.run(["xdg-open", output_file])
    dpg.configure_item("output_path_window", show=False)


#----------------ユーザーからの入力----------------
def global_key_handler(sender, app_data):
    global notes, is_playing

    #歌詞入力中はキー操作無効
    if not dpg.get_item_configuration("lyric_input_window")["show"]:
        if not dpg.get_item_configuration("lyrics_window")["show"]:
            if app_data == dpg.mvKey_1:
                set_tool(None, "Select")
                if dpg.does_item_exist("tool_combo"): dpg.set_value("tool_combo", tool_combo_labels()[0])
            elif app_data == dpg.mvKey_2:
                set_tool(None, "Pen")
                if dpg.does_item_exist("tool_combo"): dpg.set_value("tool_combo", tool_combo_labels()[1])
            elif app_data == dpg.mvKey_3:
                set_tool(None, "Eraser")
                if dpg.does_item_exist("tool_combo"): dpg.set_value("tool_combo", tool_combo_labels()[2])
            elif app_data == dpg.mvKey_4:
                set_tool(None, "Pitch Edit")
                if dpg.does_item_exist("tool_combo"): dpg.set_value("tool_combo", tool_combo_labels()[3])
            elif app_data == dpg.mvKey_Spacebar:
                if is_playing:
                    stop_play(None, None)
                else:
                    toggle_play(None, None)
        
            if app_data in (259, 261, dpg.mvKey_Back, dpg.mvKey_Delete):
                notes = [note for note in notes if not note.get("selected", False)]
        
            cmd_down = dpg.is_key_down(dpg.mvKey_LWin) or dpg.is_key_down(dpg.mvKey_RWin) or dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl)
            shift_down = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)
            if cmd_down:
                if app_data == dpg.mvKey_C:
                    menu_copy(None, None)
                elif app_data == dpg.mvKey_X:
                    menu_cut(None, None)
                elif app_data == dpg.mvKey_V:
                    menu_paste(None, None)
                elif app_data == dpg.mvKey_N:
                    menu_new(None, None)
                elif app_data == dpg.mvKey_O:
                    menu_open(None, None)
                elif app_data == dpg.mvKey_S and shift_down:
                    menu_save_as(None, None)
                elif app_data == dpg.mvKey_S:
                    menu_save(None, None)
                elif app_data == dpg.mvKey_Z and shift_down:
                    menu_redo(None, None)
                elif app_data == dpg.mvKey_Z:
                    menu_undo(None, None)
            
                

def handle_input():
    global dragging_note, resizing, offset_x
    global box_selecting, selection_start, selection_end
    global playhead_x, dragging_playhead
    global locator_R, locator_L, dragging_locator_R, dragging_locator_L
    global changed_playhead, notes_changed, history_notes_changed, is_dragging_changed
    global editing_bend_first, editing_bend_second, editing_bend_first_note, editing_bend_second_note, bend_changed
    global is_saved

    if current_tool == "Eraser" and dpg.is_mouse_button_down(0):
        if dpg.is_item_hovered("roll_child") or dpg.is_item_hovered("roll_drawlist"):
            pmx, pmy = dpg.get_drawing_mouse_pos()
            mx, my = pmx / zoom_x, pmy / zoom_y
            notes_before = len(notes)
            notes[:] = [note for note in notes if not (note["x"] <= mx <= note["x"] + note["w"] and note["y"] <= my <= note["y"] + note["h"])]
            if len(notes) != notes_before:
                notes_changed = True
                is_dragging_changed = True
                is_saved = False
        return

    if dpg.is_mouse_button_released(0):
        if is_dragging_changed:
            history_notes_changed = True
            is_dragging_changed = False

        if box_selecting:
            box_selecting = False
            pmx, pmy = dpg.get_drawing_mouse_pos()
            mx, my = pmx / zoom_x, pmy / zoom_y
            selection_end = (mx, my)
            x1, x2 = min(selection_start[0], selection_end[0]), max(selection_start[0], selection_end[0])
            y1, y2 = min(selection_start[1], selection_end[1]), max(selection_start[1], selection_end[1])
            for note in notes:
                nx1, nx2 = note["x"], note["x"] + note["w"]
                ny1, ny2 = note["y"], note["y"] + note["h"]
                if x1 < nx2 and x2 > nx1 and y1 < ny2 and y2 > ny1:
                    note["selected"] = True
                
        dragging_note = None
        resizing = False
        dragging_playhead = False
        dragging_locator_R = False
        dragging_locator_L = False

        editing_bend_first_note = None
        editing_bend_second_note = None
        editing_bend_first = False
        editing_bend_second = False

    if dragging_playhead and dpg.is_mouse_button_down(0):
        if dpg.is_item_hovered("timeline_child") or dpg.is_item_hovered("timeline_drawlist") or dpg.is_item_hovered("roll_child") or dpg.is_item_hovered("roll_drawlist"):
            pmx, pmy = dpg.get_drawing_mouse_pos()
            mx = pmx / zoom_x
            playhead_x = max(0, snap(mx, grid_w))
            if is_playing:
                changed_playhead = True
        return

    if dragging_locator_R and dpg.is_mouse_button_down(0):
        if dpg.is_item_hovered("timeline_child") or dpg.is_item_hovered("timeline_drawlist") or dpg.is_item_hovered("roll_child") or dpg.is_item_hovered("roll_drawlist"):
            pmx, pmy = dpg.get_drawing_mouse_pos()
            mx = pmx / zoom_x
            locator_R = max(0, snap(mx, grid_w)) / 160.0
            dpg.set_value("locator_r", locator_R)
            is_saved = False
        return

    if dragging_locator_L and dpg.is_mouse_button_down(0):
        if dpg.is_item_hovered("timeline_child") or dpg.is_item_hovered("timeline_drawlist") or dpg.is_item_hovered("roll_child") or dpg.is_item_hovered("roll_drawlist"):
            pmx, pmy = dpg.get_drawing_mouse_pos()
            mx = pmx / zoom_x
            locator_L = max(0, snap(mx, grid_w)) / 160.0
            dpg.set_value("locator_l", locator_L)
            is_saved = False
        return

    if dragging_note and dpg.is_mouse_button_down(0):
        pmx, pmy = dpg.get_drawing_mouse_pos()
        mx, my = pmx / zoom_x, pmy / zoom_y
        if resizing:
            new_w = snap(mx, grid_w) - dragging_note["x"] + grid_w
            max_allowed_w = float('inf')
            for n in notes:
                if n is not dragging_note and n["y"] == dragging_note["y"]:
                    if n["x"] >= dragging_note["x"]:
                        dist = n["x"] - dragging_note["x"]
                        if dist < max_allowed_w:
                            max_allowed_w = dist
            new_w = min(new_w, max_allowed_w) if max_allowed_w != float('inf') else new_w
            dragging_note["w"] = max(grid_w, new_w)
            notes_changed = True
            is_dragging_changed = True
            is_saved = False
        else:
            new_x = snap(mx - offset_x, grid_w)
            new_y = snap(my, CELL_H)
            dx = new_x - dragging_note["x"]
            dy = new_y - dragging_note["y"]
            if dx != 0 or dy != 0:
                if dragging_note.get("selected", False):
                    can_move = True
                    for n in notes:
                        if n.get("selected", False):
                            pn_x = n["x"] + dx
                            pn_y = n["y"] + dy
                            if pn_x < 0:
                                can_move = False
                                break
                            for un in notes:
                                if not un.get("selected", False):
                                    if un["y"] == pn_y and max(pn_x, un["x"]) < min(pn_x + n["w"], un["x"] + un["w"]):
                                        can_move = False
                                        break
                        if not can_move:
                            break
                    if can_move:
                        for n in notes:
                            if n.get("selected", False):
                                n["x"] += dx
                                n["y"] += dy
                        notes_changed = True
                        is_dragging_changed = True
                        is_saved = False
                else:
                    pn_x = dragging_note["x"] + dx
                    pn_y = dragging_note["y"] + dy
                    can_move = pn_x >= 0
                    if can_move:
                        for un in notes:
                            if un is not dragging_note:
                                if un["y"] == pn_y and max(pn_x, un["x"]) < min(pn_x + dragging_note["w"], un["x"] + un["w"]):
                                    can_move = False
                                    break
                    if can_move:
                        dragging_note["x"] += dx
                        dragging_note["y"] += dy
                        notes_changed = True
                        is_dragging_changed = True
                        is_saved = False
        return

    if box_selecting and dpg.is_mouse_button_down(0):
        pmx, pmy = dpg.get_drawing_mouse_pos()
        mx, my = pmx / zoom_x, pmy / zoom_y
        selection_end = (mx, my)
        return

    if editing_bend_first and dpg.is_mouse_button_down(0):
        pixels_per_sec = (bpm / 60.0) * CELL_W
        pmx, pmy = dpg.get_drawing_mouse_pos()
        mx, my = pmx / zoom_x, pmy / zoom_y
        clamped_mx = max(editing_bend_first_note["x"], min(mx, editing_bend_first_note["x"] + editing_bend_first_note["w"]))
        new_bend_second = (clamped_mx - editing_bend_first_note["x"]) / pixels_per_sec
        if editing_bend_first_note.get("bend_second") != new_bend_second:
            editing_bend_first_note["bend_second"] = new_bend_second
            notes_changed = True
            is_dragging_changed = True
            bend_changed = True #応急処置
            is_saved = False
        return
        
    if editing_bend_second and dpg.is_mouse_button_down(0):
        pixels_per_sec = (bpm / 60.0) * CELL_W
        pmx, pmy = dpg.get_drawing_mouse_pos()
        mx, my = pmx / zoom_x, pmy / zoom_y
        clamped_mx = max(editing_bend_second_note["x"], min(mx, editing_bend_second_note["x"] + editing_bend_second_note["w"]))
        new_bend_first = (editing_bend_second_note["x"] + editing_bend_second_note["w"] - clamped_mx) / pixels_per_sec
        if editing_bend_second_note.get("bend_first") != new_bend_first:
            editing_bend_second_note["bend_first"] = new_bend_first
            notes_changed = True
            is_dragging_changed = True
            bend_changed = True #応急処置
            is_saved = False
        return


    if dpg.is_mouse_button_clicked(0):
        if dpg.is_item_hovered("timeline_child") or dpg.is_item_hovered("keys_child") or dpg.is_item_hovered("roll_child"):
            dpg.configure_item("draw_item_checkbox", show=False) #ここにも追加


        if dpg.is_item_hovered("timeline_child") or dpg.is_item_hovered("timeline_drawlist"):
            pmx, pmy = dpg.get_drawing_mouse_pos()
            mx = pmx / zoom_x
            if pmx > locator_R * 160 * zoom_x - 7 and pmx < locator_R * 160 * zoom_x + 7:
                dragging_locator_R = True
                return
            if pmx > locator_L * 160 * zoom_x - 7 and pmx < locator_L * 160 * zoom_x + 7:
                dragging_locator_L = True
                return
            playhead_x = max(0, snap(mx, grid_w))
            dragging_playhead = True
            return

        if dpg.is_item_hovered("keys_drawlist"): #鍵盤クリックで音ならす
            pmx, pmy = dpg.get_drawing_mouse_pos()
            my = pmy / zoom_y
            tone_num = 84 - int(my / CELL_H)
            with open(Path(my_path) / "settings" / "音階hz表.json", "r", encoding="utf-8") as f:
                tones_dict = json.load(f)
            hz = tones_dict[str(tone_num)]
            try:
                out_device = sd.query_devices(kind='output')
                samplerate = int(out_device['default_samplerate'])
            except Exception:
                samplerate = 48000 # fallback

            t = np.linspace(0, 0.3, int(samplerate * 0.3), endpoint=False)
            x = np.sin(2 * np.pi * hz * t)
            x *= 0.2
            sd.play(x, samplerate=samplerate)
            
            
            

        if not dpg.is_item_hovered("roll_child") and not dpg.is_item_hovered("roll_drawlist"):
            return

        pmx, pmy = dpg.get_drawing_mouse_pos()
        mx, my = pmx / zoom_x, pmy / zoom_y

        margin_x = 10 / zoom_x

        if not current_tool == "Pitch Edit":
            for note in notes:
                if note["x"] <= mx <= note["x"] + note["w"] + margin_x and note["y"] <= my <= note["y"] + note["h"]:
                    if abs(mx - (note["x"] + note["w"])) < margin_x:
                        dragging_note = note
                        resizing = True
                        return

            for note in notes:
                if note["x"] <= mx <= note["x"] + note["w"] and note["y"] <= my <= note["y"] + note["h"]:
                    dragging_note = note
                    resizing = False
                    offset_x = mx - note["x"]
                    if current_tool == "Select":
                        if not note.get("selected", False):
                            for n in notes:
                                n["selected"] = False
                            note["selected"] = True
                    return
        else:
            pixels_per_sec = (bpm / 60.0) * CELL_W #ここではzoom_xなしで計算
            for note in notes:
                px = note["x"]
                pw = note["w"]
                py = note["y"] + note["h"] / 2
                pbend_first_x = note["bend_second"] * pixels_per_sec
                pbend_second_x = note["bend_first"] * pixels_per_sec
                #firstの方
                if px + pbend_first_x - margin_x <= mx <= px + pbend_first_x + margin_x and abs(my - py) < note["h"]:
                    editing_bend_first_note = note
                    editing_bend_first = True
                    return
                #secondの方
                if px + pw - pbend_second_x - margin_x <= mx <= px + pw - pbend_second_x + margin_x and abs(my - py) < note["h"]:
                    editing_bend_second_note = note
                    editing_bend_second = True
                    return


        if current_tool == "Pen":
            x = snap(mx, grid_w)
            y = snap(my, CELL_H)
            overlapping = False
            for note in notes:
                if note["y"] == y and max(x, note["x"]) < min(x + grid_w, note["x"] + note["w"]):
                    overlapping = True
                    break
            if not overlapping:
                notes.append({"x": x, "y": y, "w": grid_w, "h": CELL_H, "selected": False, "lyric": "", "bend_first": 0.05, "bend_second": 0.05}) #ピッチベンドの単位は秒、現状変更不可、0.05+0.05秒の0.1秒でピッチが次の音に変化
                notes_changed = True
                history_notes_changed = True
                is_saved = False
                
        elif current_tool == "Select":
            box_selecting = True
            selection_start = (mx, my)
            selection_end = (mx, my)
            for n in notes:
                n["selected"] = False

def double_click_callback(sender, app_data):
    global d_mx, d_my
    if dpg.is_item_hovered("roll_child") or dpg.is_item_hovered("roll_drawlist"):
        pmx, pmy = dpg.get_drawing_mouse_pos()
        d_mx, d_my = pmx / zoom_x, pmy / zoom_y
        for note in notes:
            if note["x"] <= d_mx <= note["x"] + note["w"] and note["y"] <= d_my <= note["y"] + note["h"]:
                dpg.configure_item("lyric_input_window", show=True)
                mouse_x, mouse_y = dpg.get_mouse_pos()
                mouse_x += 20
                mouse_y += 110
                dpg.set_item_pos("lyric_input_window", (mouse_x, mouse_y))
                dpg.set_value("lyric_input", note.get("lyric", ""))
                break

def change_lyric_callback(sender, app_data):
    global d_mx, d_my, notes_changed, history_notes_changed, is_saved
    for note in notes:
        if note["x"] <= d_mx <= note["x"] + note["w"] and note["y"] <= d_my <= note["y"] + note["h"]:
            note["lyric"] = app_data
            dpg.configure_item("lyric_input_window", show=False)
            notes_changed = True
            history_notes_changed = True
            is_saved = False
            break

#歌詞一括編集
def open_lyrics_window():
    global notes
    dpg.configure_item("lyrics_window", show=True)
    notes_sorted = sorted(notes, key=lambda x: x["x"])
    existing_lyrics = ""
    selected = False
    for note in notes_sorted:
        if note["selected"]:
            selected = True
            break
    if selected:
        for note in notes_sorted:
            if note["selected"]:
                existing_lyrics += note["lyric"] + " "
    else:
        for note in notes_sorted:
            existing_lyrics += note["lyric"] + " "
    dpg.set_value("lyrics_input", existing_lyrics)
    resize_lyrics_window()

def change_all_lyric_callback(lyrics):
    global notes, notes_changed, history_notes_changed, is_saved
    notes_sorted = sorted(notes, key=lambda x: x["x"])
    words = lyrics.split()

    notes_selected = []
    for note in notes_sorted:
        if note["selected"]:
            notes_selected.append(note)
    if len(notes_selected) > 0: #選択されてるノートが一つ以上ある場合
        word_index = 0
        for note in notes_selected:
            note["lyric"] = words[word_index]
            word_index += 1
            if word_index >= len(words):
                break
    else: #選択されてるノートがない場合
        word_index = 0
        for note in notes_sorted:
            if word_index < len(words):
                note["lyric"] = words[word_index]
                word_index += 1
            else:
                break
    dpg.configure_item("lyrics_window", show=False)
    notes_changed = True
    history_notes_changed = True
    is_saved = False


#設定ウィンドウを開く
def open_preferences():
    #出力デバイスを取得
    all_devices = [d for d in sd.query_devices() if d['max_output_channels'] > 0]
    devices_name_only = []
    for device in all_devices:
        devices_name_only.append(device["name"])
    dpg.configure_item("output_device", items=devices_name_only)

    resize_preferences_window()
    if dpg.does_item_exist("prefs_lang_combo"):
        dpg.set_value("prefs_lang_combo", LANG_COMBO_LABEL[ui_language])
    dpg.configure_item("preferences", show=True)

def set_output_device(sender, app_data):
    all_devices = sd.query_devices()
    target_id = None
    for i, dev in enumerate(all_devices):
        if dev['max_output_channels'] > 0 and dev["name"] == app_data:
            target_id = i
            break

    if target_id is not None:
        sd.default.device = target_id
    else:
        return


        


    


#----------------ファイルメニュー----------------
def menu_new(sender, app_data):
    global is_saved
    if is_saved:
        menu_new_2(None, None)
    else:
        dpg.configure_item("new_app_window", show=True)
        resize_new_app_window()


def menu_new_2(sender, app_data): #menu_new()で確認取った上で(もしくは確認ウィンドウの”変更を破棄”から呼ばれて)などで、実際にnewする関数
    global notes, playhead_x, current_file_path, singer_path, singer_changed, bpm, GRID_WIDTH, locator_L, locator_R, notes_changed, history_notes_changed, notes_history, setting_history, history_index, is_saved, is_opend
    playhead_x = 0.0
    current_file_path = None
    singer_path = None
    dpg.set_value("singer_path_text", fmt_path_line(None))
    singer_changed = True
    bpm = 120
    dpg.set_value("bpm_input", bpm)
    GRID_WIDTH = 1920
    locator_L = 0
    locator_R = 0
    dpg.set_value("locator_l", locator_L)
    dpg.set_value("locator_r", locator_R)
    notes_changed = True
    is_saved = True
    is_opend = True
    notes_history = [[]]
    setting_history = [[120, None, 0.0, 0.0]]
    history_index = 0
    notes = []

def open_file_callback(sender, app_data):
    global notes, current_file_path, GRID_WIDTH, singer_changed, bpm, singer_path, locator_L, locator_R, notes_changed, history_notes_changed, notes_history, setting_history, history_index, is_known_singer_added, is_saved, is_opend
    if "file_path_name" in app_data and app_data["file_path_name"]:
        file_path = Path(app_data["file_path_name"]) / "notes.json"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                notes = data.get("notes", [])
                current_file_path = app_data["file_path_name"]
            #V3以前のプロジェクトを読み込んだ場合、というかnoteにbend_firstとbend_secondがなかった場合
            for i, note in enumerate(notes):
                if not "bend_first" in note:
                    notes[i]["bend_first"] = 0.05
                if not "bend_second" in note:
                    notes[i]["bend_second"] = 0.05
            #GRID_WIDTHを足りないなら延長
            max_x = max((note["x"] + note["w"] for note in notes), default=0)
            if max_x > GRID_WIDTH:
                GRID_WIDTH = snap(max_x, CELL_W * 4) + CELL_W * 4
            notes_changed = True

            with open(Path(app_data["file_path_name"]) / "others.json", "r", encoding="utf-8") as f:
                others_data = json.load(f)
                bpm = others_data.get("bpm", 120)
                dpg.set_value("bpm_input", bpm)
                singer_path = others_data.get("singer", None)
                if singer_path:
                    dpg.set_value("singer_path_text", fmt_path_line(singer_path))
                    add_known_singer_to_json(singer_path)
                    is_known_singer_added = True
                    singer_changed = True
                locator_L = others_data.get("locator_left", 0)
                locator_R = others_data.get("locator_right", 0)
                dpg.configure_item("locator_l", default_value=locator_L)
                dpg.configure_item("locator_r", default_value=locator_R)
                
            notes_history = [copy.deepcopy(notes)]
            setting_history = [[bpm, singer_path, locator_R, locator_L]]
            history_index = 0

            is_saved = True
            is_opend = True
        except Exception as e:
            print(f"Error opening file: {e}")

def menu_open(sender, app_data):
    global is_saved
    if is_saved:
        dpg.show_item("open_file_dialog")
    else:
        dpg.configure_item("open_app_window", show=True)
        resize_open_app_window()

def menu_save(sender, app_data):
    global notes, current_file_path, is_saved
    if current_file_path:
        try:
            with open(Path(current_file_path) / "notes.json", "w", encoding="utf-8") as f:
                json.dump({"notes": notes}, f, indent=4, ensure_ascii=False)
            with open(Path(current_file_path) / "others.json", "w", encoding="utf-8") as f:
                json.dump({"bpm": bpm, "singer": singer_path, "locator_right": locator_R, "locator_left": locator_L}, f, indent=4, ensure_ascii=False)
            is_saved = True
        except Exception as e:
            print(f"Error saving file: {e}")
    else:
        menu_save_as(sender, app_data)

def save_file_callback(sender, app_data):
    global notes, current_file_path, is_saved
    #current_file_pathのフォルダを作成
    Path(app_data["file_path_name"]).mkdir(parents=True, exist_ok=True)
    if "file_path_name" in app_data and app_data["file_path_name"]:
        file_path = Path(app_data["file_path_name"]) / "notes.json"
        #if not file_path.endswith('.json') and not '.' in file_path.split('/')[-1]:
        #    file_path += '.json'
        #elif not file_path.endswith('json'):
        #    file_path += 'json'
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({"notes": notes}, f, indent=4, ensure_ascii=False)
                current_file_path = app_data["file_path_name"]
        except Exception as e:
            print(f"Error saving file: {e}")

    #その他bpm、シンガーなどの保存 others.json
    others_path = Path(app_data["file_path_name"]) / "others.json"
    try:
        with open(others_path, "w", encoding="utf-8") as f:
            json.dump({"bpm": bpm, "singer": singer_path, "locator_right": locator_R, "locator_left": locator_L}, f, indent=4, ensure_ascii=False)
        is_saved = True
    except Exception as e:
        print(f"Error saving others file: {e}")


def menu_save_as(sender, app_data):
    dpg.show_item("save_file_dialog")


def select_output_file_callback(sender, app_data):
    global user_named, user_named_output_path
    dpg.set_value("output_to_text", tr("msg_output_to") + " " + app_data["file_path_name"])
    user_named_output_path = app_data["file_path_name"]
    user_named = True

def check_is_saved():
    global current_file_path, is_saved
    #print(current_file_path)
    #print(is_saved)
    """
    if current_file_path == None:
        dpg.configure_item("close_app_window", show=True)
        resize_close_app_window()
    else:
    """
    if is_saved == False:
        dpg.configure_item("close_app_window", show=True)
        resize_close_app_window()
    else:
        dpg.stop_dearpygui()

def save_and_close():
    menu_save(None, None)
    dpg.stop_dearpygui()

def save_and_new():
    menu_save(None, None)
    menu_new_2(None, None)
    dpg.configure_item("new_app_window", show=False)

def delete_and_new():
    menu_new_2(None, None)
    dpg.configure_item("new_app_window", show=False)

def save_and_open():
    menu_save(None, None)
    dpg.show_item("open_file_dialog")
    dpg.configure_item("open_app_window", show=False)

def delete_and_open():
    dpg.show_item("open_file_dialog")
    dpg.configure_item("open_app_window", show=False)

#----------------編集メニュー----------------
def menu_undo(sender, app_data):
    global notes, notes_history, setting_history, history_index, notes_changed, bpm, singer_path, locator_R, locator_L, history_notes_changed, singer_changed, is_saved
    if history_index > 0:
        history_index -= 1
        notes = copy.deepcopy(notes_history[history_index])
        current_setting = copy.deepcopy(setting_history[history_index])
        bpm = current_setting[0]
        singer_path = current_setting[1]
        locator_R = current_setting[2]
        locator_L = current_setting[3]
        dpg.set_value("bpm_input", bpm)
        dpg.set_value("singer_path_text", fmt_path_line(singer_path))
        dpg.set_value("locator_l", locator_L)
        dpg.set_value("locator_r", locator_R)
        notes_changed = True
        singer_changed = True
        is_saved = False

def menu_redo(sender, app_data):
    global notes, notes_history, setting_history, history_index, notes_changed, bpm, singer_path, locator_R, locator_L, history_notes_changed, singer_changed, is_saved
    if history_index < len(notes_history) - 1:
        history_index += 1
        notes = copy.deepcopy(notes_history[history_index])
        current_setting = copy.deepcopy(setting_history[history_index])
        bpm = current_setting[0]
        singer_path = current_setting[1]
        locator_R = current_setting[2]
        locator_L = current_setting[3]
        dpg.set_value("bpm_input", bpm)
        dpg.set_value("singer_path_text", fmt_path_line(singer_path))
        dpg.set_value("locator_l", locator_L)
        dpg.set_value("locator_r", locator_R)
        notes_changed = True
        singer_changed = True
        is_saved = False

def push_history():#history_notes_changed = Trueの時のみupdate内で呼ぶ
    global notes, notes_history, setting_history, history_index, notes_changed, bpm, singer_path, locator_R, locator_L, history_notes_changed
    if history_index < len(notes_history) - 1:
        notes_history = notes_history[:history_index + 1]
        setting_history = setting_history[:history_index + 1]
    notes_history.append(copy.deepcopy(notes))
    setting_history.append([bpm, singer_path, locator_R, locator_L])
    history_index += 1
    if len(notes_history) > 100:
        notes_history.pop(0)
        setting_history.pop(0)
        history_index -= 1
    


def menu_delete(sender, app_data):
    global notes, notes_changed, history_notes_changed, is_saved
    for note in notes:
        if note.get("selected", False):
            notes_changed = True
            history_notes_changed = True
            is_saved = False
            break
    notes = [note for note in notes if not note.get("selected", False)]

def menu_copy(sender, app_data):
    global clipboard
    clipboard = [note.copy() for note in notes if note.get("selected", False)]
    for note in clipboard:
        note["selected"] = False

def menu_cut(sender, app_data):
    menu_copy(sender, app_data)
    menu_delete(sender, app_data)

def menu_paste(sender, app_data):
    global notes, notes_changed, history_notes_changed, is_saved
    if not clipboard:
        return
    min_x = min([note["x"] for note in clipboard])
    offset_x = snap(playhead_x, grid_w) - min_x
    for note in notes:
        note["selected"] = False
    
    new_notes_to_add = []
    for note in clipboard:
        new_note = note.copy()
        new_note["x"] = max(0, new_note["x"] + offset_x)
        new_note["selected"] = True
        
        overlap = False
        for un in notes:
            if un["y"] == new_note["y"] and max(new_note["x"], un["x"]) < min(new_note["x"] + new_note["w"], un["x"] + un["w"]):
                overlap = True
                break
        if not overlap:
            new_notes_to_add.append(new_note)

    notes.extend(new_notes_to_add)
    notes_changed = True
    history_notes_changed = True
    is_saved = False

#----------------GUI描画----------------
def create_ui():
    with dpg.window(label="Main Window", tag="main_window"):
        # メニューバー
        with dpg.menu_bar():
            with dpg.menu(label=tr("menu_file"), tag="menu_file"):
                dpg.add_menu_item(label=tr("mi_new"), tag="mi_new", shortcut="Cmd+N", callback=menu_new)
                dpg.add_separator()
                dpg.add_menu_item(label=tr("mi_open"), tag="mi_open", shortcut="Cmd+O", callback=menu_open)
                dpg.add_separator()
                dpg.add_menu_item(label=tr("mi_save"), tag="mi_save", shortcut="Cmd+S", callback=menu_save)
                dpg.add_menu_item(label=tr("mi_save_as"), tag="mi_save_as", callback=menu_save_as, shortcut="Cmd+Shift+S")
                dpg.add_menu_item(label=tr("mi_export"), tag="mi_export", callback=lambda:dpg.configure_item("bnc_window", show=True), shortcut="Cmd+E")
                dpg.add_separator()
                dpg.add_menu_item(label=tr("mi_quit"), tag="mi_quit", callback=check_is_saved)
            with dpg.menu(label=tr("menu_edit"), tag="menu_edit"):
                dpg.add_menu_item(label=tr("mi_undo"), tag="mi_undo", shortcut="Cmd+Z", callback=menu_undo)
                dpg.add_menu_item(label=tr("mi_redo"), tag="mi_redo", shortcut="Cmd+Shift+Z", callback=menu_redo)
                dpg.add_separator()
                dpg.add_menu_item(label=tr("mi_cut"), tag="mi_cut", shortcut="Cmd+X", callback=menu_cut)
                dpg.add_menu_item(label=tr("mi_copy"), tag="mi_copy", shortcut="Cmd+C", callback=menu_copy)
                dpg.add_menu_item(label=tr("mi_paste"), tag="mi_paste", shortcut="Cmd+V", callback=menu_paste)
                dpg.add_separator()
                dpg.add_menu_item(label=tr("mi_delete"), tag="mi_delete", shortcut="Del", callback=menu_delete)
            with dpg.menu(label=tr("menu_view"), tag="menu_view"):
                dpg.add_menu_item(label=tr("mi_controls"), tag="mi_controls", callback=lambda:dpg.configure_item("controls_drawlist", show=not dpg.is_item_shown("controls_drawlist")))
                dpg.add_menu_item(label=tr("mi_piano_roll"), tag="mi_piano_roll", callback=lambda:dpg.configure_item("Piano_Roll", show=not dpg.is_item_shown("Piano_Roll")))
                dpg.add_menu_item(label=tr("mi_export"), tag="mi_export_view", callback=lambda:dpg.configure_item("bnc_window", show=not dpg.is_item_shown("bnc_window")))
                dpg.add_menu_item(label=tr("mi_singer_setting"), tag="mi_singer_setting", callback=lambda:dpg.configure_item("singer_setting_window", show=not dpg.is_item_shown("singer_setting_window")))
                dpg.add_menu_item(label=tr("mi_singer"), tag="mi_singer", callback=lambda:dpg.configure_item("select_singer_dialog", show=True))
            with dpg.menu(label=tr("menu_tools"), tag="menu_tools"):
                dpg.add_menu_item(label=tr("mi_preferences"), tag="mi_preferences", callback=open_preferences)
            with dpg.menu(label=tr("menu_window"), tag="menu_window"):
                dpg.add_menu_item(label=tr("mi_maximize"), tag="mi_maximize", callback=dpg.maximize_viewport)
                dpg.add_menu_item(label=tr("mi_minimize"), tag="mi_minimize", callback=dpg.minimize_viewport)
                dpg.add_menu_item(label=tr("mi_fullscreen"), tag="mi_fullscreen", callback=dpg.toggle_viewport_fullscreen)

        with dpg.child_window(label=tr("child_controls"), height = 66, tag="controls_drawlist"):
            with dpg.group(horizontal=True):#水平にしたいだけ
                #音源情報
                with dpg.group(horizontal=True):
                    with dpg.texture_registry(tag="singer_texture"):
                        dpg.add_dynamic_texture(width=50, height=50, default_value=no_image_image, tag="singer_icon")
                    dpg.add_image("singer_icon")
                    with dpg.group():
                        dpg.add_text(tr("info_no_selected"), tag="info_text")
                        with dpg.tooltip("info_text"):
                            dpg.add_text(tr("tip_no_singer"), tag="tooltip_text")
                            dpg.add_text("")
                        with dpg.group(horizontal=True):
                            dpg.add_button(label=tr("btn_singer_setting"), tag="btn_singer_setting", callback=singer_setting_callback)
                            dpg.add_button(label=tr("btn_edit_lyrics"), tag="btn_edit_lyrics", callback=open_lyrics_window)

                with dpg.theme(tag="theme_play_active"):#再生中のPlayボタンのテーマ
                    with dpg.theme_component(dpg.mvButton):
                        dpg.add_theme_color(dpg.mvThemeCol_Button, (67, 102, 135, 255))
                        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (59, 105, 151, 255))
                        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (59, 105, 151, 255))
                        dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255, 255))

                with dpg.group(horizontal=True, tag="playback_controls"):
                    with dpg.group():
                        dpg.add_text(tr("lbl_locator"), tag="lbl_locator")
                        with dpg.group(horizontal=True):
                            dpg.add_text(tr("lbl_l"), tag="lbl_l")
                            dpg.add_input_float(default_value=0.0, callback=set_locator_L, width=43, step=0, tag="locator_l")
                            dpg.add_spacer(width=5)
                            dpg.add_text(tr("lbl_r"), tag="lbl_r")
                            dpg.add_input_float(default_value=0.0, callback=set_locator_R, width=43, step=0, tag="locator_r")
                    dpg.add_button(label="|<", callback=rewind_play, width=60, height=50)
                    dpg.add_button(label=tr("btn_play"), callback=toggle_play, width=80, height=50, tag="play_btn")
                    dpg.add_button(label=tr("btn_stop"), callback=stop_play, width=80, height=50, tag="stop_play_btn")
                    with dpg.group():
                        with dpg.group(horizontal=True):
                            dpg.add_text(tr("lbl_volume"), tag="lbl_volume")
                            dpg.add_slider_float(default_value=1.0, min_value=0.0, max_value=3.0, width=150, callback=set_volume, tag="volume_slider")
                            with dpg.tooltip("volume_slider"):
                                dpg.add_text(tr("tip_volume"), tag="volume_tip_text")
                        with dpg.group(horizontal=True):
                            dpg.add_text(tr("lbl_bpm"), tag="lbl_bpm")
                            dpg.add_input_float(default_value=bpm, callback=set_bpm, width=102, step=1.0, tag="bpm_input")

                with dpg.group(horizontal=True, tag="others_panel"):
                    dpg.add_button(label=tr("btn_bnc"), tag="bnc_main_btn", callback=show_bnc_window, width=40, height=22)
                    with dpg.child_window(label=tr("child_history"), tag="history_child", width=180, height=50, border=True):
                        dpg.add_text("", tag="warning_text")

        with dpg.child_window(label=tr("child_piano_roll"), tag="Piano_Roll"):
            with dpg.group(horizontal=True):
                with dpg.child_window(width=-65, height=35, border=False, no_scrollbar=True, tag="rollmenu_child"):
                    with dpg.group(horizontal=True):
                        dpg.add_text("X")
                        dpg.add_slider_float(default_value=3.0, min_value=0.1, max_value=10.0, callback=set_zoom_x, width=150)
                        dpg.add_text("Y")
                        dpg.add_slider_float(default_value=1.0, min_value=0.1, max_value=3.0, callback=set_zoom_y, width=150)

                        dpg.add_spacer(width=8)
                        dpg.add_text("||")
                        dpg.add_spacer(width=8)

                        dpg.add_text(tr("lbl_grid"), tag="lbl_grid")
                        dpg.add_combo(items=["1/4", "1/8", "1/16", "1/32", "1/64"], default_value="1/8", callback=set_quantize, width=55)
                        dpg.add_text(tr("lbl_tool"), tag="lbl_tool")
                        dpg.add_combo(items=tool_combo_labels(), default_value=tool_label_for_current(), callback=tool_combo_callback, width=85, tag="tool_combo")
                        with dpg.tooltip("tool_combo"):
                            dpg.add_text(tr("tip_tools"), tag="tool_tip_text")

                        dpg.add_spacer(width=8)
                        dpg.add_text("||")
                        dpg.add_spacer(width=8)

                        dpg.add_checkbox(label=tr("chk_auto_scroll"), tag="auto_scroll_chk", callback=switch_auto_scroll)

                        dpg.add_spacer(width=8)
                        dpg.add_text("||")
                        dpg.add_spacer(width=8)

                        dpg.add_button(label=tr("btn_view_combo"), tag="view_combo", width=60, callback=set_view_combo)

                with dpg.child_window(width=60, height=35, border=False, no_scrollbar=True):
                    with dpg.group(horizontal=True):
                        dpg.add_button(label=" ＋ ", callback=add_measure, tag="add_btn")
                        dpg.add_button(label=" ー ", callback=remove_measure, tag="remove_btn")
                        dpg.bind_item_font("add_btn", "bold_font")
                        dpg.bind_item_font("remove_btn", "bold_font")

            with dpg.group(horizontal=True):
                with dpg.child_window(width=60, height=30, no_scrollbar=True):
                    pass
                with dpg.child_window(width=-1, height=30, tag="timeline_child", no_scrollbar=True):
                    with dpg.drawlist(width=GRID_WIDTH, height=30, tag="timeline_drawlist"):
                        pass

            with dpg.group(horizontal=True):
                with dpg.child_window(width=60, autosize_y=True, tag="keys_child", no_scrollbar=True):
                    with dpg.drawlist(width=60, height=GRID_HEIGHT, tag="keys_drawlist"):
                        pass
                with dpg.child_window(horizontal_scrollbar=True, width=-1, autosize_y=True, tag="roll_child"):
                    with dpg.drawlist(width=GRID_WIDTH, height=GRID_HEIGHT, tag="roll_drawlist"):
                        pass
                    dpg.bind_item_font("roll_child", "medium_font")

    with dpg.window(label=tr("win_singer_setting"), tag="singer_setting_window", show=False, pos=(300, 200), height=238, width=400, no_resize=True):
        dpg.add_text(fmt_path_line(None), tag="singer_path_text", wrap=380)
        dpg.add_separator()
        dpg.add_text(tr("lbl_known_singers"), tag="known_singers_hdr")
        with dpg.texture_registry(show=False, tag="known_singers_texture_registry"):
            pass
        with dpg.child_window(width=380, height=98, horizontal_scrollbar=False, no_scrollbar=True):
            with dpg.group(horizontal=True, tag="known_singers_group"):
                pass
        dpg.add_button(label=tr("btn_select_add_singer"), tag="select_singer_main_btn", callback=select_singer_button_callback, width=140, height=30, pos=(130, 195))

    with dpg.window(label=tr("win_lyric_input"), tag="lyric_input_window", show=False, height=120, width=200, modal=True, no_title_bar=True, no_resize=True):
        dpg.add_input_text(label=tr("lbl_lyric"), tag="lyric_input", width=-30, callback=change_lyric_callback, on_enter=True, hint=tr("hint_lyric"))
        dpg.add_text(tr("lyric_input_help"), tag="lyric_input_help", wrap=180)
        dpg.add_button(label=tr("btn_cancel"), tag="lyric_cancel_btn", callback=lambda: dpg.configure_item("lyric_input_window", show=False), width=60, height=30, pos=(70, 80))

    with dpg.window(label=tr("win_rendering"), tag="rendering_window", show=False, height=100, width=150, modal=True, no_title_bar=True, no_resize=True, pos=(300, 200)):
        dpg.add_text(tr("txt_rendering"), tag="rendering_text", wrap=280)

    with dpg.window(label=tr("win_output_path"), tag="output_path_window", show=False, height=140, width=300, modal=False, no_title_bar=True, no_resize=True, pos=(300, 200)):
        dpg.add_text(tr("msg_output_to"), tag="output_path_text", wrap=280)
        dpg.add_button(label=tr("btn_open_folder"), callback=open_output_folder, width=100, height=30, pos=(60, 100), tag="open_folder_btn")
        dpg.add_button(label=tr("btn_ok"), callback=lambda: dpg.configure_item("output_path_window", show=False), width=60, height=30, pos=(170, 100), tag="ok_btn")

    with dpg.window(label=tr("win_bnc"), tag="bnc_window", show=False, height=300, width=400, modal=False, no_resize=True, pos=(300, 200)):
        dpg.add_radio_button(items=[tr("bnc_whole"), tr("bnc_selection")], default_value=tr("bnc_whole"), tag="bnc_range", callback=on_bnc_range_changed)
        dpg.add_spacer()
        dpg.add_separator()
        dpg.add_spacer()
        dpg.add_button(label=tr("btn_output_path"), callback=lambda: dpg.configure_item("select_output_path", show=True), width=100, height=30, tag="output_path_btn")
        dpg.add_text(tr("msg_output_to"), tag="output_to_text", wrap=380)
        dpg.add_button(label=tr("btn_bnc_export"), callback=rendering, width=80, height=30, pos=(220, 260), tag="bnc_btn")
        dpg.add_button(label=tr("btn_cancel"), callback=lambda: dpg.configure_item("bnc_window", show=False), width=80, height=30, pos=(310, 260), tag="bnc_cancel_btn")

    with dpg.window(label=tr("win_lyrics"), tag="lyrics_window", show=False, height=326, width=500, modal=False, no_resize=True, pos=(300, 200)):
        dpg.add_input_text(multiline=True, tag="lyrics_input", default_value="", width=-1, height=-27)
        with dpg.group(horizontal=True):
            dpg.add_text(tr("lyrics_hint"), tag="lyrics_hint_text", pos=(10, 295))
            dpg.add_button(label=tr("btn_ok"), callback=lambda: change_all_lyric_callback(dpg.get_value("lyrics_input")), width=60, height=23, pos=(335, 295), tag="lyrics_ok_btn")
            dpg.add_button(label=tr("btn_cancel"), callback=lambda: dpg.configure_item("lyrics_window", show=False), width=80, height=23, pos=(404, 295), tag="lyrics_cancel_btn")

    with dpg.window(tag="draw_item_checkbox", no_title_bar=True, no_scrollbar=True, show=False, no_resize=True, no_move=True):
        build_view_layer_checkboxes()

    with dpg.window(label=tr("win_confirm"), modal=False, show=False, no_move=True, no_resize=True, tag="close_app_window", width=390, height=130):
        dpg.add_text(tr("txt_unsaved"), tag="close_unsaved_text")
        dpg.add_spacer(height=20)
        with dpg.group(horizontal=True):
            dpg.add_button(label=tr("btn_cancel"), tag="close_cancel_btn", callback=lambda: dpg.configure_item("close_app_window", show=False), width=120, height=40)
            dpg.add_spacer(width=30)
            dpg.add_button(label=tr("btn_discard"), tag="close_discard_btn", callback=lambda: dpg.stop_dearpygui(), width=100, height=40)
            dpg.add_button(label=tr("btn_save"), tag="close_save_btn", callback=save_and_close, width=100, height=40)

    with dpg.window(label=tr("win_confirm"), modal=False, show=False, no_move=True, no_resize=True, tag="new_app_window", width=390, height=130):
        dpg.add_text(tr("txt_unsaved"), tag="new_unsaved_text")
        dpg.add_spacer(height=20)
        with dpg.group(horizontal=True):
            dpg.add_button(label=tr("btn_cancel"), tag="new_cancel_btn", callback=lambda: dpg.configure_item("new_app_window", show=False), width=120, height=40)
            dpg.add_spacer(width=30)
            dpg.add_button(label=tr("btn_save"), tag="new_save_btn", callback=save_and_new, width=100, height=40)
            dpg.add_button(label=tr("btn_discard"), tag="new_discard_btn", callback=delete_and_new, width=100, height=40)

    with dpg.window(label=tr("win_confirm"), modal=False, show=False, no_move=True, no_resize=True, tag="open_app_window", width=390, height=130):
        dpg.add_text(tr("txt_unsaved"), tag="open_unsaved_text")
        dpg.add_spacer(height=20)
        with dpg.group(horizontal=True):
            dpg.add_button(label=tr("btn_cancel"), tag="open_cancel_btn", callback=lambda: dpg.configure_item("open_app_window", show=False), width=120, height=40)
            dpg.add_spacer(width=30)
            dpg.add_button(label=tr("btn_save"), tag="open_save_btn", callback=save_and_open, width=100, height=40)
            dpg.add_button(label=tr("btn_discard"), tag="open_discard_btn", callback=delete_and_open, width=100, height=40)

    with dpg.window(label=tr("win_preferences"), tag="preferences", show=False, width=600, height=400, modal=False, no_resize=True):
        with dpg.tab_bar():
            with dpg.tab(label=tr("prefs_tab_playback"), tag="prefs_tab_playback"):
                dpg.add_combo(label=tr("prefs_output_device"), tag="output_device", callback=set_output_device, default_value=sd.query_devices(kind="output")["name"])
            with dpg.tab(label=tr("prefs_tab_display"), tag="prefs_tab_display"):
                dpg.add_combo(label=tr("prefs_display_language"), tag="prefs_lang_combo", items=list(LANG_COMBO_LABEL.values()), default_value=LANG_COMBO_LABEL[ui_language], callback=on_display_language_changed, width=240)


def draw():
    global current_tool
    global is_notes_draw, is_lyric_draw, is_pitch_curve_draw
    dpg.delete_item("roll_drawlist", children_only=True)
    if dpg.does_item_exist("timeline_drawlist"):
        dpg.delete_item("timeline_drawlist", children_only=True)
    if dpg.does_item_exist("keys_drawlist"):
        dpg.delete_item("keys_drawlist", children_only=True)

    physical_grid_width = int(GRID_WIDTH * zoom_x)
    physical_grid_height = int(GRID_HEIGHT * zoom_y)
    
    dpg.configure_item("roll_drawlist", width=physical_grid_width, height=physical_grid_height)
    if dpg.does_item_exist("timeline_drawlist"):
        # 縦スクロールバーの有無による最大スクロール値の差で末尾がズレるのを防ぐため、幅に十分な余裕を持たせる
        dpg.configure_item("timeline_drawlist", width=physical_grid_width + 100, height=30)
    if dpg.does_item_exist("keys_drawlist"):
        # 横スクロールバーの有無による最大スクロール値の差で末尾がズレるのを防ぐため、高さに十分な余裕を持たせる
        dpg.configure_item("keys_drawlist", width=60, height=physical_grid_height + 100)

    # グリッド
    max_cols = int(GRID_WIDTH // grid_w) + 1
    for col in range(max_cols):
        x = col * grid_w * zoom_x
        
        if (col * grid_w) % (CELL_W * 4) == 0:
            dpg.draw_line((x, 0), (x, physical_grid_height), color=(150,150,150,200), thickness=2, parent="roll_drawlist")
            measure_num = int((col * grid_w) / (CELL_W * 4)) + 1
            if dpg.does_item_exist("timeline_drawlist"):
                dpg.draw_text((x + 2, 8), str(measure_num), color=(200,200,200,255), size=14, parent="timeline_drawlist")
                dpg.draw_line((x, 20), (x, 30), color=(150,150,150,200), parent="timeline_drawlist")
        elif (col * grid_w) % (CELL_W) == 0:
            dpg.draw_line((x, 0), (x, physical_grid_height), color=(100,100,100,200), thickness=1.5, parent="roll_drawlist")
        elif (col * grid_w) % (CELL_W // 2) == 0:
            dpg.draw_line((x, 0), (x, physical_grid_height), color=(100,100,100,160), thickness=1, parent="roll_drawlist")
        else:
            dpg.draw_line((x, 0), (x, physical_grid_height), color=(100,100,100,100), thickness=0.75, parent="roll_drawlist")
        
    max_rows = int(GRID_HEIGHT // CELL_H) + 1

    #===========================================鍵盤描画===========================================
    #白鍵描画
    for row in range(max_rows):
        y = row * CELL_H * zoom_y
        dpg.draw_line((0, y), (physical_grid_width, y), color=(100,100,100,100), parent="roll_drawlist")
        
        if dpg.does_item_exist("keys_drawlist"):
            h = CELL_H * zoom_y
            is_black_pattern = [False, True, False, True, False, True, False, False, True, False, True, False]
            is_black = is_black_pattern[row % 12]
            
            if not is_black:
                # 白鍵
                #dpg.draw_rectangle((0, y), (55, y + h), fill=(240, 240, 240), color=(120, 120, 120, 255), parent="keys_drawlist")
                if is_black_pattern[(row-1) % 12] == True and is_black_pattern[(row+1) % 12] == True: #黒に挟まれてる白鍵
                    dpg.draw_rectangle((0, y - (h/2)), (55, y + h + (h/2)), fill=(240, 240, 240), color=(120, 120, 120, 255), parent="keys_drawlist")
                elif is_black_pattern[(row-1) % 12] == True and is_black_pattern[(row+1) % 12] == False: #上が黒鍵の白鍵
                    dpg.draw_rectangle((0, y - (h/2)), (55, y + h), fill=(240, 240, 240), color=(120, 120, 120, 255), parent="keys_drawlist")
                elif is_black_pattern[(row-1) % 12] == False and is_black_pattern[(row+1) % 12] == True: #下が黒鍵の白鍵
                    dpg.draw_rectangle((0, y), (55, y + h + (h/2)), fill=(240, 240, 240), color=(120, 120, 120, 255), parent="keys_drawlist")
    #黒鍵描画
    for row in range(max_rows):
        y = row * CELL_H * zoom_y
        #dpg.draw_line((0, y), (physical_grid_width, y), color=(100,100,100,50), parent="roll_drawlist")
        
        if dpg.does_item_exist("keys_drawlist"):
            h = CELL_H * zoom_y
            is_black_pattern = [False, True, False, True, False, True, False, False, True, False, True, False]
            is_black = is_black_pattern[row % 12]
            if is_black:
                # 黒鍵の奥の隙間（白鍵の根元部分として描画）
                #dpg.draw_rectangle((0, y), (55, y + h), fill=(200, 200, 200), color=(120, 120, 120, 255), parent="keys_drawlist")
                # 黒鍵本体（手前を短くする）
                dpg.draw_rectangle((0, y), (35, y + h), fill=(40, 40, 40), color=(20, 20, 20, 255), parent="keys_drawlist")

    #音名描画
    n = 83
    for row in range(max_rows):
        y = row * CELL_H * zoom_y
        #dpg.draw_line((0, y), (physical_grid_width, y), color=(100,100,100,50), parent="roll_drawlist")
        
        if dpg.does_item_exist("keys_drawlist"):
            if n % 12 == 0:
                dpg.draw_text((2, y + 1), "C" + str(n // 12 + 1), color=(170,170,170,255), size=16, parent="keys_drawlist")
            elif n % 12 == 1:
                dpg.draw_text((2, y + 1), "C#" + str(n // 12 + 1), color=(130,130,130,255), size=16, parent="keys_drawlist")
            elif n % 12 == 2:
                dpg.draw_text((2, y + 1), "D" + str(n // 12 + 1), color=(170,170,170,255), size=16, parent="keys_drawlist")
            elif n % 12 == 3:
                dpg.draw_text((2, y + 1), "D#" + str(n // 12 + 1), color=(130,130,130,255), size=16, parent="keys_drawlist")
            elif n % 12 == 4:
                dpg.draw_text((2, y + 1), "E" + str(n // 12 + 1), color=(170,170,170,255), size=16, parent="keys_drawlist")
            elif n % 12 == 5:
                dpg.draw_text((2, y + 1), "F" + str(n // 12 + 1), color=(170,170,170,255), size=16, parent="keys_drawlist")
            elif n % 12 == 6:
                dpg.draw_text((2, y + 1), "F#" + str(n // 12 + 1), color=(130,130,130,255), size=16, parent="keys_drawlist")
            elif n % 12 == 7:
                dpg.draw_text((2, y + 1), "G" + str(n // 12 + 1), color=(170,170,170,255), size=16, parent="keys_drawlist")
            elif n % 12 == 8:
                dpg.draw_text((2, y + 1), "G#" + str(n // 12 + 1), color=(130,130,130,255), size=16, parent="keys_drawlist")
            elif n % 12 == 9:
                dpg.draw_text((2, y + 1), "A" + str(n // 12 + 1), color=(170,170,170,255), size=16, parent="keys_drawlist")
            elif n % 12 == 10:
                dpg.draw_text((2, y + 1), "A#" + str(n // 12 + 1), color=(130,130,130,255), size=16, parent="keys_drawlist")
            elif n % 12 == 11 and n >= 0:
                dpg.draw_text((2, y + 1), "B" + str(n // 12 + 1), color=(170,170,170,255), size=16, parent="keys_drawlist")
            n -= 1
            

    # ノート
    pixels_per_sec = (bpm / 60.0) * CELL_W * zoom_x

    for note in notes:
        px = note["x"] * zoom_x
        py = note["y"] * zoom_y
        pw = note["w"] * zoom_x
        ph = note["h"] * zoom_y
        
        is_sel = note.get("selected", False)
        fill_color = (100, 200, 255, 180) if is_sel else (0, 0, 255, 120)
        outline_color = (255, 255, 255, 255) if is_sel else (255, 255, 255, 255)
        
        if is_notes_draw: #ノートを描画するか
            dpg.draw_rectangle(
                (px, py),
                (px + pw, py + ph),
                fill=fill_color,
                color=outline_color,
                parent="roll_drawlist"
            )
        #歌詞の描画
        if is_lyric_draw: #歌詞を描画するか
            note_lyric = note.get("lyric", "")
            if note_lyric:
                dpg.draw_text(
                    (px + 5, py),
                    note_lyric,
                    color=(255, 255, 255, 255),
                    size=18,
                    parent="roll_drawlist",
                )
        if current_tool == "Pitch Edit":
            #bendはじめと終わりの点
            bend_first = note.get("bend_first", 0.05)
            bend_second = note.get("bend_second", 0.05)
            bend_y = py + ph / 2
            dpg.draw_circle((px + bend_second * pixels_per_sec, bend_y), 4, color=(255, 255, 255, 255), parent="roll_drawlist")
            dpg.draw_circle((px + pw - bend_first * pixels_per_sec, bend_y), 4, color=(255, 255, 255, 255), parent="roll_drawlist")


    #ピッチ曲線の描画
    #1秒が何pxか計算
    #pixels_per_sec = (bpm / 60.0) * CELL_W * zoom_x
    notes_list = sorted(notes, key=lambda x: x["x"])
    #被ってるノートを削除
    last_note_end = -1
    notes_list_to_draw = []
    for note in notes_list:
        note_start = note["x"]
        note_end = note["x"] + note["w"]
        if note_start >= last_note_end:
            notes_list_to_draw.append(note)
            last_note_end = note_end

    note_number = 0
    pitch_curve_points = []
    pitch_curve_segments = []
    for note in notes_list_to_draw:
        #ピッチ曲線の描画
        #座標をリストに入れて後でdraw_polylineする
        #曲線部分は計算する
        bend_first = note.get("bend_first", 0.05)
        bend_second = note.get("bend_second", 0.05)
        start_x = note["x"] * zoom_x + pixels_per_sec * bend_second
        end_x = (note["x"] + note["w"]) * zoom_x - pixels_per_sec * bend_first
        y = note["y"] + note["h"] / 2 #ノートの真ん中
        y = y * zoom_y
        note_end_x = note["x"] + note["w"]

        if note_number == len(notes_list_to_draw) - 1:
            pitch_curve_points.append([start_x, y])
            pitch_curve_points.append([(note["x"] + note["w"]) * zoom_x, y])
            if len(pitch_curve_points) >= 2:
                pitch_curve_segments.append(pitch_curve_points)
            break
        next_note = notes_list_to_draw[note_number + 1]
        next_bend_second = next_note.get("bend_second", 0.05)
        next_start_x = (next_note["x"]) * zoom_x + pixels_per_sec * next_bend_second
        next_y = next_note["y"] + next_note["h"] / 2
        next_y = next_y * zoom_y
        next_note_start_x = next_note["x"]
        
        pitch_curve_points.append([start_x, y]) #とりあえずこれを追加
        pitch_curve_points.append([end_x, y])
        #シグモイド曲線の計算
        #(end_x, y)から(next_start_x, next_y)までの間のシグモイド曲線を計算、pitch_curve_pointsに追加
        if note_end_x == next_note_start_x:
            curve_width = next_start_x - end_x
            if curve_width > 0:
                if abs(next_y - y) > 0:
                    point_count = max(8, min(64, int(curve_width / 4)))
                    sigmoid_x = np.linspace(-5, 5, point_count)
                    sigmoid_y = 1 / (1 + np.exp(-sigmoid_x))
                    for i, ratio in enumerate(sigmoid_y):
                        x = end_x + curve_width * (i + 1) / point_count
                        pitch_y = y + (next_y - y) * ratio
                        pitch_curve_points.append([x, pitch_y])
            else:
                pitch_curve_points.append([next_start_x, next_y])
        else:
            if len(pitch_curve_points) >= 2:
                pitch_curve_segments.append(pitch_curve_points)
            pitch_curve_points = []
        note_number += 1

    if is_pitch_curve_draw: #ピッチ曲線を描画するか
        for pitch_curve_points in pitch_curve_segments:
            dpg.draw_polyline(pitch_curve_points, color=(255, 255, 170, 255), thickness=1.5, parent="roll_drawlist")
        
    # 選択枠の描画
    if box_selecting:
        x1, x2 = min(selection_start[0], selection_end[0]) * zoom_x, max(selection_start[0], selection_end[0]) * zoom_x
        y1, y2 = min(selection_start[1], selection_end[1]) * zoom_y, max(selection_start[1], selection_end[1]) * zoom_y
        dpg.draw_rectangle((x1, y1), (x2, y2), fill=(100, 150, 255, 50), color=(100, 150, 255, 200), parent="roll_drawlist")

    #ロケーターの描画
    px_r = max(locator_R, locator_L) * 160 * zoom_x
    px_l = min(locator_R, locator_L) * 160 * zoom_x
    if dpg.does_item_exist("timeline_drawlist"):
        if px_r > px_l:
            dpg.draw_rectangle((px_l, 0), (px_r, 10), fill=(100, 100, 255, 120), color=(100, 100, 255, 120), parent="timeline_drawlist")
        r1 = (px_r, 0)
        r2 = (px_r - 10, 0)
        r3 = (px_r, 10)
        l1 = (px_l, 0)
        l2 = (px_l + 10, 0)
        l3 = (px_l, 10)
        dpg.draw_triangle(r1, r2, r3, fill=(255, 255, 255, 255), color=(255, 255, 255, 255), parent=("timeline_drawlist"))
        dpg.draw_triangle(l1, l2, l3, fill=(255, 255, 255, 255), color=(255, 255, 255, 255), parent=("timeline_drawlist"))

    # 再生バー（プレイヘッド）の描画
    px = playhead_x * zoom_x
    dpg.draw_line((px, 0), (px, physical_grid_height), color=(255, 255, 255, 255), thickness=2, parent="roll_drawlist")
    if dpg.does_item_exist("timeline_drawlist"):
        p1 = (px - 6.0 + 0.5, 0.0)
        p2 = (px + 6.0 + 0.5, 0.0)
        p3 = (px + 0.5, 12.0)
        dpg.draw_triangle(p1, p2, p3, fill=(255, 255, 255, 255), color=(255, 255, 255, 255), parent="timeline_drawlist")
        dpg.draw_line((px, 0), (px, 30), color=(255, 255, 255, 255), thickness=2, parent="timeline_drawlist")

def update():
    global playhead_x, last_time, singer_changed, info_text, changed_playhead, notes, notes_changed, is_playing, history_notes_changed, singer_path, is_known_singer_added
    global is_rendering_background, pending_render, bg_pre_sound, bg_warnings_text, previously_rendering, pre_sound, GRID_WIDTH, is_auto_scroll
    global is_saved, is_opend

    #viewportのタイトル
    saved_text = " *" if not is_saved else ""
    path_text = f"    {current_file_path}" if not current_file_path == None else ""
    dpg.set_viewport_title(f"V5{path_text}{saved_text}")


    if is_playing:
        #描画処理
        current_time = time.time()
        dt = current_time - last_time
        last_time = current_time
        pixels_per_second = (bpm / 60.0) * CELL_W
        playhead_x += dt * pixels_per_second
        if changed_playhead:
            sd.stop()
            is_playing = False
            toggle_play(None, None)
            changed_playhead = False
        if playhead_x >= GRID_WIDTH:
            stop_play(None, None)
        if is_auto_scroll:
            viewport_width = dpg.get_viewport_width() - 130
            if viewport_width // 2 < playhead_x * zoom_x:
                dpg.set_x_scroll("roll_child", playhead_x * zoom_x - viewport_width // 2)
            else:
                dpg.set_x_scroll("roll_child", 0)

    handle_input()
    draw()

    """
    if notes != last_notes:
        notes_changed = True
    last_notes = notes.copy()
    """
    
    if dpg.does_item_exist("roll_child"):
        try:
            scroll_x = dpg.get_x_scroll("roll_child")
            scroll_y = dpg.get_y_scroll("roll_child")
            if dpg.does_item_exist("timeline_child"):
                dpg.set_x_scroll("timeline_child", scroll_x)
                dpg.set_y_scroll("timeline_child", 7.0)
            if dpg.does_item_exist("keys_child"):
                dpg.set_y_scroll("keys_child", scroll_y)
                dpg.set_x_scroll("keys_child", 0.0)
        except:
            pass

    #音源変更時
    if singer_changed and dpg.does_item_exist("singer_icon"):
        notes_changed = True #音源変更で履歴を更新
        if not is_opend: #開かれた又は新規作成、でない場合未保存判定
            is_saved = False
        is_opend = False #音源変更時又は新規作成時未保存判定対策専用フラグなのでここでFalseにする
        if not singer_path == None:
            change_image_callback()
            singer_changed = False

            #info_textなどの更新
            dpg.set_value("singer_path_text", fmt_path_line(singer_path))
            new_info = Path(singer_path) / "character.txt"
            if not new_info.exists():
                dpg.set_value("info_text", tr("msg_no_char_txt"))
                dpg.set_value("tooltip_text", tr("tip_no_char_txt"))
                return
            character_info = open(Path(singer_path) / "character.txt", "r", encoding="utf-8")
            lines = character_info.readlines()
            line_val = 1
            for line in lines:
                if line.startswith("name="):
                    name = line.split("name=")[1].strip()
                    dpg.set_value("info_text", name)
                if line.startswith("info:"):
                    info_line = line_val
                line_val += 1
            if info_line is not None and info_line < len(lines):
                info_text = ""
                for i in range(len(lines) - info_line):
                    info_text = info_text + lines[info_line + i].strip() + "\n"
                dpg.set_value("tooltip_text", info_text)

        else:
            dpg.set_value("singer_icon", no_image_image)
            dpg.set_value("info_text", tr("info_no_selected"))
            dpg.set_value("tooltip_text", tr("tip_no_singer"))
            singer_changed = False

    if is_known_singer_added:
        set_known_singers_buttons()
        is_known_singer_added = False


    if history_notes_changed:
        push_history()
        history_notes_changed = False
        
    if not is_rendering_background:
        if previously_rendering:
            dpg.set_value("warning_text", bg_warnings_text)
            pre_sound = bg_pre_sound
            previously_rendering = False
        
        if pending_render:
            notes_changed = True
            pending_render = False
            
        if notes_changed and singer_path and notes:
            is_rendering_background = True
            notes_changed = False
            previously_rendering = True
            dpg.set_value("warning_text", tr("msg_rendering_bg"))
            t = threading.Thread(target=bg_render_task, args=(copy.deepcopy(notes), bpm, GRID_WIDTH, current_file_path, singer_path), daemon=True)
            t.start()
    else:
        if notes_changed:
            pending_render = True
            notes_changed = False
        



#playback_controlsを常に中央に、他を右端に
def resize_callback():
    viewport_width = dpg.get_viewport_width()

    if dpg.does_item_exist("playback_controls"):
        btn_width = 220  # 3つのボタンの合計幅
        x = max(((viewport_width - btn_width) // 2) - 175, 230)
        dpg.set_item_pos("playback_controls", (x, 8))

    if dpg.does_item_exist("others_panel"):
        others_width = 260 # Bnc(40) + history(180) + margin ~ 240
        x_others = max(viewport_width - others_width, x + btn_width + 100 if dpg.does_item_exist("playback_controls") else 0)
        dpg.set_item_pos("others_panel", (x_others, 8))

#output_path_windowを中央に
def resize_output_path_window():
    viewport_width = dpg.get_viewport_width()
    viewport_height = dpg.get_viewport_height()
    dpg.set_item_pos("output_path_window", (viewport_width // 2 - 150, viewport_height // 2 - 70))

def resize_rendering_window():
    viewport_width = dpg.get_viewport_width()
    viewport_height = dpg.get_viewport_height()
    dpg.set_item_pos("rendering_window", (viewport_width // 2 - 75, viewport_height // 2 - 50))

def resize_bnc_window():
    viewport_width = dpg.get_viewport_width()
    viewport_height = dpg.get_viewport_height()
    dpg.set_item_pos("bnc_window", (viewport_width // 2 - 200, viewport_height // 2 - 100))

def resize_singer_setting_window():
    viewport_width = dpg.get_viewport_width()
    viewport_height = dpg.get_viewport_height()
    dpg.set_item_pos("singer_setting_window", (viewport_width // 2 - 200, viewport_height // 2 - 150))

def resize_lyrics_window():
    viewport_width = dpg.get_viewport_width()
    viewport_height = dpg.get_viewport_height()
    dpg.set_item_pos("lyrics_window", (viewport_width // 2 - 250, viewport_height // 2 - 163))

def resize_preferences_window():
    viewport_width = dpg.get_viewport_width()
    viewport_height = dpg.get_viewport_height()
    dpg.set_item_pos("preferences", (viewport_width // 2 - 300, viewport_height // 2 - 200))

def resize_close_app_window():
    viewport_width = dpg.get_viewport_width()
    viewport_height = dpg.get_viewport_height()
    dpg.set_item_pos("close_app_window", (viewport_width // 2 -195, viewport_height // 2 - 65))

def resize_new_app_window():
    viewport_width = dpg.get_viewport_width()
    viewport_height = dpg.get_viewport_height()
    dpg.set_item_pos("new_app_window", (viewport_width // 2 -195, viewport_height // 2 - 65))

def resize_open_app_window():
    viewport_width = dpg.get_viewport_width()
    viewport_height = dpg.get_viewport_height()
    dpg.set_item_pos("open_app_window", (viewport_width // 2 -195, viewport_height // 2 - 65))



#=========================処理=========================
#音源画像のデフォルト画像
no_image_image = get_image_data(Path(my_path) / "images" / "no_image.png")


dpg.create_context()


#フォントの設定
with dpg.font_registry():
    with dpg.font(Path(my_path) / "fonts" / "NotoSansJP-Regular.otf", 16, tag="main_font"):
        dpg.add_font_range_hint(dpg.mvFontRangeHint_Japanese)
    dpg.bind_font("main_font")
    with dpg.font(Path(my_path) / "fonts" / "NotoSansJP-Medium.otf", 30, tag="medium_font"):
        dpg.add_font_range_hint(dpg.mvFontRangeHint_Japanese)

#ファイルダイアログの設定
with dpg.file_dialog(label = tr("dlg_open_project"), directory_selector=True, show=False, callback=open_file_callback, tag="open_file_dialog", width=600, height=400):
    dpg.add_file_extension(tr("ext_folders"), color=(150, 255, 150, 255))

with dpg.file_dialog(label = tr("dlg_save_project"), directory_selector=True, show=False, callback=save_file_callback, tag="save_file_dialog", width=600, height=400):
    dpg.add_file_extension(tr("ext_folders"), color=(150, 255, 150, 255))

with dpg.file_dialog(label = tr("dlg_select_singer"), directory_selector=True, show=False, callback=select_singer_callback, tag="select_singer_dialog", width=600, height=400):
    dpg.add_file_extension(tr("ext_folders"), color=(150, 255, 150, 255))

with dpg.file_dialog(label = tr("dlg_select_wav"), directory_selector=False, show=False, callback=select_output_file_callback, tag="select_output_path", width=600, height=400):
    dpg.add_file_extension(tr("ext_wav"), color=(150, 255, 150, 255))
    dpg.add_file_extension(tr("ext_folders"), color=(150, 255, 150, 255))



create_ui()
apply_ui_language()

dpg.create_viewport(title='V5', width=1200, height=800, resizable=True, disable_close=True)

dpg.set_viewport_resize_callback(resize_callback)

dpg.setup_dearpygui()

with dpg.handler_registry():
    dpg.add_key_press_handler(callback=global_key_handler)
    dpg.add_mouse_double_click_handler(callback=double_click_callback)

dpg.set_exit_callback(check_is_saved)

dpg.show_viewport()

dpg.set_primary_window("main_window", True)

resize_callback()#初期配置
dpg.set_y_scroll("roll_child", 480)#初期配置
set_known_singers_buttons()#既知の音源ボタンの配置

while dpg.is_dearpygui_running():
    update()
    dpg.render_dearpygui_frame()

dpg.destroy_context()
