---
last_modified: 2026-08-23
---

# RAG 召回与重排（Bi-Encoder / Cross-Encoder）

本文回答一个具体困惑：向量检索已经能算出相似度了，为什么还要重排？为什么必须用两种编码器？

> 与 [RAG_重新排名.md](RAG_重新排名.md) 的分工：那份是概念全景（含 Late Interaction / ColBERT、存储倍数估算、工程注意事项），本文只写三样它没有的——attention 层面的机制细节与术语纠偏、2026-08-23 的实测数据、面试答法。基础定义不在这里重复。

## 0. 一句话结论

**同一个 encoder-only + self-attention 架构的两种用法，差别是两侧 token 能不能在同一个 attention 矩阵里互相看见。**

## 1. 两阶段分工

| 阶段 | 干什么 | 用什么 | 特点 | 类比 |
| --- | --- | --- | --- | --- |
| 召回（Recall） | 从整个知识库快速找出可能相关的 N 个片段（20-50 起步） | Bi-Encoder + ANN 索引 | 快、粗、可能漏 | 海选/粗排 |
| 重排（Rerank） | 对这 N 个片段逐一仔细打分，重新排序取 Top K（3-5） | Cross-Encoder | 慢、准、精挑 | 终面/精排 |

召回的目标是**别漏**，重排的目标是**别错**。这个两段式和广告检索系统里的粗排 → 精排是同一个范式。

## 2. 机制：两种编码器到底差在哪

一句话：**同一个 encoder-only + self-attention 架构的两种用法，差别是两侧 token 能不能在同一个 attention 矩阵里互相看见。**

### 2.1 Bi-Encoder（双编码器）

- query 和 doc 各自独立过模型：`query_vec = encode(query)`、`doc_vec = encode(doc)`，然后 `score = cosine(query_vec, doc_vec)`。
- self-attention 只在各自序列内部发生：query 的所有 Q/K/V 只来自 query，doc 的只来自 doc，**编码阶段两侧零交互**，交互只剩最后一次 cosine——压缩成一个标量。
- 信息损失点：句子被压成一个向量，token 级的对应关系全部丢弃。它只能回答"整体像不像"，不能回答"哪个词对哪个词"。
- 好处：doc 向量可以**离线预计算 + 建 ANN 索引**，在线只算 1 次 query 向量再查索引，成本与库大小无关，百万级文档也能毫秒级。

### 2.2 Cross-Encoder（交叉编码器）

- 把 query 和 doc 拼成一个序列过模型：`[CLS] query [SEP] doc [SEP]`，输出一个相关性分数。
- 拼接后 attention 矩阵是 `(len_q + len_d)²` 的**全连接**：query 的每个 token 能 attend doc 的每个 token，反之亦然。所以它能对齐"无需重启"里的"无需"和"必须重启"里的"必须"这组对立语义。
- 代价：输入依赖 query，**无法预计算**，每个候选都要在线过一遍模型，成本随候选数线性增长。

### 2.3 为什么工程上必须拆两阶段

关键不是准确度，而是"能不能离线预计算"：

| | 能否离线建索引 | 在线成本 | 适合的候选量 |
| --- | --- | --- | --- |
| Bi-Encoder | 能（doc 向量离线算好入库） | 1 次 query 前向 + 查索引，与库大小无关 | 全库（百万级） |
| Cross-Encoder | 不能（输入含 query） | 每个候选一次前向 | 几十条 |

一个能建索引、一个不能，所以只能让快的从百万里筛出几十个（广撒网），让准的在这几十个上精挑（别错）。

### 2.4 术语纠偏（容易被面试官抠）

- Cross-Encoder 里的 cross，**不是** Transformer 里 encoder-decoder 的 cross-attention（那是 decoder 的 Q 对 encoder 的 K/V）。这里指的是"跨越 query 和 doc 两条序列"，实现上仍然是 self-attention，只是序列被拼长了。
- 同一个模型两种身份：BERT/bge 取 `[CLS]` 加分类头输出相关性分数就是 Cross-Encoder；取池化向量算 cosine 就是 Bi-Encoder。bge-reranker 和 bge-m3 就是这么分家的。
- 所以"encoder-only + attention 能判断语义相似"这句话是对的，但要补上：**取决于你让它在哪一步看到对面的 token**。

## 3. 实测数据（2026-08-23，阿里云百炼 API，本机实跑）

query：`配置改了怎么才能不重启就生效？`

阶段一 召回（text-embedding-v4，cosine）：

| 排名 | sim | 文档 |
| --- | --- | --- |
| 1 | 0.8586 | 修改配置后必须重启服务，否则新配置不会生效。（词面最像，语义相反） |
| 2 | 0.7713 | 配置热加载：调用 /admin/reload 即可让新配置生效，无需重启进程。（正解） |
| 3 | 0.7237 | Nginx 执行 reload 即可让新配置生效，无需重启 master 进程。 |

阶段二 重排（qwen3-rerank）：

| 排名 | score | 召回名次 | 文档 |
| --- | --- | --- | --- |
| 1 | 0.9251 | 第 2 名 | 配置热加载：…无需重启进程。（正解被捞回第一） |
| 2 | 0.8564 | 第 3 名 | Nginx reload… |
| 3 | 0.7401 | 第 1 名 | 修改配置后必须重启服务。（从第 1 压到第 3） |

**正解：召回第 2 → 重排第 1；语义相反项：召回第 1 → 重排第 3。**
这就是"向量相似 ≠ 语义相关"的实证：Bi-Encoder 被"配置/重启/生效"几个词的表面重叠骗了。

换 rerank 模型的实测（同一批候选）：

| 模型 | 正解排名 | 语义相反项排名 | 结论 |
| --- | --- | --- | --- |
| qwen3-rerank | 1（0.9251） | 3 | 正确 |
| qwen3.7-text-rerank | 1（0.9923） | 3 | 正确 |
| gte-rerank-v2 | 2（0.5270） | **1**（0.5395） | **排错** |

结论：**rerank 不是接上就有收益，模型选错可能比不接更差。** 另注：gte-rerank 系列官方公告 2026-05-30 下线，实测仍可调，新项目直接用 qwen3-rerank。

延迟实测（qwen3-rerank，候选数 → 耗时）：

| 候选数 | 5 | 10 | 20 | 40 | 100 | 200 |
| --- | --- | --- | --- | --- | --- | --- |
| 耗时 | 169ms | 193ms | 187ms | 218ms | 354ms | 577ms |

约等于"固定 ~150ms + 每条约 2ms"。API 场景下召回 50-100 条再重排完全可接受。**但别把这条推成通用结论**：本地部署的 cross-encoder 是实打实的 N 次前向、纯线性，API 是服务端批处理，几十条内被固定开销盖住了。

反例（说明收益取决于召回质量）：另一个 query 的召回正解就是第 1 名，重排后还是第 1 名——这种 case 不能拿来演示重排的价值，也不能据此判断"重排没用"，要先看 recall@k。

## 4. 边界与代价

1. **重排救不了漏召回**。重排只能在召回集合内排序，召回没捞到就永远没有。召回 top-k 要放够，先看 recall@k 再看重排收益。
2. **收益取决于召回质量**。召回已经 Top1 很准的时候，重排收益很小。别指望重排解决召回本身的问题。
3. **延迟随候选数增长，top_n 就是延迟预算的开关**。送进 LLM 上下文的只放重排后 Top 3-5，不是 Top 20。
4. **第三条路：LLM 做 listwise 重排**。一次把多个候选丢给模型排序（qwen3.7-text-rerank 属这类，支持 instruct 指定"问答检索"或"语义等价"策略）。语义理解更强，但慢、贵、分数不稳定。
5. **"为什么不直接召回 3 个"的标准答案**：向量相似度排名 ≠ 真正相关性排名，Top 3 截断会把真正相关的漏在第 4 名之后；重排就是把这第 4 名重新捞上来。

## 5. Go / 广告类比

| 概念 | 对应物 |
| --- | --- |
| Bi-Encoder 召回 | 离线预计算 + 倒排/ANN 索引查表（O(log N)，与库大小无关） |
| Cross-Encoder 重排 | 无索引，对候选逐条算完整评分函数（O(N)，只敢用在候选集） |
| 两阶段组合 | 广告检索的粗排 → 精排 |
| cosine 一个标量 | 只比"总分"，看不到字段级差异 |
| attention token 对齐 | 精排模型里的交叉特征（query 词 × doc 词） |

## 6. 面试答法（结论 → 原理 → 边界 → 项目例子）

**结论**：召回用双编码压向量快筛，重排用交叉编码逐对精算；前者保覆盖，后者保准确。根因是只有双编码能离线建索引——一个能预计算、一个不能，才必须拆两阶段。

**原理**：Bi-Encoder 把 query 和 doc 各自独立编码成向量，只剩一次 cosine 比较，没有 token 级交互；Cross-Encoder 把两者拼成一个序列过 self-attention，`(len_q+len_d)²` 全连接能做 token 级对齐，所以能分辨"无需重启"和"必须重启"，但输入依赖 query 不能预计算，每个候选都要在线过一遍模型。

**边界**：救不了漏召回（召回 top-k 要放够）；延迟随候选数增长；rerank 模型选型影响巨大（实测老模型会把语义相反的排第一）；召回已很准时收益有限；另有 LLM listwise 重排这条中间路线。

**示例**（示例项目，非线上方案）：知识库文档离线用 text-embedding-v4 建 Milvus 索引，在线召回 20-50 条，再过 qwen3-rerank 取 Top 3-5 送进模型。用"配置改动不重启如何生效"这个 case 验证过：向量召回把"必须重启"的文档排第 1，重排后纠正到第 3、正解升到第 1。这套粗筛 + 精排的两段式，和广告检索里的粗排/精排是同一个思路。

## 7. 可运行脚本与端点

脚本（只用标准库，无需装包，key 自动三级读取）：

- `rerank_demo.py` — 两阶段对比 + 正解/相反项排名变化
- `probe_scaling.py` — rerank 模型质量对比 + 候选数 → 延迟曲线
- `probe_dashscope.py` — 端点与参数形状探测（换模型前先跑它）

运行：`python rerank_demo.py`（脚本未随仓库分发）

端点（实测可用）：

```
embedding  POST https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings
           {"model":"text-embedding-v4","input":[...],"dimensions":1024}

rerank     POST https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank
           {"model":"qwen3-rerank",
            "input":{"query":"...","documents":["...","..."]},
            "parameters":{"top_n":N,"return_documents":false}}
           响应 output.results[] = {"index": 3, "relevance_score": 0.87}
           index 是输入 documents 的下标，用它算"召回第几名 → 重排第几名"
```

坑：

- DASHSCOPE_API_KEY 设在 Windows 用户环境变量里，git-bash 当前会话的 `env` 读不到，脚本里用注册表兜底。网上示例直接 `os.environ` 会报 key 缺失。
- DashScope 原生 embedding 端点用 `dimension`（单数），传 `dimensions` 会被 400 拒；走 OpenAI 兼容端点则用 `dimensions`。省事就统一走兼容端点（`langchain-openai` 也能直接接）。
- 单条 query/document 有 token 上限，超限返回 400 而不是截断。
