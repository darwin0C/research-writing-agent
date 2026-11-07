# 修改报告 · demo-sample

目标期刊：IJHMT · 改写程度：medium

## 1. 修改后段落

```latex
Nanostructured surfaces can enhance boiling heat transfer \cite{kim2015,chen2019}, and surface wettability strongly affects bubble nucleation. In this study, molecular dynamics simulations were performed for argon on copper walls with contact angles of 35$^\circ$ and 110$^\circ$. At a wall temperature of 300 K, the hydrophilic surface reduced the onset time of nucleation from 350 ps to 125 ps (Fig.~\ref{fig:onset}). These results relate surface wettability to nucleation onset, which is relevant to the design of cooling surfaces.
```

## 2. 主要修改

| # | 原文 | 改后 | 原因 |
|---|---|---|---|
| 1 | In recent years, … have attracted increasing attention due to their remarkable ability to significantly enhance | … can enhance | 模板化开头 + 空泛修饰；"significantly" 无统计依据 |
| 2 | It is worth noting that … plays a crucial role in | … strongly affects | 填充语 + 套话；合并为一句 |
| 3 | Our results clearly demonstrate that … reduces … when the wall temperature is 300 K, as shown in Fig. | At a wall temperature of 300 K, … reduced … (Fig.) | 降低论断强度；条件前置；结果用过去时 |
| 4 | This innovative study provides valuable insights … paves the way for … high-performance cooling devices | These results relate … which is relevant to … cooling surfaces | 删除自我评价；不再暗示超出模拟范围的应用结论 |

## 3. 论断强度变化

- “clearly demonstrate” → 直接陈述结果（降级）：只有两个接触角、一个壁温，证据不足以支撑 demonstrate。
- 结尾应用意义从“为高性能冷却器件铺路”降为“与冷却表面设计相关”（降级）。
- 无任何论断被加强。

## 4. 校验

`PASS · 0 errors · 0 warnings`：公式、引用（kim2015、chen2019）、交叉引用、全部数字及单位均保留。

AI 套话密度：76.2 → 0.0（每千词）；强论断词：3 → 0。

## 5. 需要作者确认

- “surface wettability strongly affects bubble nucleation” 原文无引用，建议补一篇文献或改为指向本文结果。
- 350 ps 对应的是疏水表面（110°）吗？原文没有明说，建议写成 “from 350 ps on the hydrophobic surface to 125 ps on the hydrophilic surface”。

> 投稿时请按期刊政策说明 AI 辅助编辑的使用情况。
