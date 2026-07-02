# VLUT 使用マニュアル（日本語）

> 语言 / 言語: [中文](USAGE.zh.md) · **日本語**

**VLUT** は gm/id 手法に基づくアナログ回路設計ツールです。ローカルの
Cadence Spectre でトランジスタ特性をルックアップテーブル(LUT)化し、
デスクトップ GUI 上で特性カーブの閲覧・サイズ計算・トポロジー設計・
**ADE ネットリストの反復サイジング** を行います。
[ADT (Analog Designer's Toolbox)](https://adt.master-micro.com/) を参考に
実装しています。

---

## 1. 動作環境

| 項目 | 要件 |
|------|------|
| OS | Linux(X11 が必要。RHEL8 で動作確認) |
| シミュレータ | Cadence Spectre(`spectre` が PATH にあること) |
| Python | 3.11 以上(venv を作成) |
| PDK | Spectre 用モデルライブラリ(corner section 付き `.lib`) |
| 回路図連携(任意) | [virtuoso-bridge](https://github.com/…)(local モード) |

## 2. インストールと起動

```bash
git clone https://github.com/sockepler/VLUT.git && cd VLUT
./install.sh        # venv 作成 + 依存インストール + `vlut` コマンド登録
cp pdks/example.yaml.template pdks/my_pdk.yaml   # PDK を記述
vlut                # デスクトップGUI 起動(./start.sh でも可)
```

`install.sh` は Python 3.9 以上を自動選択して venv を作り、
`~/.local/bin/vlut` ランチャーを配置します(必要なら ~/.bashrc の
PATH にも追記)。

- 言語(English / 日本語)と PDK はツールバーで切り替え、選択は次回起動時も保持されます。
- コーナー(tt/ff/ss/…)もツールバーで選択します。全タブに反映されます。

## 3. PDK の設定・追加

### 3.1 GUI で新しい PDK を追加(推奨)

ツールバーの **＋ PDK追加** ボタンでダイアログが開きます。yaml を手書き
する必要はありません。

1. **参照** で Spectre のモデルライブラリ(section 付き `.lib` 等)を選択。
2. ライブラリを自動スキャンして、**コーナー section** と **BSIM MOS モデル
   名(極性つき)** を一覧表示します。
3. 登録するコーナー(既定 tt/ff/ss)とモデルにチェック。各モデルの Vmax は
   モデル名から自動推定(名前に "33" があれば 3.3V)、必要なら編集。
4. 抽出グリッド(L リスト・VSB・ステップ)を設定(既定値あり)。
5. **Save** で `pdks/<名前>.yaml` を書き出し、その PDK に自動で切り替わります。
   Vmax ごとにグリッドを分け、3.3V 系は lmin 未満の L を自動的に除外します。
   BJT/抵抗/MIM の section は存在すれば自動で追記されます(デバイス名は後で
   yaml に追記)。

追加後は特性抽出タブでその PDK の LUT を作成できます。
ダイアログは縦に長い場合スクロールできます(Save/Cancel は常に下部に固定)。

### 3.2 yaml を直接書く

`pdks/<名前>.yaml` を置くだけでも PDK メニューに現れます。書式:

```yaml
name: my_pdk180
title: "My 0.18um PDK"
model_lib: /path/to/models/spectre/xxx.lib   # section 付き corner lib
mos_corners: [tt, ff, ss]
default_corner: tt
grids:                      # 特性抽出の掃引グリッド(共有プリセット)
  g18:
    vmax: 1.8
    Ls: [0.18, 0.28, 0.5, 1.0, 2.0, 5.0]     # µm
    vsbs: [0.0, 0.3, 0.6, 0.9]               # V
    vgs_step: 0.02
    vds_step: 0.05
mos:
  nch: {polarity: n, grid: g18, wchar: 10e-6, desc: "core NMOS"}
  pch: {polarity: p, grid: g18, wchar: 10e-6, desc: "core PMOS"}
bjt:
  section: {tt: bjt_tt, ff: bjt_ff, ss: bjt_ss}
  models:
    pnp: [pnp_2x2, pnp_5x5]
res:
  section: {tt: res_tt, ff: res_ff, ss: res_ss}
  devices:
    rpoly: {subckt: rpoly_ckt, terms: 2, desc: "poly resistor"}
cap:
  section: {tt: mim_tt, ff: mim_ff, ss: mim_ss}
  devices:
    mim: {subckt: mim_ckt, desc: "MIM"}
```

ポイント:

- `wchar` は特性抽出時の基準ゲート幅。結果は W で正規化されるので
  広め(10µm 程度)を推奨。
- MOS モデルの `lmin` がグリッドの最小 L より大きいとエラー
  (CMI-2215 など)になります。native デバイス等は専用グリッドを
  用意してください。
- LUT ファイルは `luts/<pdk名>_<デバイス>_<コーナー>.npz` に保存されます。

## 4. 各タブの使い方

### 4.1 デバイス特性抽出(Characterize)

最初に一度実行して LUT を作成します。

1. 対象 MOS デバイスにチェック
2. コーナー(ツールバー)・温度・並列ジョブ数を設定
3. **開始** — L × VSB ごとに 1 つの Spectre ジョブが走ります
   (1 デバイス・1 コーナーあたり約 1 分/6 並列)

抽出される OP パラメータ: ids, vth, vdsat, gm, gds, gmbs, cgg, cgs,
cgd, cgb, cdd, css(4 次元グリッド L × VSB × VDS × VGS)。

### 4.2 特性カーブ(Curves)

任意の派生量同士をプロットします。X/Y は gm/ID・ID/W・gm/gds・fT・
Vth・Vdsat・Vov・各容量など。複数 L の重ね描き、VDS/VSB 指定、
log 軸切替、matplotlib ツールバーでのズーム・保存に対応。

代表的な使い方:

- **ID/W vs gm/ID** — 電流密度設計チャート(サイジングの基本)
- **fT vs gm/ID** — 速度と効率のトレードオフ
- **gm/gds vs gm/ID** — L ごとの本征利得

### 4.3 検索・サイズ(Query / Size)

1 点検索と W 計算。

- 入力: デバイス、L、VDS、VSB + 「gm/ID」「VGS」「Vov」のいずれか
- 出力: 全 OP パラメータ(fT、gm/gds、ID/W 含む)
- さらに「サイズ目標」に gm または ID を与えると **必要 W** を逆算

### 4.4 ネットリスト設計(Netlist Designer)— 中核機能

ADE が生成したネットリストを読み込み、実際のバイアス状態で
gm/ID 反復サイジングを行います。

**手順:**

1. **参照…** で ADE の netlist ディレクトリ(`input.scs` のある場所)を
   選択し **読み込み**。
   - maestro 形式(`input.scs` + `include "netlist"`)と si 直接出力
     (input.scs に回路がインライン)の両方に対応
   - 元ディレクトリは変更しません(`work/design/` に複製して作業)
2. テーブルに全 MOS が並びます(subckt 階層・`_ckt` ラッパー・
   `m=`/`mr=` 乗数を自動認識)。**OP実行** で各デバイスの実測
   ID / gm/ID / VGS / VDS / Vdsat / gm/gds が表示されます。
3. サイズ調整したいデバイスの **「→ gm/ID」** に目標値を入力
   (必要なら **「→ L」** も)。空欄のデバイスはロック(現状維持)。
4. **単体W上限 [µm]** を設定(デフォルト 10)。計算された総 W は
   この上限以下の単体 W × m 並列に自動分割されます。
5. **反復設計** — OP → LUT で W/m 再計算 → ネットリスト書換 → OP …
   を W が収束するまで繰り返します(通常 3〜5 回)。
6. 結果の保存:
   - **ネットリスト保存…** — サイズ済みネットリストを書き出し
   - **Virtuosoへ反映** — virtuoso-bridge 経由で各回路図の
     インスタンス `w` / `l` / `m`(`mr`)プロパティを直接更新
     (ネットリスト中の `// Library name / Cell name` コメントから
     対象セルを自動特定)

**補足:**

- サイジングは subckt マスターを書き換えます。同じ subckt の複数
  インスタンスは同時に変わります(回路図編集と同じ意味論)。
- `as/ad/ps/pd/nrd/nrs` は単体 W に追従して再計算されます。
- 旧 PDK を指すモデル include は現行 PDK に自動リマップされます
  (section 対応、重複除去、section なし `.lib` の展開)。内容は
  ログの `[remap]` 行で確認できます。
- 値なしの ADE 設計変数(`parameters Vos` など)は 0 が代入されます。
- 差動対・カレントミラー等の対称デバイスは各自の実測 ID で独立に
  サイジングされるため、収束後に W が僅かに(<1%)ずれます。
  完全一致が必要な場合は保存後に手で揃えてください。
- テストベンチのない素の cell ネットリストも読み込めますが、
  バイアスがないため OP は全ゼロになり反復はできません。

### 4.5 トポロジー設計(Topologies)

内蔵トポロジーのgm/id設計と Spectre 検証:

| トポロジー | 内容 |
|-----------|------|
| ソース接地段 | NMOS 入力 + PMOS 電流源負荷 |
| 5トランジスタOTA | NMOS 差動対 + PMOS ミラー + テール |
| 2段ミラーOTA | 上記 + PMOS ソース接地 2 段目、Cc + Rz 補償 |

仕様(GBW、CL、位相余裕、各部 gm/ID・L)を入力 → **設計** で
W/L/ID テーブルと予測性能(A0/GBW/PM/消費電力/振幅範囲)を表示。
**Spectre検証** で実モデルによる AC 解析(巨大インダクタで DC ループを
閉じる方式)を実行し、実測 A0/GBW/PM とボード線図を表示します。
LUT 予測と実測は通常 2dB / 数 % 以内で一致します。

### 4.6 受動素子・BJT(Passives / BJT)

- **抵抗**: W/L 指定で実測、または目標 R から L を逆算(Spectre 1 点解析)
- **MIM 容量**: サイズ指定で実測、または目標 C から正方形サイズを逆算
- **BJT**: VBE 掃引で |IC| と β のカーブを表示(バンドギャップ設計用)

## 5. Virtuoso ADE プラグイン(GUIを使わず ADE 内で実行)

`virtuoso/vlut_ade.il` を Virtuoso の CIW から読み込むと、ADE の中から
gm/ID スイープ・サイジングを実行し、ADE/OCEAN の計算式で最適点を選べます。

### 5.1 読み込み

```
load("/path/to/VLUT/virtuoso/vlut_ade.il")
```

**毎回自動で読み込む**には一度だけ実行:

```
virtuoso/install_plugin.sh            # ~/.cdsinit にガード付き load を追記
virtuoso/install_plugin.sh --uninstall
```

(`install.sh` が `--no-plugin` 以外なら自動で実行します)。ファイルが存在する
場合のみ load するため Virtuoso 起動を壊しません。**VLUT** メニューは CIW と
**各 ADE Explorer / Assembler（Maestro）ウィンドウの中**の両方に出ます
（`maestro`/`adexl` のウィンドウトリガーで自動登録されるので、Maestro を開けば
その中にメニューが現れます）。3 項目:

- **Netlist current ADE/Maestro into VLUT…** — 開いている ADE/Maestro
  セッションをネットリスト化してフォームに一発取り込み
- **gm/ID Sweep Sizing…** — スイープ・サイジングのフォーム
- **PDK / LUT Manager…** — PDK 切り替えと LUT 特性抽出

### 5.2 gm/ID Sweep Sizing フォーム

**数字とパラメータ以外は入力しません**。ディレクトリはファイル選択、
コーナー・PDK・デバイス・ネット・指標はすべてドロップダウンかリストです。

1. ネットリストの取り込み(いずれか):
   - **Maestro/ADE から一発**: ADE Explorer/Assembler を開いた状態で、
     CIW メニュー **Netlist current ADE/Maestro into VLUT…**、または
     フォームの **Netlist open ADE/Maestro → import** ボタン。開いている
     セッションを自動でネットリスト化(`asiNetlist`)し、その netlist
     ディレクトリを読み込んでスキャンします(参照不要)。
   - **手動**: **…or Browse netlist dir** で `input.scs` のあるフォルダを
     選び、**Re-scan devices/nets** で解析。
2. **PDK / Corner** をドロップダウンで選択(コーナーは PDK に追従)。
3. **スイープグループ**(複数可): デバイスをリスト選択し、gm/ID の値リスト
   （`8 12 16`）と L を入力 → **Add sweep group** で追加。複数グループを追加
   すれば**同時にスイープ**できます。**Combine** で組み合わせ方を選択:
   - `product` = 全組み合わせ（入れ子の 2 次元以上スイープ）
   - `zip` = 各グループを同じ長さのリストで**同時に**進める（ロックステップ）
4. **Fixed devices**(リスト選択)+ **Fixed gm/ID / L**(数字)+
   **Add fixed group** で固定グループを追加(複数可、**Clear** で消去)。
5. **Analysis**(ac/tran/dc)と **Metric** を選択。指標は **net**/**net2**
   ドロップダウンと **t1/t2/しきい値** の数値から ADE 式を自動生成します。
   - AC 系: DC利得・位相余裕・GBW・ユニティゲイン周波数・帯域幅
   - **tran(時間)系**: `V(net) at t1`、`dV net t1→t2`（2 時刻間の電圧差）、
     `dV (net−net2) at t1` / `|net−net2| at t1`（差動＝コンパレータ出力など）、
     `cross time @thr`（ネットがしきい値を横切る時刻＝判定時間）、
     `settle t (net vs net2 @thr)`（コンパレータ整定＝\|net−net2\| がしきい値に
     達する時刻）、`delay net→net2 @thr`、`peak-to-peak`
   例: `value(v("out") 5e-7)-value(v("out") 1e-9)`、
   `cross(abs(v("outp")-v("outn")) 0.9 1 "rising")`。**Goal** で最大化/最小化。
   （時間系を使うときは Analysis=tran にしてください。）
6. **Run sweep** — 各スイープ点でネットリストをサイジング(OP→LUT→OP)し、
   ADE 解析を実行。完了後、指標が各点で評価され、**Results** 表に最適点が
   マークされます。
7. **Plot metric vs gm/ID**(ViVA で指標曲線)、**Plot best waveform**
   (最適点の波形)、**Apply best to schematic**(最適サイズ w/l/m を回路図へ)。

一般的でない式を使いたい場合は `vlut_ade.il` 冒頭の `VLUTMetricTypes` /
`VLUTWaveTypes` に一行(`("ラベル" "式-ネット用%s")`)追記します。

### 5.3 PDK / LUT Manager フォーム

- **PDK** を選ぶと、各デバイスがどのコーナーの LUT を持っているか表示。
- **Characterize LUTs** — デバイス/コーナー/温度/並列数を指定して
  バックグラウンドで特性抽出(進捗は CIW に表示)。
- 新しい yaml を `pdks/` に追加したら **Refresh status** で反映。

## 6. トラブルシューティング

| 症状 | 原因と対策 |
|------|-----------|
| 「LUT not found」 | 対象デバイス×コーナーが未抽出 → 特性抽出タブで生成 |
| 特性抽出が CMI-2215 で失敗 | グリッドの L がモデルの lmin 未満 → yaml のグリッドを修正 |
| OP実行が SFE-675 | モデル include の section 不正 → 自動リマップされるはず。ログの `[remap]` を確認 |
| OP実行で「no components」 | テストベンチのない cell ネットリスト(バイアスなし) |
| 反復が収束しない | 目標 gm/ID がバイアス的に実現不可能(電流源が飽和しない等)。ログの ΔW と OP を確認し、目標を緩める |
| GUI が起動しない | X11/DISPLAY を確認。SSH なら `ssh -X` |
| Virtuosoへ反映が失敗 | virtuoso-bridge が起動しているか、Virtuoso 側で CIW `load(...)` 済みかを確認 |
| プラグインのフォームで Browse が反応しない | `zenity` が未インストール。パスを手入力するか zenity を導入 |

## 7. ディレクトリ構成

```
pdks/*.yaml        PDK 定義(GUI の ＋PDK追加 か手書きで作成)
pdks/example.yaml.template  PDK 記述テンプレート
gmid/              Python パッケージ(解析エンジン + GUI)
  char_mos.py      LUT 特性抽出(並列 Spectre)
  lut.py           LUT 補間・逆引き・サイジング
  pdk.py / pdkscan.py  PDK 定義の読み込み / モデルライブラリ走査
  netlist.py       ADE ネットリスト解析/編集/OP デッキ生成
  designer.py      gm/ID 反復サイジング(W + multiplier)
  topologies.py    内蔵トポロジー設計
  verify.py        検証テストベンチ生成
  passives.py      R/MIM/BJT 計算
  cli.py           vlut-cli(プラグイン用ヘッドレスエンジン)
  qtgui/           PyQt5 GUI(タブごとに 1 モジュール + PDK追加ダイアログ)
virtuoso/vlut_ade.il  Virtuoso ADE プラグイン(SKILL)
luts/              生成された LUT(.npz、git 管理外)
work/              Spectre 作業ディレクトリ(git 管理外)
```
