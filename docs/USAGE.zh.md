# VLUT 使用手册（中文）

> 语言 / 言語: **中文** · [日本語](USAGE.ja.md)

**VLUT** 是一款基于 gm/id 方法的模拟电路设计工具。它用本机的 Cadence
Spectre 把晶体管特性做成查找表（LUT），在桌面 GUI 里浏览特性曲线、算尺寸、
做拓扑设计，并对 **ADE 网表做迭代定尺寸**。设计参考了
[ADT (Analog Designer's Toolbox)](https://adt.master-micro.com/)。

---

## 1. 运行环境

| 项目 | 要求 |
|------|------|
| 操作系统 | Linux（需要 X11，已在 RHEL8 验证） |
| 仿真器 | Cadence Spectre（`spectre` 在 PATH 中） |
| Python | 3.9 以上（脚本会自建 venv） |
| PDK | Spectre 模型库（带 corner section 的 `.lib`） |
| 原理图联动（可选） | virtuoso-bridge（local 模式） |

## 2. 安装与启动

```bash
git clone https://github.com/sockepler/VLUT.git && cd VLUT
./install.sh        # 建 venv + 装依赖 + 注册 vlut 命令 + ADE 插件自启
cp pdks/example.yaml.template pdks/my_pdk.yaml   # 写自己的 PDK
vlut                # 启动桌面 GUI（也可 ./start.sh）
```

`install.sh` 会自动选一个 3.9 以上的 Python 建 venv，把启动器放到
`~/.local/bin/vlut`（必要时往 `~/.bashrc` 加 PATH），并把 Virtuoso ADE
插件注册到 `~/.cdsinit` 自启（用 `--no-plugin` 跳过）。

- 界面语言（English / 日本語）和 PDK 在工具栏切换，选择会保存到下次启动。
- 工艺角（tt/ff/ss/…）也在工具栏选，所有页面统一生效。

## 3. 配置 / 新增 PDK

### 3.1 在 GUI 里新建 PDK（推荐）

点工具栏 **＋ Add PDK** 打开对话框，不用手写 yaml：

1. **Browse** 选一个 Spectre 模型库（带 `section` 的 corner `.lib`）——就是你
   ADE 里 "Setup → Model Libraries" 指向的那个文件。
2. 工具自动扫描（会跟随 `include`），列出 **corner section** 和 **BSIM MOS
   模型名（含极性）**。选对文件后会显示绿色提示"检测到 N 个 corner、M 个模型"；
   选错（如裸 `.mdl`/`.ckt`）会红色提示该选哪种文件。
3. 勾选要登记的 corner（默认 tt/ff/ss）和模型。每个模型的 Vmax 从名字自动
   猜（含 "33" 视为 3.3V），可改。
4. 设置抽出网格（L 列表、VSB、步长，有默认值）。
5. **Save** 写出 `pdks/<名字>.yaml` 并自动切换到该 PDK。会按 Vmax 分组建
   grid，3.3V 系自动剔除小于 lmin 的 L；BJT/电阻/MIM 的 section 若存在会自动
   补上（器件名可后续在 yaml 里补）。

之后到"器件表征"页就能给这个 PDK 生成 LUT。对话框内容过长时可滚动
（Save/Cancel 固定在底部）。

### 3.2 直接写 yaml

把 `pdks/<名字>.yaml` 放进去也会出现在 PDK 菜单里。格式：

```yaml
name: my_pdk180
title: "My 0.18um PDK"
model_lib: /path/to/models/spectre/xxx.lib   # 带 section 的 corner lib
mos_corners: [tt, ff, ss]
default_corner: tt
grids:                      # 抽出扫描网格（共享预设）
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

要点：

- `wchar` 是抽出时的基准栅宽；结果按 W 归一化，建议取宽一点（10µm 左右）。
- 若 MOS 模型的 `lmin` 大于网格里最小的 L 会报错（如 CMI-2215）。native 等
  器件请单独配网格。
- LUT 存到 `luts/<pdk名>_<器件>_<corner>.npz`。

## 4. 各页面用法

### 4.1 器件表征（Characterize）

首次使用先跑一次，生成 LUT：

1. 勾选目标 MOS 器件
2. 设 corner（工具栏）、温度、并行任务数
3. **Start** —— 每个 (L, VSB) 起一个 Spectre 任务（一个器件一个 corner
   约 1 分钟 / 6 并行）

抽出的 OP 参数：ids, vth, vdsat, gm, gds, gmbs, cgg, cgs, cgd, cgb, cdd,
css（四维网格 L × VSB × VDS × VGS）。

### 4.2 特性曲线（Curves）

任意派生量互相作图。X/Y 可选 gm/ID、ID/W、gm/gds、fT、Vth、Vdsat、Vov、
各种电容等；支持多 L 叠画、指定 VDS/VSB、对数轴、matplotlib 工具栏缩放/保存。

常用：

- **ID/W vs gm/ID** —— 电流密度设计图（定尺寸的基础）
- **fT vs gm/ID** —— 速度与效率的折中
- **gm/gds vs gm/ID** —— 各 L 的本征增益

### 4.3 查询 / 尺寸（Query / Size）

单点查询与 W 计算：

- 输入：器件、L、VDS、VSB + 「gm/ID」「VGS」「Vov」之一
- 输出：全部 OP 参数（含 fT、gm/gds、ID/W）
- 再在「尺寸目标」给定 gm 或 ID，可反推 **所需 W**

### 4.4 网表设计（Netlist Designer）—— 核心功能

读入 ADE 生成的网表，在真实偏置下做 gm/ID 迭代定尺寸。

**步骤：**

1. **Browse** 选 ADE 的 netlist 目录（有 `input.scs` 的那个），点 **Load**。
   - 同时支持 maestro 布局（`input.scs` + `include "netlist"`）和 si 直接
     导出（电路内联在 input.scs）
   - 不改原目录（复制到 `work/design/` 里操作）
2. 表格列出所有 MOS（自动识别 subckt 层次、`_ckt` 封装、`m=`/`mr=` 乘数）。
   点 **Run OP** 显示各管实测 ID / gm/ID / VGS / VDS / Vdsat / gm/gds。
3. 给要调的器件填 **「→ gm/ID」**（需要的话也填 **「→ L」**）。留空的器件
   锁定不变。
4. 设 **单体 W 上限 [µm]**（默认 10）。算出的总 W 会拆成若干个不超过该上限的
   单体 W × m 并联。
5. **Iterate** —— OP → 查 LUT 重算 W/m → 改网表 → OP …… 直到 W 收敛
   （一般 3~5 次）。
6. 保存结果：
   - **Save netlist** —— 导出定好尺寸的网表
   - **Push to Virtuoso** —— 经 virtuoso-bridge 直接改各原理图实例的
     `w` / `l` / `m`（`mr`）属性（用网表里 `// Library / Cell name` 注释
     定位目标 cell）

**说明：**

- 定尺寸改的是 subckt 母版，同一 subckt 的多个实例一起变（和改原理图一样）。
- `as/ad/ps/pd/nrd/nrs` 随单体 W 重算。
- 指向旧 PDK 的模型 include 会自动重映射到当前 PDK（对应 section、去重、无
  section 的 `.lib` 展开）；日志里 `[remap]` 行可查。
- ADE 里没赋值的设计变量（如 `parameters Vos`）会补 0。
- 差分对 / 电流镜等对称器件各自按实测 ID 独立定尺寸，收敛后 W 可能相差
  <1%；要严格一致就保存后手工对齐。
- 没测试台的裸 cell 网表也能读，但没偏置，OP 全零、无法迭代。

### 4.5 拓扑设计（Topologies）

内置拓扑的 gm/id 设计 + Spectre 验证：

| 拓扑 | 内容 |
|------|------|
| 共源级 | NMOS 输入 + PMOS 电流源负载 |
| 五管 OTA | NMOS 差分对 + PMOS 镜像 + 尾电流 |
| 两级 Miller OTA | 上述 + PMOS 共源第二级、Cc + Rz 补偿 |

填规格（GBW、CL、相位裕度、各处 gm/ID·L）→ **Design** 显示 W/L/ID 表和
预测指标（A0/GBW/PM/功耗/摆幅）→ **Spectre verify** 用真实模型跑 AC（用大
电感闭 DC 环的方式），显示实测 A0/GBW/PM 和 Bode 图。LUT 预测与实测通常在
2dB / 几个百分点内吻合。

### 4.6 无源器件 / BJT（Passives / BJT）

- **电阻**：给 W/L 实测，或给目标 R 反解 L（Spectre 单点）
- **MIM 电容**：给尺寸实测，或给目标 C 反解方形边长
- **BJT**：扫 VBE 出 |IC| 与 β 曲线（带隙设计用）

## 5. Virtuoso ADE 插件（不开 GUI，在 ADE 里直接跑）

把 `virtuoso/vlut_ade.il` 载入 Virtuoso 后，可以在 ADE 里做 gm/ID 扫描定
尺寸，并用 ADE/OCEAN 公式挑最优点。

### 5.1 载入

```
load("/path/to/VLUT/virtuoso/vlut_ade.il")
```

**每次自启**只需执行一次：

```
virtuoso/install_plugin.sh            # 往 ~/.cdsinit 加一段带保护的 load
virtuoso/install_plugin.sh --uninstall
```

（`install.sh` 在没加 `--no-plugin` 时会自动做这一步。）加载行带
`when(isFile ...)` 保护，文件不存在也不会中断 Virtuoso 启动。**VLUT** 菜单会
同时出现在 **CIW** 和 **每个 ADE Explorer / Assembler（Maestro）窗口内**
（通过窗口触发器自动注册，开 Maestro 就有）。三项：

- **Netlist current ADE/Maestro into VLUT…** —— 把当前打开的 ADE/Maestro
  会话网表化并一键导入表单
- **gm/ID Sweep Sizing…** —— 扫描定尺寸表单
- **PDK / LUT Manager…** —— 切换 PDK、表征 LUT

### 5.2 gm/ID Sweep Sizing 表单

**除数字和 parameter 外都不用手打**：目录用文件浏览，corner/PDK/器件/网名/
指标全是下拉或多选列表。

1. 导入网表（任选其一）：
   - **从 Maestro/ADE 一键**：开着 ADE Explorer/Assembler，用 CIW 菜单
     **Netlist current ADE/Maestro into VLUT…**，或表单上的 **Netlist open
     ADE/Maestro → import** 按钮。自动把当前会话网表化（`asiNetlist`）、读入
     其 netlist 目录并扫描（不用浏览）。
   - **手动**：**…or Browse netlist dir** 选有 `input.scs` 的目录，再点
     **Re-scan devices/nets** 解析。
2. **PDK / Corner** 下拉选择（corner 随 PDK 变）。
3. **扫描组（可多组）**：多选器件，填一串 gm/ID 值（`8 12 16`）和 L →
   **Add sweep group** 加入。加多组即可 **同时扫描**。**Combine** 选组合方式：
   - `product` = 各组所有组合（嵌套的二维及以上扫描）
   - `zip` = 各组等长、**同步**推进（锁步）
4. **固定组**：多选 Fixed devices + 填 Fixed gm/ID / L（数字）→ **Add fixed
   group** 加入固定组（可多组，**Clear** 清空）。
5. **Analysis**（ac/tran/dc）与 **Metric**。指标由 **net**/**net2** 下拉和
   **t1/t2/阈值** 数字自动拼成 ADE 公式：
   - AC 类：直流增益、相位裕度、GBW、单位增益频率、带宽
   - **tran（时间）类**：`V(net) at t1`、`dV net t1→t2`（两时刻电压差）、
     `dV (net−net2) at t1` / `|net−net2| at t1`（差分，如比较器输出）、
     `cross time @thr`（网穿过阈值的时刻＝判定时间）、
     `settle t (net vs net2 @thr)`（比较器建立＝\|net−net2\| 达到阈值的时刻）、
     `delay net→net2 @thr`、`peak-to-peak`
   例：`value(v("out") 5e-7)-value(v("out") 1e-9)`、
   `cross(abs(v("outp")-v("outn")) 0.9 1 "rising")`。**Goal** 选最大化/最小化。
   （用时间类指标记得把 Analysis 选成 tran。）
6. **Run sweep** —— 每个扫描点定尺寸（OP→LUT→OP）后跑网表自带分析；完成后
   在每点求指标，**Results** 表标出最优点。
7. **Plot metric vs gm/ID**（ViVA 指标曲线）、**Plot best waveform**（最优点
   波形）、**Apply best to schematic**（把最优 w/l/m 写回原理图）。

要用不常见的公式，可在 `vlut_ade.il` 顶部的 `VLUTMetricTypes` /
`VLUTWaveTypes` 里加一行（`("标签" "带 @net@/@t1@… 占位符的公式")`）。

### 5.3 PDK / LUT Manager 表单

- 选 **PDK** 后显示每个器件已表征了哪些 corner。
- **Characterize LUTs** —— 指定器件/corner/温度/并行数，后台表征（进度打到
  CIW）。
- 往 `pdks/` 加了新 yaml 后，点 **Refresh status** 刷新。

## 6. 疑难排查

| 现象 | 原因与对策 |
|------|-----------|
| “LUT not found” | 该器件×corner 还没表征 → 到"器件表征"页生成 |
| 表征报 CMI-2215 | 网格的 L 小于模型 lmin → 改 yaml 网格 |
| Run OP 报 SFE-675 | 模型 include 的 section 不对 → 一般会自动重映射，看日志 `[remap]` |
| Run OP 报 “no components” | 没测试台的裸 cell 网表（无偏置） |
| 迭代不收敛 | 目标 gm/ID 在该偏置下不可达（电流源没饱和等）→ 看日志 ΔW 与 OP，放宽目标 |
| GUI 起不来 | 检查 X11/DISPLAY；SSH 用 `ssh -X` |
| Push to Virtuoso 失败 | 确认 virtuoso-bridge 已启动、Virtuoso 侧 CIW 已 `load(...)` |
| 插件表单 Browse 没反应 | 没装 `zenity`；手填路径或安装 zenity |
| 插件扫描后器件为空 | 弹框会提示；多半是表单里选的 PDK 与网表器件型号不匹配 |

## 7. 目录结构

```
pdks/*.yaml        PDK 定义（GUI 的 ＋Add PDK 或手写）
pdks/example.yaml.template  PDK 模板
gmid/              Python 包（分析引擎 + GUI）
  char_mos.py      LUT 表征（并行 Spectre）
  lut.py           LUT 插值 / 反查 / 定尺寸
  pdk.py / pdkscan.py  PDK 定义读取 / 模型库扫描
  netlist.py       ADE 网表解析/编辑/OP deck 生成
  designer.py      gm/ID 迭代定尺寸（W + multiplier）
  topologies.py    内置拓扑设计
  verify.py        验证测试台生成
  passives.py      R/MIM/BJT 计算
  cli.py           vlut-cli（插件用的无界面引擎）
  qtgui/           PyQt5 GUI（每页一个模块 + 新建 PDK 对话框）
virtuoso/vlut_ade.il      Virtuoso ADE 插件（SKILL）
virtuoso/install_plugin.sh  插件自启安装/卸载
luts/              生成的 LUT（.npz，不入库）
work/              Spectre 工作目录（不入库）
```
