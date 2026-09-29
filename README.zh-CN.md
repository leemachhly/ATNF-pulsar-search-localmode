# 脉冲星参数查取中心（本地 · ATNF）

B 名 / J 名互查，DM · RM · P0 · F1 · 流量 · 脉冲宽度 · 双星与自转参数（含派生 AGE / Bsurf / Edot），默认 **14 天**自动从 ATNF 更新。

**整个程序都在本文件夹内**，拷贝到 Windows / Linux / macOS 任意位置即可运行（需 Python 3.9+，无第三方依赖）。

## 功能

- **J 名 ↔ B 名** 互查（`J0826+2637` / `B0823+26` / 部分名模糊搜索）
- **参数表**：P0、F0、F1、DM、RM、坐标、流量、W50/W10、PB/ECC、AGE/Bsurf/Edot、TYPE…
- **派生参数**（psrcat.db 原始文件不含，本地计算，见下表）
- **详情页**：展示该源在 ATNF 中的**全部字段**，可一键把新字段加到常用列
- **筛选**：J 名 / B 名 / DM 范围；快捷标签（有 B 名、MSP、高能关联、双星）
- **双主题**（右上角切换并记忆）：
  - **蓝底白字**（默认）— 蓝底、参数白色加粗
  - **白底黑字** — 浅色主题，适合打印/截图
- **语言切换**（右上角切换并记忆）：
  - **English**（默认）
  - **中文**
- **更新**：默认 14 天；UI「立即更新 ATNF」或改 `config.json` 的 `update_interval_days`
- **自包含**：整夹可拷；另提供便携 zip

## 一键启动（Windows / Linux 通用）

| 系统 | 命令 |
|------|------|
| **Windows** | 双击 `start.bat`，或在终端执行 `start.bat` |
| **Linux / macOS** | `./start.sh` 或 `sh start.sh` |
| **通用** | `python start.py` / `python3 start.py` |

启动后自动：建库（若缺失）→ 检查更新（按 14 天策略）→ 开服务 → 打开浏览器 <http://127.0.0.1:8787/>。

### 启动参数

```bash
python start.py --port 8790      # 换端口
python start.py --no-browser     # 只起服务，不弹网页
python start.py --no-update      # 启动时不自动更新 ATNF
python start.py --build-only     # 仅确保本地数据库存在
python start.py --help
```

### 仅更新数据库

```bash
python update_db.py              # 下载（若需要）并重建 SQLite
python update_db.py --offline    # 不联网，用 data/psrcat.db 重建
python update_db.py --force      # 强制重新下载 ATNF 包
```

## 网页界面

| 控件 | 位置 | 说明 |
|------|------|------|
| **语言** `EN` / `中文` | 右上角 | 全站文案切换，选择记在浏览器 |
| **主题** `蓝底白字` / `白底黑字` | 右上角 | 两套配色，选择记在浏览器 |
| 搜索框 | 左侧 | J 名 / B 名 / 关键字；下拉可选 DM 范围 |
| 快捷标签 | 搜索下方 | 全部 · 有 B 名 · 毫秒星 · 高能关联 · 双星 |
| 表头 | 表格 | 点击排序 |
| 详情面板 | 右侧 | 全部 ATNF 字段 +「添加字段」扩展主表列 |
| 刷新 / 更新 ATNF | 右上角 | 刷新状态；强制更新目录 |

## 派生参数

原始 `psrcat.db` 只存测量值（`P0`/`P1` 或 `F0`/`F1`、DM、RM 等），特征年龄与自转能损等在建库时本地计算：

| 参数 | 公式 |
|------|------|
| `AGE` (yr) | `P0 / (2·P1)` |
| `BSURF` (G) | `3.2e19 · √(P0·P1)` |
| `EDOT` (erg/s) | `4π²·I·P1/P0³`（I = 10⁴⁵ g cm²） |
| `BLC` (G) | `BSURF · (R_NS/R_LC)³`，`R_LC = c·P0/(2π)` |

缺失时还会自动换算：`P0 = 1/F0`，`P1 = -F1/F0²`（以及逆变换）。  
仅对自转减慢源（`P1 > 0`）计算；详情页中带 `derived` 标记。

## 目录结构（自包含，可整夹拷贝）

```
pulsar_center/
├── start.py            # 通用启动入口
├── start.bat           # Windows 启动
├── start.sh            # Linux / macOS 启动
├── server.py           # HTTP 服务 + API
├── update_db.py        # ATNF 下载 / 解析 / 建库
├── config.json         # 字段、端口、更新周期
├── static/index.html   # 网页界面（双主题 + EN/中文）
├── data/               # 本地生成（.gitignore 排除）
│   ├── psrcat.db       # ATNF 原始目录缓存
│   ├── pulsars.sqlite  # 本地查询库
│   └── meta.json       # 更新时间 / 版本 / 下次到期
├── .gitignore
├── README.md           # 英文文档（GitHub 默认）
├── README.zh-CN.md     # 本文档
└── _smoke_test.py      # 可选自检
```

## 添加 / 修改参数

编辑 `config.json`：

```jsonc
{
  "update_interval_days": 14,
  "core_fields": ["PSRJ", "PSRB", "P0", "DM", "RM", "..."],
  "display_fields": ["PSRJ", "PSRB", "P0", "DM", "RM", "..."]
}
```

- `core_fields`：需要保留的 ATNF 字段名（见 <https://www.atnf.csiro.au/research/pulsar/psrcat/psrcat_definition.html>）
- `display_fields`：界面默认列
- `update_interval_days`：自动更新周期（默认 14）
- `field_labels`：可选显示名
- 也可以在网页详情页 **「添加字段」** 直接写 ATNF 字段名（如 `S1500`、`DM1`、`PX`、`MINMASS`）

改完配置后执行：

```bash
python update_db.py --offline
```

## API（便于脚本调用）

```
GET  /api/status
GET  /api/search?q=J0826&field=jname&limit=50
GET  /api/pulsar/J0826+2637
GET  /api/fields
POST /api/update
POST /api/config          # {update_interval_days, display_fields, ...}
POST /api/field           # {name:"S1500", display:true}
```

## 自动更新（每 14 天）

1. **默认**：`start.py` / `server.py` 启动时若缓存超过 `update_interval_days`，后台自动跑 `update_db.py`。
2. **可选 Windows 计划任务**：

```bat
schtasks /Create /TN "ATNF_PulsarCenter_Update" /SC DAILY /MO 14 ^
  /TR "python D:\path\to\pulsar_center\update_db.py" /F
```

3. **可选 Linux cron**（每 14 天）：

```cron
0 4 */14 * *  cd /path/to/pulsar_center && python3 update_db.py >> update.log 2>&1
```

## 说明

- 数据来自 **ATNF Pulsar Catalogue**（Manchester et al. 2005, AJ 129, 1993）。
- 全表约 4000+ 颗脉冲星；启动后搜索支持模糊匹配。
- 无第三方依赖，仅用 Python 标准库。
- 界面语言与主题偏好存在浏览器 `localStorage`，不写服务器配置。
