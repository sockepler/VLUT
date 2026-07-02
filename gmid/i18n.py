"""English / Japanese UI strings."""

LANGS = ["en", "ja"]

_T = {
    # generic
    "app_title": ("gm/id Design Tool", "gm/id 設計ツール"),
    "pdk": ("PDK", "PDK"),
    "add_pdk": ("Add PDK", "PDK追加"),
    "pdk_name": ("Name (id)", "名前 (ID)"),
    "pdk_title": ("Title", "タイトル"),
    "model_lib": ("Model library", "モデルライブラリ"),
    "mos_corners_pick": ("MOS corners (from lib)", "MOSコーナー（libから）"),
    "mos_models_pick": ("MOS models to include (from lib)",
                        "登録するMOSモデル（libから）"),
    "polarity": ("Polarity", "極性"),
    "sweep_grid": ("Characterization grid", "特性抽出グリッド"),
    "grid_ls": ("L list [µm]", "L リスト [µm]"),
    "grid_vsbs": ("VSB list [V]", "VSB リスト [V]"),
    "pdk_note": ("MOS is enough for gm/id. BJT/R/C sections are auto-added if"
                 " present; edit the yaml to add their device names later.",
                 "gm/idにはMOSで十分です。BJT/R/C のセクションは存在すれば自動"
                 "追加されます。デバイス名は後でyamlに追記してください。"),
    "pdk_need_name_lib": ("Set a name and pick a model library.",
                          "名前とモデルライブラリを指定してください。"),
    "pdk_need_corner": ("No corner selected. Pick the corner .lib (the file"
                        " your ADE Model Libraries points to), not a bare .mdl.",
                        "コーナーが未選択です。ADEのModel Librariesが指すコーナー"
                        " .lib を選んでください（素の .mdl ではありません）。"),
    "pdk_need_model": ("No MOS model selected. Pick the corner .lib that your"
                       " ADE points to — a bare .mdl/.ckt won't list them.",
                       "MOSモデルが未選択です。ADEが指すコーナー .lib を選んで"
                       "ください。素の .mdl/.ckt では検出されません。"),
    "pdk_pick_lib_hint": ("Pick the corner model library — the .lib your ADE"
                          " Model Libraries setup points to (it has the"
                          " section tt/ff/ss blocks). Corners and MOS models"
                          " are detected and pre-checked automatically.",
                          "ADEのModel Librariesが指すコーナー用 .lib を選んで"
                          "ください（section tt/ff/ss を含むファイル）。コーナー"
                          "とMOSモデルは自動検出・自動チェックされます。"),
    "pdk_detect_ok": ("Detected %d corners and %d MOS models — pre-checked."
                      " Review, then Save.",
                      "コーナー %d 個、MOSモデル %d 個を検出・チェック済み。"
                      "確認して Save。"),
    "pdk_detect_no_model": ("No MOS transistor models found in this file."
                            " Pick the corner .lib your ADE points to"
                            " (a .mdl/.ckt alone won't work).",
                            "このファイルにMOSモデルがありません。ADEが指す"
                            "コーナー .lib を選んでください（.mdl/.ckt 単体は不可）。"),
    "pdk_detect_no_corner": ("Models found but no corner sections. Pick the"
                             " corner .lib (with section tt/ff/ss), not a bare"
                             " .mdl.",
                             "モデルはありますがコーナーがありません。section"
                             " tt/ff/ss を持つコーナー .lib を選んでください。"),
    "pdk_detect_none": ("No corners or models detected — this is not a model"
                        " library. Pick the corner .lib your ADE points to.",
                        "コーナーもモデルも検出できません。モデルライブラリでは"
                        "ありません。ADEが指すコーナー .lib を選んでください。"),
    "corner": ("Corner", "コーナー"),
    "language": ("Language", "言語"),
    "temp": ("Temp [°C]", "温度 [°C]"),
    "device": ("Device", "デバイス"),
    "plot": ("Plot", "プロット"),
    "run": ("Run", "実行"),
    "error": ("Error", "エラー"),
    "ok": ("OK", "OK"),
    "browse": ("Browse…", "参照…"),
    "log": ("Log", "ログ"),
    "value": ("Value", "値"),
    "parameter": ("Parameter", "パラメータ"),
    # tabs
    "tab_curves": ("Curves", "特性カーブ"),
    "tab_query": ("Query / Size", "検索・サイズ"),
    "tab_netlist": ("Netlist Designer", "ネットリスト設計"),
    "tab_topo": ("Topologies", "トポロジー設計"),
    "tab_passives": ("Passives / BJT", "受動素子・BJT"),
    "tab_char": ("Characterize", "デバイス特性抽出"),
    # curves
    "x_axis": ("X axis", "X軸"),
    "y_axis": ("Y axis", "Y軸"),
    "log_x": ("log X", "log X"),
    "log_y": ("log Y", "log Y"),
    "lengths": ("L [µm]", "L [µm]"),
    # query
    "given": ("Given", "指定条件"),
    "size_target": ("Size target", "サイズ目標"),
    "none": ("(none)", "（なし）"),
    "query": ("Query", "検索"),
    "result": ("Result", "結果"),
    "W_computed": ("W (computed)", "W（計算値）"),
    # netlist designer
    "netlist_dir": ("ADE netlist dir (input.scs)", "ADEネットリスト (input.scs)"),
    "load": ("Load", "読み込み"),
    "run_op": ("Run OP", "OP実行"),
    "iterate": ("Iterate", "反復設計"),
    "max_iter": ("Max iter", "最大反復"),
    "save_as": ("Save netlist…", "ネットリスト保存…"),
    "push_virtuoso": ("Push to Virtuoso", "Virtuosoへ反映"),
    "remap_log": ("Model remap log", "モデル再マップ ログ"),
    "col_device": ("Device", "デバイス"),
    "col_model": ("Model", "モデル"),
    "col_count": ("#", "個数"),
    "col_W": ("W/unit [µm]", "単体W [µm]"),
    "col_m": ("m", "m"),
    "col_Wtot": ("W total [µm]", "総W [µm]"),
    "col_L": ("L [µm]", "L [µm]"),
    "wmax": ("Max unit W [µm]", "単体W上限 [µm]"),
    "col_id": ("ID [A]", "ID [A]"),
    "col_gmid": ("gm/ID", "gm/ID"),
    "col_vgs": ("VGS", "VGS"),
    "col_vds": ("VDS", "VDS"),
    "col_vdsat": ("Vdsat", "Vdsat"),
    "col_gain": ("gm/gds", "gm/gds"),
    "col_target_gmid": ("→ gm/ID", "→ gm/ID"),
    "col_target_L": ("→ L [µm]", "→ L [µm]"),
    "hint_target": ("Set '→ gm/ID' (and optional '→ L') for devices to size;"
                    " leave blank to lock.",
                    "サイズ調整するデバイスに「→ gm/ID」（必要なら「→ L」も）を"
                    "入力。空欄はロック。"),
    "converged": ("Converged after %d iterations", "%d回の反復で収束しました"),
    "not_converged": ("Not converged (last ΔW=%.1f%%)",
                      "収束せず（最終 ΔW=%.1f%%）"),
    "no_netlist": ("Load a netlist first", "先にネットリストを読み込んでください"),
    "off_device": ("off", "OFF"),
    "loaded_n": ("Loaded: %d MOS devices, %d other PDK devices",
                 "読み込み完了: MOS %d個、その他PDKデバイス %d個"),
    "pushed": ("Pushed W/L to Virtuoso (see log)", "VirtuosoへW/Lを反映しました"),
    # topology
    "topology": ("Topology", "トポロジー"),
    "design": ("Design", "設計"),
    "verify": ("Spectre verify", "Spectre検証"),
    "spec": ("Specification", "仕様"),
    "devices_table": ("Devices (LUT sizing)", "デバイス（LUTサイジング）"),
    "metrics": ("Predicted metrics", "予測性能"),
    "verified": ("Verified metrics", "検証結果"),
    "netlist_view": ("Verification netlist", "検証ネットリスト"),
    "topo_cs": ("Common-source stage", "ソース接地段"),
    "topo_ota5t": ("5T OTA", "5トランジスタOTA"),
    "topo_miller": ("Two-stage Miller OTA", "2段ミラーOTA"),
    "vdd": ("VDD [V]", "VDD [V]"),
    "gbw": ("GBW [Hz]", "GBW [Hz]"),
    "cl": ("CL [F]", "CL [F]"),
    "pm": ("Phase margin [°]", "位相余裕 [°]"),
    "vcm": ("Input CM [V]", "入力コモンモード [V]"),
    "gmid1": ("M1 gm/ID", "M1 gm/ID"),
    "l1": ("M1 L [µm]", "M1 L [µm]"),
    "gmid2": ("Stage2/load gm/ID", "2段目/負荷 gm/ID"),
    "l2": ("Stage2/load L [µm]", "2段目/負荷 L [µm]"),
    "gmid_in": ("Input pair gm/ID", "入力対 gm/ID"),
    "l_in": ("Input pair L [µm]", "入力対 L [µm]"),
    "gmid_ld": ("Mirror load gm/ID", "ミラー負荷 gm/ID"),
    "l_ld": ("Load L [µm]", "負荷 L [µm]"),
    "gmid_tail": ("Tail gm/ID", "テール gm/ID"),
    "l_tail": ("Tail L [µm]", "テール L [µm]"),
    "a0_db": ("DC gain A0 [dB]", "直流利得 A0 [dB]"),
    "a1_db": ("Stage1 gain [dB]", "1段目利得 [dB]"),
    "a2_db": ("Stage2 gain [dB]", "2段目利得 [dB]"),
    "gbw_hz": ("GBW [Hz]", "GBW [Hz]"),
    "pm_deg": ("Phase margin [°]", "位相余裕 [°]"),
    "p2_hz": ("2nd pole [Hz]", "第2極 [Hz]"),
    "cc": ("Comp. cap Cc [F]", "補償容量 Cc [F]"),
    "rz": ("Nulling Rz [Ω]", "ゼロ消去抵抗 Rz [Ω]"),
    "itotal": ("Total current [A]", "総電流 [A]"),
    "power": ("Power [W]", "消費電力 [W]"),
    "vout_min": ("Vout min [V]", "出力下限 [V]"),
    "vout_max": ("Vout max [V]", "出力上限 [V]"),
    "vcm_min": ("VCM min [V]", "VCM下限 [V]"),
    "vcm_max": ("VCM max [V]", "VCM上限 [V]"),
    "tail_node": ("Tail node [V]", "テールノード [V]"),
    "vout_dc": ("Vout DC [V]", "出力DC [V]"),
    "vout1_dc": ("Stage1 out DC [V]", "1段目出力DC [V]"),
    "vsg6_design": ("M6 VSG design [V]", "M6 VSG 設計値 [V]"),
    "vsg6_available": ("M6 VSG available [V]", "M6 VSG 実際値 [V]"),
    "role_input": ("input", "入力"),
    "lib_cell": ("Lib / Cell", "ライブラリ / セル"),
    # passives
    "resistor": ("Resistor", "抵抗"),
    "mimcap": ("MIM capacitor", "MIM容量"),
    "bjt": ("BJT", "BJT"),
    "rtype": ("Type", "種類"),
    "target_r": ("Target R [Ω]", "目標 R [Ω]"),
    "target_c": ("Target C [F]", "目標 C [F]"),
    "measure": ("Measure", "測定"),
    "solve_l": ("Solve L", "L を解く"),
    "solve_size": ("Solve size", "サイズを解く"),
    "sweep_vbe": ("Sweep VBE", "VBE掃引"),
    "model": ("Model", "モデル"),
    # characterization
    "char_title": ("Generate MOS gm/id LUTs (Spectre DC sweeps L × VSB × VDS × VGS)",
                   "MOS gm/id LUT生成（Spectre DC掃引 L × VSB × VDS × VGS）"),
    "parallel": ("Parallel jobs", "並列ジョブ数"),
    "start_char": ("Start", "開始"),
    "existing_luts": ("Existing LUTs", "既存LUT"),
    "char_running": ("Characterizing… %d/%d", "特性抽出中… %d/%d"),
    "char_done": ("Done", "完了"),
    "no_lut": ("(none — characterize first)", "（なし — 先に特性抽出してください）"),
}

_lang = "en"


def set_lang(lang):
    global _lang
    _lang = lang if lang in LANGS else "en"


def get_lang():
    return _lang


def tr(key):
    e = _T.get(key)
    if e is None:
        return key
    return e[1] if _lang == "ja" else e[0]
