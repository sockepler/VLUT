# VLUT 使用マニュアル

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

## 3. PDK の設定(差し替え)

PDK は `pdks/<名前>.yaml` に記述します。ファイルを追加するだけで
ツールバーの PDK メニューに現れます。

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

## 5. トラブルシューティング

| 症状 | 原因と対策 |
|------|-----------|
| 「LUT not found」 | 対象デバイス×コーナーが未抽出 → 特性抽出タブで生成 |
| 特性抽出が CMI-2215 で失敗 | グリッドの L がモデルの lmin 未満 → yaml のグリッドを修正 |
| OP実行が SFE-675 | モデル include の section 不正 → 自動リマップされるはず。ログの `[remap]` を確認 |
| OP実行で「no components」 | テストベンチのない cell ネットリスト(バイアスなし) |
| 反復が収束しない | 目標 gm/ID がバイアス的に実現不可能(電流源が飽和しない等)。ログの ΔW と OP を確認し、目標を緩める |
| GUI が起動しない | X11/DISPLAY を確認。SSH なら `ssh -X` |
| Virtuosoへ反映が失敗 | virtuoso-bridge が起動しているか、Virtuoso 側で CIW `load(...)` 済みかを確認 |

## 6. ディレクトリ構成

```
pdks/*.yaml        PDK 定義(ここを書けば PDK 追加)
gmid/              Python パッケージ(解析エンジン + GUI)
  char_mos.py      LUT 特性抽出(並列 Spectre)
  lut.py           LUT 補間・逆引き・サイジング
  netlist.py       ADE ネットリスト解析/編集/OP デッキ生成
  designer.py      gm/ID 反復サイジング
  topologies.py    内蔵トポロジー設計
  verify.py        検証テストベンチ生成
  passives.py      R/MIM/BJT 計算
  qtgui/           PyQt5 GUI(タブごとに 1 モジュール)
luts/              生成された LUT(.npz、git 管理外)
work/              Spectre 作業ディレクトリ(git 管理外)
```
