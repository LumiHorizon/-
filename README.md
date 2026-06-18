# 天才交易员的投资知识库

把 B站博主**青枫浦上Q（赛博青哥）**的早盘/复盘/视频内容蒸馏成可复用的投资框架，配套 A股取数脚本与一个 Claude Code Skill。**clone 到任意机器即可让 Claude Code 按博主框架分析个股。**

---

## 目录结构

```
.
├── README.md                      # 本文件
├── 蒸馏/                          # ★ 所有蒸馏与框架 md
│   ├── 框架规律库.md               # ★ 可复用规律库（按场景分类，先读这个）
│   ├── framework_qingge.md        # ★ 完整方法论（情绪周期/宏观/选股体系）
│   ├── 青枫浦上Q_逐月蒸馏.md        # 逐月汇总
│   ├── 青枫浦上Q_视频蒸馏.md        # 视频汇总
│   ├── 青枫浦上Q_动态蒸馏.md        # 动态汇总
│   ├── distill_YYYY-MM-DD_morning.md  # 每日早盘蒸馏
│   ├── distill_YYYY-MM-DD_review.md   # 每日复盘蒸馏
│   └── distill_YYYY-MM_videos.md      # 当月视频蒸馏
├── skills/qfps-stock/SKILL.md     # ★ Claude Code Skill（跨项目/跨机复用）
│
│  # —— 取数 / 选股 / 出图 ——
├── em_fetch.py                    # ★ 东方财富取数（实时行情+历史K线，稳定直连）
├── boll7_scan.py                  # 七轨布林线选股扫描（筛买入区标的）
├── make_ppt_2026-06-11.py         # PPT 生成模板脚本（python-pptx）
│
│  # —— B站抓取脚本 ——
├── bili_space.py                  # 抓 UP 空间全部动态（最全、可翻历史）
├── bili_feedall_deep.py           # 深翻关注动态、解锁付费长文（OPUS动态）
├── batch_subtitle_dl.py           # 按月批量下载视频字幕 → subtitles/
├── asr_transcribe.py              # 视频无字幕时的 whisper 语音转写兜底
│
│  # —— 数据文件（脚本的原料/进度）——
├── qfps_all_deep.json             # 动态正文存档（蒸馏原始语料，--resume 累积）
├── qfps_all_deep.offset           # 动态抓取的翻页书签/进度光标
├── qfps_video_catalog.json        # 视频目录（time/bvid/title），下字幕的索引
└── subtitles/                     # 视频字幕原文
```

> `★` = 核心文件。`models/`（1.5G 语音模型）和 `cookie.txt`（B站登录凭证）已被 `.gitignore` 排除，不入库。

---

## 文件用途速览

| 文件 | 用途 |
|---|---|
| `蒸馏/框架规律库.md` | 从历次蒸馏提炼的规律，按"节奏/性质/选股/避险/产业"分类，带快速索引 |
| `蒸馏/framework_qingge.md` | 博主完整方法论：情绪周期、宏观传导、选股纪律 |
| `蒸馏/distill_*_morning/review.md` | 每天的进攻方向、关键信号、行动清单、可复用框架 |
| `em_fetch.py` | `from em_fetch import quotes, secid, kline`，取实时行情/前复权日K |
| `boll7_scan.py` | 七轨布林线扫描，筛当前处于买入区的标的 |
| `skills/qfps-stock/` | 让任意 Claude Code 项目自动调用本知识库的 Skill |

---

## 数据流水线

两条线把博主原始内容变成 `蒸馏/` 里的成品：

```
动态线：bili_feedall_deep.py ──► qfps_all_deep.json (+.offset 进度)
                                      └─► 蒸馏 ──► distill_*_morning/review.md

视频线：qfps_video_catalog.json ──► batch_subtitle_dl.py ──► subtitles/
                                      └─► 蒸馏 ──► distill_*_videos.md
        （视频无字幕时用 asr_transcribe.py 做 whisper 语音转写兜底）
```

- 动态抓取靠 `--resume` + `.offset` 增量累积，**不覆盖历史**。
- 取数/分析用 `em_fetch.py`，选股用 `boll7_scan.py`，出图用 `make_ppt_2026-06-11.py`（模板）。

---

## 在其他机器接入（Claude Code）

```bash
# 1. 克隆
git clone git@github.com:Bubbling-Cola/-.git ~/qfps-kb

# 2. 激活 Skill（用户级，所有项目可用；软链接以便随 git 更新）
mkdir -p ~/.claude/skills
ln -s ~/qfps-kb/skills/qfps-stock ~/.claude/skills/qfps-stock

# 3. 用前拉取最新蒸馏
cd ~/qfps-kb && git pull
```

之后在任意项目里说"按博主框架分析某股 / 判断买卖 / 解读盘面"，Claude 会自动读框架+最近蒸馏、用 `em_fetch.py` 取数后给出判断。

---

## 日常维护（主机）

```bash
# 每天蒸馏完
git add -A && git commit -m "蒸馏 YYYY-MM-DD" && git push
```

---

## 注意事项

- **价格数据只用东方财富**（`em_fetch.py`），不用 baostock。
- **展示标的须标注板块**：主板 / 创业板 / 科创板 / 北交所。
- **取数依赖本机网络**：`em_fetch.py` 走东财直连 + DNS pinning，换机器若取数失败需按脚本注释重新探测可用 IP（框架与蒸馏等纯文本不受影响）。
- 抓取动态须加 `--resume`，禁止覆盖历史数据。
- 仓库含博主内容的二次整理，**请保持私有**。
- 内容为投资研究记录，**不构成投资建议**。
