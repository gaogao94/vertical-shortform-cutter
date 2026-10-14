# vertical-shortform-cutter

[中文](README.md) · [English](README.en.md)

一个 **AI Agent 技能（skill）**：把一段长的口播视频剪成竖版短视频。

给它一段长录像——访谈、直播、讲座、培训——加上**逐词时间码**，它输出一条 20–60 秒的竖版成片，字幕只给关键信息变色。

**先读 [`SKILL.md`](SKILL.md)**，那是完整契约。本文件只是门面。

---

## 它做什么

| 步骤 | 命令 | 产出 |
|---|---|---|
| 读转写稿、推导关键词 | `build.py --list-only` | 打印转写稿 + 关键词表 |
| 按你的稿子定剪点 | `build.py --beats ... --phrases ...` | `script.txt`、`plan.json`、`captions.json` |
| 出片 | `render.py` | 竖版 MP4，字幕烧入，响度已标准化 |
| 封面 | `cover.py` | 封面图 |
| 封面作第一帧 | `add_cover.py` | 第一帧是封面的成片 |

切割、变速、响度标准化、烧字幕**合并成一次 FFmpeg 处理**。一条 30 秒成片在 2 核 CPU 上不到一分钟；用 React 逐帧渲染同样内容大约要 20 分钟——这个差距就是这条路线存在的理由。

## 它固化的方法论

顺序是关键，而且反直觉：

1. **先把转写稿通读一遍，写出你希望观众听到的稿子**——完整、按顺序、念得通。
2. **然后才**给稿子的每一句挑对应的源片段。
3. **开头放"问题"，不放"结论"。** 一段话里最有力的句子通常依赖前文铺垫，把它抽到第 0 秒只会让观众一头雾水。
4. **觉得节奏赶就加回内容 + 降语速。** 单降语速会让片子变短（时长 = 素材长度 ÷ 倍速），同样多的信息挤进更短时间，"赶"的感觉反而更重。

---

## 关于 OpenMontage

**这个 skill 与 [OpenMontage](https://github.com/calesthio/OpenMontage) 无关，也不依赖它。**

它是独立的一套脚本，只依赖 **ffmpeg + Python 标准库**。你不需要装 OpenMontage 就能用。

**那为什么值得提一句？** 因为这套流程是从 OpenMontage 的一次真实实战里长出来的。当时用它做一条竖版短视频，遇到了这些情况：

| 当时的情况 | 这个 skill 的处理 |
|---|---|
| OpenMontage 走 **Remotion 逐帧渲染**，一条 55 秒成片要 **18.4 分钟** | 换成 **FFmpeg 单遍**，0.8 分钟，**快 22–25 倍** |
| OpenMontage 的 `clip-factory` pipeline **需要自己转写**（本地 118 秒素材花 15.6 分钟） | **不转写**——直接吃你已有的逐词时间码 |
| OpenMontage 的 `transcriber` 用 faster-whisper，且依赖 `ffprobe` | 不绑定任何转写引擎；`ffprobe` 缺失时见 [`references/SETUP.md`](references/SETUP.md) |
| 字幕由 Remotion 的 caption 组件产出，断句按字数切 | 按**句段 + 词边界**切，见 [`references/TRAPS.md`](references/TRAPS.md) 第 4 条 |

**两者可以配合用**：如果你已经在用 OpenMontage，它的 `transcriber` 工具（走 faster-whisper）产出的逐词时间码**可以直接喂给这个 skill**，然后就跳过后半段的渲染开销。时间码格式见 [`references/TIME-BUDGET.md`](references/TIME-BUDGET.md) 第二节。

反过来说，如果你只是要剪短视频，**用这个 skill 就够了，不必装 OpenMontage**。

---

## 耗时：钱花在哪

这是全套流程里最重要的一节，因为**最贵的从来不是剪辑**。

一台 2 核 / 7.7 GB 内存 / 无独显的机器，处理 118 秒源素材：

| 步骤 | 耗时 | 占比 |
|---|---|---|
| **语音转写** | **15.6 min** | 35% |
| **逐帧渲染花字** | **18.4 min** | 41% |
| 其余全部（分析、切割、字幕、校验、出片） | ~11 min | 24% |
| **合计** | **≈45 min** | 100% |

**两个瓶颈占 76%，而且这两个都能省掉**：

1. **不要在这里转写** → 用你已有的逐词时间码，省 35%
2. **不要用浏览器逐帧渲染** → 用 FFmpeg 单遍，省 41%

优化后：**≈45 min → ≈12 min**。

素材越长差距越大。**30 分钟的源素材**：逐帧路线约 **5.6 小时**，单遍路线约 **15 分钟**。

完整实测数据、分辨率影响、以及三项容易低估的成本（磁盘空间、上下文窗口、反复出片）见 **[`references/TIME-BUDGET.md`](references/TIME-BUDGET.md)**。

---

## 依赖

- **ffmpeg**（需含 libx264 与 `ass` 滤镜）和 **ffprobe**
- **Python 3.10+**，只用标准库
- 可选：`jieba`（`pip install jieba`），提升中文关键词提取质量
- **逐词时间码**——来自你已经在用的转写工具；**这个 skill 不转写**

## 验证它能跑

```bash
python selftest.py
```

用合成素材跑完整流程并断言 **25 项**，其中包括真实发生过并已修复的回归：

- 文本修正跨越合并边界后仍然生效
- 替换前后长度不同时，变色高亮不错位
- 关键词不被换行切断
- 提速后帧率不变成 42
- 静音封面不把响度拉低

**不使用任何真实素材。**

## 目录

```
SKILL.md                 契约：流程、检查项、什么算"做好了"
scripts/build.py         按写好的稿子定剪点；生成字幕与关键词高亮
scripts/render.py        一次出片：切割、变速、响度、烧字幕
scripts/cover.py         封面图生成
scripts/add_cover.py     把封面拼成视频第一帧
references/PACING.md     完播结构、语速、该删什么
references/CAPTIONS.md   字幕样式、关键词变色、三种字幕模式
references/TRAPS.md      15 个难发现且诊断昂贵的坑
references/TIME-BUDGET.md 实测耗时与优化（先看这个）
references/SETUP.md      安装，以及 ffprobe 缺失时怎么办
selftest.py              25 项断言的端到端自测
实测笔记-用AI剪一条竖版短视频.md   一次完整实战的复盘，适合直接读
```

## 协议

MIT——随便用、随便改、随便发。
