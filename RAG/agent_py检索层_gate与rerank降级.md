# AIOps 工作台检索层：rerank 降级 + 置信度 gate

> 场景：AIOps 工作台检索层。记录日期 2026-10-07。
> 落点：`apps/backend/src/super_ai/retrieval/tool.py`，配置 `config/project.json` 的 `retrieval.gateMinScore`。

## 为什么要改

改造前 `KnowledgeRetrievalTool.run()` 有两个缺口：

1. rerank 调用抛异常 → 整次检索失败，返回 `SYSTEM_UNAVAILABLE`。可 RRF 融合结果已经在手里，等于一个可选阶段（精排）拖垮了必选阶段（召回）。
2. 没有任何置信度门槛。库外问题会照样返回 5 条低分片段，模型拿着它编答案——这是幻觉最直接的来源，不是 prompt 能兜住的。

## 改了什么

### 1. rerank 失败降级到 RRF 顺序

```text
try:   rankings = arerank(...)
except: logger.warning(...); rankings = None; rerank_fallback = True

rankings is None -> 直接取 candidates[:top_k]（RRF 融合顺序）
                    rerankRank / rerankScore 保持 None
                    result.rerank_fallback = True
```

语义：召回两条路（向量 + BM25）都是必选，精排是可选。精排挂了退化成"融合排序"，可用性从"整条链不可用"变成"精度下降但能答"。

### 2. 置信度 gate（阈值 `retrieval.gateMinScore`，默认 0.5）

```text
最高精排分 >= 阈值  -> 正常返回
最高精排分 <  阈值  -> results / citations 置空，gate 负载说明原因
阈值 = 0            -> 关闭 gate，恢复旧行为
向量/BM25 模式或降级态 -> 跳过 gate（量纲不同：余弦相似度、RRF 排名分不是精排分）
```

模型拿到的工具负载多了两个字段：

```json
{"gate": {"minScore": 0.5, "topScore": 0.31, "passed": false,
          "reason": "Top rerank score 0.310 < gate 0.50: ..."},
 "rerankFallback": false}
```

模型看到 `passed=false` 就该回答"知识库没找到"，而不是从 5 条无关片段里凑。

### 0.5 这个数的出处

来自另一套知识库 RAG 的标定（scripts/calibrate_crag_threshold.py）：48 道库内题 rerank Top1 min 0.509；15 道库外题 Top1 max 0.634；0.50 放行库内 48/48、误放行库外 1/15。两边都是 text-embedding-v4 + qwen3 rerank，量纲可比，但**必须用本项目的 56 题 sop_testset 复跑确认**，不能当成定论。

## 顺手确认的两条事实（离线复盘落盘数据得出）

数据源：`evals/reports/sop-milvus/ragas_eval-20260929-230211.json`（mode=hybrid_rerank，56 题，每题 top5 精排分）。

1. 精排分区间很窄：0.60 ~ 0.98；相邻落差 p50 0.027、p90 0.115、max 0.257。
   → 断崖截断（abs 0.15 或 rel 0.25）平均只省 1 条（5 → 3.95），收益微弱。
2. 56 题里 gold 只有 1 条，52/56 排第 1，最晚第 3；k=3 起 gold_recall 就是 1.00。
   → 现有测试集测不出断崖的好坏，任何截断都不掉召回。
3. top5 里与 gold 同文档的 chunk 占 0.59（均值），砍掉的多半是同一篇 SOP 的后续步骤。
   → 对 procedure 类问题是负收益。

结论：断崖截断不引入；要控制上下文就锚在 top1 的相对阈值（score >= top1*0.92 时平均 1.80 条、零 gold 丢失），且只在预算不够时开。

## 验证

```bash
cd apps/backend
export TMPDIR=...   # Windows 下 tmp_path 会被拒访问，指到可写目录
PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
```

结果：164 个用例，158 过，6 个失败全部是改造前就存在的环境/配置漂移（`.gitignore` 缺 `config/project.json`、测试期望 `qwen3.7-max` 而本地是 `qwen3.8-flash`、`start-local.sh` 的 `bash -n` 失败），与本改动无关。

新增/改写的用例（tests/test_knowledge_retrieval_tool.py）：

- rerank 失败 → 返回 RRF 顺序、rerankRank/Score 为空、rerank_fallback=True、gate 为 None
- 精排 0.31 < 0.5 → 空结果 + gate.passed=False + 原因含 0.310
- 精排 0.50（边界）→ 通过
- gate=0 → 关闭
- vector 模式（无精排分）→ 跳过 gate
- 负阈值 → ValueError
- LangChain 工具负载含 gate / rerankFallback
- `load_default_gate_min_score` 读配置、缺键/非法值回落默认

## 评测口径的两个附带影响

- `evals/ragas_eval.py` 走生产链路，gate 生效 → 低分题会变成拒答，重跑后的 Context 指标和历史报告不可直接比较。
- `evals/recall_curve.py` 是排名 ablation，显式 `gate_min_score=0`，否则低分题被清空会掩盖召回问题。

## 面试说法

“精排是可选阶段，召回是必选阶段——所以 rerank 挂了降级到 RRF 融合顺序，而不是让整次检索 500。库外问题我用最高精排分做闸门，阈值 0.5 是在 48 道库内 / 15 道库外题上标定出来的，低于阈值直接返回空结果并把原因写进工具负载，让模型明确说没找到，而不是拿低分片段凑答案。阈值只在精排分上生效，余弦相似度和 RRF 排名分不在同一量纲，不能拿来比。”
