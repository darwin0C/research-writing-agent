# research-writing-agent

科研论文写作助手。当前进度：M5（路线图全部完成）：整节多 Agent 流水线、分层校验引擎、术语表、期刊配置、埋错基准集、个人风格库，Word、审稿回复、基金申请书（含中文）三类文档，以及不依赖 Claude Code 的独立运行器和浏览器审阅应用。完整方案见 [PLAN.md](PLAN.md)。

## 用法（Claude Code）

在本目录打开 Claude Code（新会话才会加载子 Agent 和 Hook），然后：

```
/academic-writing 润色 paper/results.tex，目标期刊 IJHMT，改写程度 medium
```

## 流程

```
split(代码) → auditor ×1 → rewriter ×N 并行 → 每段校验(代码, Hook 自动触发)
   失败 → 只退回该段重写，最多 3 次，仍失败则保留原文
→ assemble + 整节校验(代码) → claim-checker ×1 → 需要时 reopen 对应段 → report(代码)
```

| 角色 | 定义 | 做什么 |
|---|---|---|
| 编排者 | [SKILL.md](.claude/skills/academic-writing/SKILL.md) | 拆图、派工、集成；自己不改写 |
| auditor | [auditor.md](.claude/agents/auditor.md) | 只读，每段写 issues.md |
| rewriter | [rewriter.md](.claude/agents/rewriter.md) | 每段一个，写 masked_revised.txt + changes.md |
| style-calibrator | [style-calibrator.md](.claude/agents/style-calibrator.md) | 有风格库时，每段一个，向作者本人风格靠拢 |
| claim-checker | [claim-checker.md](.claude/agents/claim-checker.md) | 跨段检查论断与证据，写 claims.md，决定 reopen |
| responder | [responder.md](.claude/agents/responder.md) | 审稿回复：每条意见一个，引用必须能在修改稿中核实 |
| 校验 Hook | [settings.json](.claude/settings.json) | rewriter 一保存就跑校验并把结果反馈给它 |

标题、图表、独立公式和过短段落会被自动“冻结”，原样通过。

## 基于 Academic Humanizer + 可切换模型

**规则层**：[rules/academic-humanizer/](rules/academic-humanizer/) 原样收录了 [Academic Humanizer](https://github.com/AIScientists-Dev/academic-humanizer) v0.3.3 的 `SKILL.md`（MIT 许可，作者 AIScientists-Dev，基于 blader/humanizer），许可证和来源说明一并保留。它的六层规则会附加到每个 Agent 的说明里，作为改写依据。与本项目规则冲突时，以本项目为准：

- 只能指向原文中已有的图、表、文献；
- 缺少证据时插入 `[[EVIDENCE: 需要作者补充什么]]`，不得编造。审阅应用中这类标记显示为“待补证据”，导出时会提醒“尚未补全，不可直接投稿”；
- 基金申请书中允许出现愿景性表述，但必须写出可行性依据。

要加入自己课题组的写作规范，在 `rules/` 下新建一个文件夹并放入 `SKILL.md`，再到“模型设置 → 规则包”中勾选。

**吸收 junbolian/Academic-Humanizer 的检查**：
- 定理、定义等形式化环境原样锁定；
- LaTeX 导言区不改动；
- `[[EVIDENCE]]` 标记内的数字不参与校验；
- 英文破折号计入 AI 套话。

**模型层**（[config/models.toml](config/models.toml)）：

| 类型 | 覆盖 | 依赖 |
|---|---|---|
| `anthropic` | Claude（Opus / Sonnet …） | `pip install anthropic` |
| `openai` | 任何 OpenAI 兼容接口：DeepSeek、通义千问（DashScope）、Kimi、智谱 GLM、OpenAI、硅基流动，以及本地 Ollama / LM Studio | 无（标准库） |

- **按节点分配**：每个 Agent 可以用不同的模型。例如审核和论断检查用较强的模型，改写用较便宜的模型。在审阅应用的“模型设置”里修改，结果保存到 `config/models.local.json`。命令行用 `--profile 名称` 让所有 Agent 统一使用一个模型。
- **密钥**：优先读取档案中指定的环境变量；也可以在网页里保存到 `~/.config/research-writing-agent/keys.json`（权限 600）。密钥永远不会写进项目，也不会在页面上显示。
- **本地模型**：localhost 地址总是直连，不经过系统代理。
- 每个档案都有“保存并测试”按钮，会发一个很小的请求，返回耗时或可读的错误原因。
- 非 Claude 服务的模型名更新较快，配置中标注 `verify` 的条目请以服务商文档为准。
- 校验、重试上限和回退规则与模型无关：无论接入哪个模型，未通过校验的文字都进不了成稿。较小的本地模型可能更常被退回，这是预期行为。

## 审阅应用与独立运行（M5）

**浏览器审阅应用**（只依赖 Python 标准库，仅监听本机 127.0.0.1）：

```bash
python3 -m checker app        # 打开 http://127.0.0.1:8765
```

- 每段显示原文与改写的逐词差异。改动可以单独接受或拒绝，也可以手动编辑或并排对照。公式、引用、交叉引用、斜体符号等以锁定标签显示。
- 每做一次选择或编辑，都会对照原文重新跑全部校验。有错误的版本不能保存，例如只拒绝一半挪动过的句子，导致数字重复出现。
- 导出：LaTeX 输出 `final.tex`，纯文本输出 `final.txt`，Word 输出 `final_tracked.docx`（修订模式）和 `final_clean.docx`。没有手动决定的段落使用流水线的结果。
- 审稿回复：可以逐条编辑回复，保存时重新核实引用和“已修改”的说法，最后生成回复信。

**独立运行器**：不需要 Claude Code，直接调用 Claude API。

```bash
pip install anthropic                     # 只有独立运行器需要
export ANTHROPIC_API_KEY=...              # 或 ant auth login
python3 -m checker run paper.docx --style ijhmt --level medium
python3 -m checker run-review comments.txt --original old.tex --revised new.tex
```

- 和 Claude Code 版走同一条流水线，使用同一套 Agent 说明文件（`.claude/agents/*.md`）和同一套校验、重试上限与回退规则。程序把输入文件交给模型，读回模型返回的文件。
- 默认模型 `claude-opus-5-5`，`--effort high`，可调整。已开启服务端拒答回退（`fallbacks: "default"`）：若某次请求因安全策略被拒，会自动换模型重试一次。重试时只向对话追加内容，不修改历史，以配合提示缓存。
- 结束时打印 API 用量（调用次数、输入/输出 token、缓存命中）。也可以在审阅应用里点“新建运行”，上传文件后在浏览器中启动。

## 三类文档（M4）

| 文档 | 输入 | 输出 |
|---|---|---|
| 论文（LaTeX） | `.tex` | `revised.tex` + 报告 |
| 论文（Word） | `.docx` | **`revised_tracked.docx`（修订模式，可在 Word 里逐条接受/拒绝）** + `revised_clean.docx` |
| 基金申请书 | `.txt`/`.md`/`.docx`/`.tex`，中文或英文 | 同上，用 `--style nsfc` 或 `--style nsf` |
| 审稿回复 | 审稿意见 + 原稿 + 修改稿 | `response_letter.md` + `response_letter.docx`，逐条核实 |

**Word**：只用 Python 标准库读写 .docx。下列内容会锁定为占位符，模型改不了：公式、Zotero/EndNote/Mendeley 引用域、交叉引用、题注编号、斜体/粗体/上下标（如 θ、m²）、超链接、图片、脚注标记、书签和批注锚点。每段有一份 `legend.md` 说明各占位符代表什么。只重写改动过的段落，文件其余部分逐字节保留。表格、文本框、页眉页脚、脚注正文，以及已带修订痕迹的段落不会处理。

**中文**：数字、单位、`从…到…` 方向、`小于`/`约` 等界限、`可能`/`初步` 等限定语、论断强度（证明 > 验证 > 表明 > 说明 > 提示）、适用范围（`在本研究条件下`）、中文套话（[config/ai_phrases_zh.txt](config/ai_phrases_zh.txt)）都会检查。`.txt` 输入不按 LaTeX 处理，`%` 就是百分号。风格校准暂时只支持英文。

**基金申请书**：[nsfc.toml](config/journals/nsfc.toml)、[nsf.toml](config/journals/nsf.toml) 规定了时态（前期结果用过去时，研究计划用将来时）和论断强度，并把“首次”“国际领先”“填补空白”“transformative”等无法核实的评价列为禁用短语。

**审稿回复**（responder Agent，每条意见一个，并行）：

```bash
python3 -m checker review-split comments.txt --original old.tex --revised new.tex --run runs/R [--lang zh]
python3 -m checker review-assemble runs/R
```

每条回复都会经过代码核实：引用的原文必须在修改稿中逐字存在；凡声称“已修改/已补充”，至少要有一处引用是修改稿里新出现的文字，否则不通过。如果实际没有修改，必须写 `Change: none` 并说明原因。连续 3 次不通过的条目，会在回复信中标注“未通过核实，请作者确认”。

## 个人风格库（M3）

让改写稿读起来像你自己写的，而不是“通用学术腔”。

```bash
python3 -m checker style-build ~/papers/my_*.tex --out style_corpus   # 建库；查看 style_corpus/profile.md
python3 -m checker style-distance draft.tex --section results         # 一段文字离你的风格有多远
```

- **风格画像**：按章节类型（引言、方法、结果、结论）统计你的写作习惯，包括句长、we/被动语态、时态、连接词、限定语、名词化程度，以及 “Figure”/“Fig.”、“this work”/“this study”、US/UK 拼写的偏好。
- **检索**：用 BM25 找出你最相似的旧段落作为参照。纯 Python 实现，不需要嵌入模型或 API。
- **风格距离**：0 表示与你的典型写法一致，低于约 1 算接近。报告中会列出“原文 → 改写 → 风格校准”三个版本的距离。
- **style-calibrator**：在内容校验通过后，每段一个 Agent 并行调整文风。调整后的版本要对照原文重新通过全部内容校验，另外还要过“防自我抄袭”检查：不得与旧论文出现连续 10 个相同的词。最多尝试 2 次，失败就保留改写版，不会退回原文。
- **验收（盲评）**：运行 `style-blind` 生成 A/B 盲评表（改写版和校准版随机排序），你打分后运行 `style-unblind` 统计结果。

[examples/author_corpus/](examples/author_corpus/) 是为演示虚构的作者语料，用的时候换成你自己的论文。

## 运行目录 `runs/<时间>-<名称>/`

| 文件 | 内容 |
|---|---|
| `run.json` | 唯一状态源（代码写入） |
| `graph.md` | 任务图：节点、依赖、完成标准 |
| `progress.md` | 每段状态、尝试次数、决策记录、下一步；中断后据此恢复 |
| `checks.md` | 每次校验：节点 \| 检查 \| 结果 \| 证据 |
| `units/uNN/` | 原文、占位符文本、issues.md、改写稿、changes.md、feedback.md |
| `claims.md` | 论断检查结果 |
| `revised.tex` / `report.md` | 合并后的全文 / 给作者的报告 |

示例：[runs/demo-section/report.md](runs/demo-section/report.md)

## 校验工具（可单独使用，无第三方依赖）

```bash
python3 -m checker mask    in.tex --out masked.txt --map map.json
python3 -m checker unmask  masked_revised.txt --map map.json --out revised.tex
python3 -m checker audit   in.tex
python3 -m checker compare original.tex revised.tex     # 有 error 时退出码为 1

# 整节流水线（通常由 Skill 调用）
python3 -m checker split    section.tex --run runs/X --journal "..." --level medium
python3 -m checker status   runs/X
python3 -m checker gate     runs/X u03 [--recheck] # 同一内容重复调用不计次；--recheck 在检查器更新后重验
python3 -m checker reopen   runs/X u03 --reason "..."
python3 -m checker assemble runs/X [--partial]
```

`compare` 检查内容（error 会拒绝改写，warning 交给人复核）：

| 层 | 检查 | 级别 |
|---|---|---|
| L1 | 公式、行内数学、`\cite`（按 key）、`\ref`、`\label`、`\SI{}`、图片、URL 原样保留；改写中新出现的 `%` 注释（未转义的百分号会吞掉后文） | error |
| L2-number / unit | 正文数字（含 one–twenty）与单位不变（`\%`、µm/um、℃/°C 已归一） | error |
| L2-binding | 原来同一句的数字被拆开 | warning |
| L3-direction | “from A to B” 顺序颠倒；动词与数字方向矛盾 | error |
| L3-direction | 含数字的句子 increase↔decrease、higher↔lower 等反义替换 | warning |
| L4-qualifier | 数值上的界限（less than / above / at least / between…and）被删或改 | error |
| L4-qualifier / scope | “approximately” 等近似词被删；“under the investigated conditions” 等适用范围被删 | warning |
| L5-claim | 论断动词强度超过原文最强（suggest < indicate < show < demonstrate < prove） | error |
| L5-claim | 强论断变多、新增强调词（clearly、significantly…）、删掉 may/might/could | warning |
| L6-cite | 引用了 .bib 里没有的 key（需 `--bib`） | error / warning |
| T-term / spelling | 引入术语表中不推荐的说法；US/UK 拼写混用 | warning |

配置：

- [config/glossary.toml](config/glossary.toml)：领域术语（首选说法、缩写、不推荐的变体），按课题组习惯增删。
- [config/journals/](config/journals/)：期刊风格（`ijhmt`、`ate`），包括时态、拼写、额外禁用短语。标注 verify 的字段要对照期刊最新的作者指南核实。
- `split` / `compare` / `audit` 都支持 `--style ijhmt --bib refs.bib --glossary path`。

## 基准测试

```bash
python3 -m eval.run        # 结果写入 eval/results.md；未达标时退出码为 1
```

基准集为 10 段热科学文字，每段配一份忠实改写，在改写中埋入 15 类错误。当前结果：7 类必须拦截的错误拦截率 100%，7 类需要提醒的错误提醒率 100%，忠实改写误拦 0 次。唯一已知盲区是同一句内两个同单位数字互换对象（`rebind_swap`），这一项交给 claim-checker 复核。

**注意**：语料和检查规则都是同一个人写的，结果偏乐观。最有价值的下一步是把自己论文里的段落加进 [eval/corpus.py](eval/corpus.py)。

测试：

```bash
python3 -m unittest discover -s tests -t .
```

## 已知局限

- 同一句内两个同单位数字互换对象，代码查不出，由 claim-checker 复核。
- 方向和适用范围检查基于词表和正则，遇到不常见的表达可能漏检；反义替换只给提醒，不拦截。
- 段落按空行切分；一段里跨段移动内容会被整节校验拦下，但不会自动定位到哪一段。
- 套话词表 `config/ai_phrases.txt` 是通用版，需要按自己领域和期刊增删。
