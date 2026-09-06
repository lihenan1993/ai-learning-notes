# 运维知识库 RAG 评测报告（Milvus + ragas）

- 生成时间：2026-09-06T20:12:00+08:00
- Milvus：`http://localhost:19530`，collection `knowledge_chunks_eval`，HNSW/COSINE（M=16，efConstruction=200，ef=64）
- 本次写入：203 行（drop 后重建）
- 语料：25 篇 SOP，203 chunks，chunk 策略 markdown-heading / 1200 字符
- 测试集：本次评 56 题（lexical 22 / semantic 19 / procedure 15；dataset 共 56 题）
- 标注方式：LLM 依据原文生成，evidence 必须逐字命中原文（否则丢弃），再过一遍审核模型
- 评测框架：ragas 0.4.3（collections API：Faithfulness / AnswerRelevancy / ContextPrecision / ContextRecall）
- 模型调用：生成侧 qwen 统一关 thinking（`extra_body={"enable_thinking": False}`，默认 thinking 单次 30-90s）；判分走 judge `deepseek-flash`，不参与生成
- 检索：真实 `KnowledgeRetrievalTool`，top_k=5，retrieval_mode 由参数控制；召回池 50 + RRF(k=60)

## 0. 用到的模型

| 角色 | 模型 | 说明 |
| --- | --- | --- |
| 聊天模型（生成答案） | `qwen3.8-flash` | 被测链路；三种召回方式共用同一模型与 prompt |
| 向量模型（embedding） | `text-embedding-v4` | 1024 维，写入 Milvus / query 召回 / Answer Relevancy 相似度 |
| 重排模型（rerank） | `qwen3-vl-rerank` | 仅 `hybrid_rerank` 模式调用，对 RRF 融合后的候选重排 |
| 判分模型（ragas judge） | `deepseek-flash` | `https://api.deepseek.com/v1`，只用于 ragas 四个指标的判定，不参与生成 |
| 测试集生成模型 | `qwen3.8-flash` | 生成问题/答案/证据，再由字符串校验 + 审核模型把关 |

## 1. 三种召回方式 × ragas 四个指标

| 召回方式 | Faithfulness | Answer Relevancy | Context Precision | Context Recall |
| --- | --- | --- | --- | --- |
| 单路 vector | 0.798 | 0.843 | 0.617 | 0.800 |
| 双路 vector+bm25 (RRF) | 0.904 | 0.814 | 0.873 | 0.900 |
| 双路 vector+bm25+rerank | 0.914 | 0.925 | 0.900 | 1.000 |

指标含义：Context Recall / Precision 只看召回片段与参考答案的关系（不需要生成答案）；Faithfulness 看回答是否被召回片段支撑；Answer Relevancy 看回答是否切题。

NaN 说明：单路 vector Faithfulness/Context Recall 报错 1 次；双路 vector+bm25 (RRF) Faithfulness/Context Recall 报错 0 次；双路 vector+bm25+rerank Faithfulness/Context Recall 报错 0 次（NaN 不参与均值）。
判分异常类型：IncompleteOutputException × 1（judge max_tokens=16384）

## 2. 分题型（Context Recall / Faithfulness）

| 题型 | 召回方式 | n | Context Recall | Context Precision | Faithfulness | Answer Relevancy |
| --- | --- | --- | --- | --- | --- | --- |
| lexical | 单路 vector | 4 | 1.000 | 0.604 | 0.917 | 0.950 |
| lexical | 双路 vector+bm25 (RRF) | 4 | 1.000 | 0.875 | 0.910 | 0.890 |
| lexical | 双路 vector+bm25+rerank | 4 | 1.000 | 0.896 | 0.882 | 0.952 |
| semantic | 单路 vector | 3 | 0.333 | 0.500 | 0.359 | 0.644 |
| semantic | 双路 vector+bm25 (RRF) | 3 | 0.667 | 0.826 | 0.913 | 0.643 |
| semantic | 双路 vector+bm25+rerank | 3 | 1.000 | 0.907 | 0.903 | 0.917 |
| procedure | 单路 vector | 3 | 1.000 | 0.750 | 0.933 | 0.899 |
| procedure | 双路 vector+bm25 (RRF) | 3 | 1.000 | 0.917 | 0.889 | 0.884 |
| procedure | 双路 vector+bm25+rerank | 3 | 1.000 | 0.900 | 0.967 | 0.896 |

## 3. 辅助指标（精确命中 + 延迟）

| 召回方式 | Recall@5（gold chunk 命中） | MRR | gold 命中数均值 | 拒答率 | 检索 p50 | 检索 p95 | 生成 p50 | 平均上下文数 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 单路 vector | 0.964 | 0.793 | 0.96 | 3.6% | 296 ms | 1774 ms | 1895 ms | 5.0 |
| 双路 vector+bm25 (RRF) | 0.946 | 0.893 | 0.95 | 5.4% | 383 ms | 1503 ms | 2072 ms | 5.0 |
| 双路 vector+bm25+rerank | 1.000 | 0.958 | 1.00 | 0.0% | 797 ms | 1733 ms | 2042 ms | 5.0 |

检索延迟 = query embedding + Milvus 召回 +（rerank）；生成延迟 = 答案生成。两段分开计时，避免生成耗时掩盖召回层的差异。
注意：延迟在并发 6 下测得，embedding 走公网 API，同一秒内的排队会让绝对值抖动；只看量级与相对差异。

## 4. 失败案例（Context Recall 最低 / Faithfulness 最低）

筛选条件：Context Recall < 0.75 或 Faithfulness < 0.8（NaN 按失败计）。

| 召回方式 | 题型 | Context Recall | Faithfulness | 问题 | 召回 top1 |
| --- | --- | --- | --- | --- | --- |
| 单路 vector | semantic | 0.000 | 0.000 | 如果点击请求中的发布者 ID 缺失或者不是整数格式，系统会如何处理？ | affclick_点击校验码与跳转#8 |
| 单路 vector | semantic | 0.000 | — | 如果流量被判定为智能链接且没有成功换单，系统会如何处理这次事件回调？ | affevent_事件归因校验码#5 |
| 双路 vector+bm25 (RRF) | semantic | 0.000 | 0.778 | 如果流量被判定为智能链接且没有成功换单，系统会如何处理这次事件回调？ | affevent_事件归因校验码#5 |
| 双路 vector+bm25 (RRF) | procedure | 1.000 | 0.667 | 在 smartlink 选单过程中，如果候选列表有多条记录且它们的 ClickCap 合计大于 0… | affclick_点击校验码与跳转#6 |
| 单路 vector | lexical | 1.000 | 0.667 | 在 getOffersByToken 流程中，如果 GetPublisherByToken 步骤失… | affoffer_Offer下发过滤#9 |

## 5. 结论

- 单路 vector：Context Recall 0.800、Context Precision 0.617、Faithfulness 0.798、Answer Relevancy 0.843
- 双路 vector+bm25 (RRF)：Context Recall 0.900、Context Precision 0.873、Faithfulness 0.904、Answer Relevancy 0.814
- 双路 vector+bm25+rerank：Context Recall 1.000、Context Precision 0.900、Faithfulness 0.914、Answer Relevancy 0.925
- 单路 vector → 双路 vector+bm25 (RRF)：Context Recall +0.100，Context Precision +0.256，Faithfulness +0.106，Answer Relevancy -0.029
- 双路 vector+bm25 (RRF) → 双路 vector+bm25+rerank：Context Recall +0.100，Context Precision +0.028，Faithfulness +0.009，Answer Relevancy +0.111
- 参考基准：测试集 56 题，每题为独立问答；同一问题在三种召回方式下使用同一套生成 prompt 与 top_k=5。

## 6. 附录：指标定义

### ragas 四个 LLM 指标

| 指标 | 定义 | ragas 怎么算 | 读法 |
| --- | --- | --- | --- |
| Faithfulness | 答案里的论断有多少能被召回片段支撑 | judge 把答案拆成 statements，逐条判是否被 contexts 蕴含，取 支撑数/论断数 | 0-1，越高越不编。拒答答案没有论断时 ragas 会抛错，本报告记 NaN |
| Answer Relevancy | 答案是否真的在回答这个问题 | 让 judge 用答案反推 N 个问题（strictness=3），算这些问题的 embedding 与原问题的余弦均值 | 0-1，越高越切题。跑题、堆废话、拒答都会掉分 |
| Context Precision | 召回片段里相关的是否排在前面 | 逐条判 context 与参考答案是否相关，再按位置做 rank-aware 加权平均 | 0-1，越高表示有用片段越靠前，衡量排序质量 |
| Context Recall | 参考答案里的信息被召回覆盖了多少 | 把参考答案拆成论断，逐条判能否被 contexts 支撑，取覆盖比例 | 0-1，越高越不漏，衡量召回是否够全 |

四个指标里，Context Precision / Recall 只依赖「问题 + 召回片段 + 参考答案」，与生成的答案无关；Faithfulness / Answer Relevancy 依赖生成出来的答案。

### 辅助列（精确指标，不走 LLM 判定）

| 列 | 定义 |
| --- | --- |
| 题型 | lexical=问题含精确标识符（字段名/错误码/宏名），考 BM25；semantic=口语改写、不含原文标识符，考向量语义；procedure=问顺序/条件/停止时机，考小节定位 |
| Recall@5（gold chunk 命中） | 测试集给每个问题标了 1-2 个 gold chunk；top5 命中比例，全中为 1.0，漏一个掉到 0.5 |
| MRR | 第一个 gold chunk 出现位置 r 的 1/r 的均值，衡量「第一条是不是就对了」 |
| gold 命中数均值 | top5 里平均命中几个 gold chunk，反映结果里有用片段的绝对数量 |
| 拒答率 | 生成答案以「资料不足，无法确定」开头的比例，越高说明检索没给出可用证据 |
| 检索 p50 / p95 | query embedding + Milvus 召回 +（rerank）的延迟分位数，三种方式之间可直接比 |
| 生成 p50 | 答案生成延迟中位数（与检索无关，三种方式应当接近，可用来确认对比公平） |
| 平均上下文数 | 实际喂给生成模型的片段条数（top_k=5，检索返回不足 5 条时会更少） |

## 7. 复现

```bash
cd apps/backend
# 1) 生成测试集（已生成过可跳过）
PYTHONPATH=src .venv/Scripts/python.exe -m evals.build_sop_testset
# 2) 重建 Milvus 评测集 + 跑三种召回方式 + ragas 打分
PYTHONPATH=src .venv/Scripts/python.exe -m evals.ragas_eval
# 复用已有 collection（不重灌数据）
PYTHONPATH=src .venv/Scripts/python.exe -m evals.ragas_eval --no-ingest
```

本次命令行参数：`{'sop_dir': 'SOP', 'dataset': 'agent_py\\apps\\backend\\evals\\datasets\\sop_testset.json', 'out': 'agent_py\\apps\\backend\\evals\\reports\\sop-milvus', 'item_limit': None, 'modes': 'vector,hybrid,hybrid_rerank', 'no_ingest': False, 'skip_ragas': False, 'from_json': 'evals/reports/sop-milvus/ragas_eval-20260906-230211.json', 'rescore_json': None, 'judge_model': 'deepseek-flash', 'judge_base_url': 'https://api.deepseek.com/v1', 'judge_api_key_env': 'DEEPSEEK_API_KEY', 'judge_max_tokens': 16384, 'judge_concurrency': 10, 'quiet': False}`









而且分两组：前两个只看「检索找到的东西对不对」，后两个只看「答案对不对」。剩下的都是不用 LLM、由程序直接算死的数字。

所有分都是 0-1，越高越好。

━━━ 第一组：只看检索，跟生成没关系 ━━━

1. 上下文召回率（Context Recall）
    定义：把标准答案拆成一条条论断，逐条判断「这条论断能不能在召回的片段里找到支撑」，分数 = 有支撑的条数 / 总条数。它完全不看模型生成了什么。
    意义：回答一个问题——「该找的资料，找全了吗」。这是检查「漏召回」的唯一直接指标。它低，说明检索压根没拿到关键片段，后面的答案是硬猜的。
    你的数据：语义题只有 0.333，说明口语化改写的问法漏召回极其严重，这是三种召回方式里差距最大的地方。
2. 上下文精确率（Context Precision）
    定义：对召回回来的每一条片段判断「和标准答案相不相关」，再按位置加权——排在第 1 位的相关片段权重最高，排在最后的权重最低，取加权平均。
    意义：回答——「有用的片段，排前面了吗」。因为 context 有长度预算，塞 5 条进去如果有 4 条是噪声，既浪费 token 又干扰模型。所以「找得到」和「排得前」是两件事，要分开量。
    典型低分场景：gold 片段在第 5 位、前 4 条是别的服务的相似章节。

━━━ 第二组：只看生成出来的答案 ━━━

1. 忠实度（Faithfulness）
    定义：judge 把答案拆成一条条论断，逐条判断「这条能不能被召回的上下文支撑」，分数 = 有支撑的论断数 / 论断总数。它不跟标准答案比，只问「你说的话有没有出处」。
    意义：专门治幻觉。1.0 表示句句有出处、没自己补知识。低分 = 模型拿常识填空或者张冠李戴。
    坑：模型拒答（"资料不足"）时答案里没有论断，ragas 会直接抛错，所以报告里记 NaN，NaN 不参与均值。
2. 答案相关性（Answer Relevancy）
    定义：反过来让 judge 拿答案去「反推」3 个问题，把这 3 个问题和原始问题都做 embedding，算余弦相似度的均值。同样不跟标准答案比。
    意义：专门治跑题和堆废话。答非所问、说了半天没落点、过度拒答，都会掉分。
    注意：它不等于「正确」。编一个切题但错误的答案，这个分照样很高——所以它必须和忠实度配对读，两个都高才算答案又准又不编。

一句话串起来：
 召回率问「资料找全没」，精确率问「好资料排前面没」，忠实度问「答案有没有超出资料」，相关性问「有没有答在点上」。

━━━ 不用 LLM 的 3 个硬指标 ━━━

1. 第 5 位命中率（Recall@5）
    定义：测试集里每道题人工/LLM 标了 1-2 个「标准出处片段」（gold chunk），看它们在 top5 结果里命中了几个。全中记 1.0，只命中一半记 0.5。
    意义：确定性指标，不依赖 judge 的判断，所以 judge 抖动时它是兜底证据。是「检索到底对不对」最硬的事实。
2. 平均倒数排名（MRR，Mean Reciprocal Rank）
    定义：第一个正确片段出现在第 r 位，就记 1/r；全部题取平均。排第 1 位得 1.0，排第 3 位得 0.33。
    意义：比命中率更关注位置。因为片段是按顺序拼进 prompt 的，前几条决定模型先看什么。0.793 → 0.958 就是「第一名基本稳了」的意思。
3. 拒答率
    定义：答案以「资料不足，无法确定」开头的比例。
    意义：检索没给出可用证据的间接信号。注意拒答不是坏事（比瞎编强），但要把它压低，压低的方法只有把召回做好。



## 8. 面试口述稿（题型设计 + 三档召回 + 口语改写为什么不划算）

> 用途：面试时直接照着说。所有指标都写成「中文名（English）」的形式，先记中文、被追问时补英文。

### 8.1 题型是怎么设计的（三种题型，考三种不同的检索能力）

语料是运维场景 25 篇 SOP（标准作业流程），按 markdown 标题切分（markdown-heading），每段 1200 字符，共 203 个 chunk（文本块）。一共出 56 道题，按「这道题需要检索层具备什么能力」分三类：

- 字面型（lexical）22 题：问题里直接带精确标识符（字段名、常量名、错误码、宏名）。
  例：在 affclick 服务中，常量 validatorCodeWrongGeoTarget 对应的错误码是多少？
  考的是：词面精确匹配（BM25 这类基于词频的检索）。这类题只有「词对上」才能过，向量再强也救不了没有字面重合的常量名。

- 语义型（semantic）19 题：把同一件事换成用户的口语说法，**不含原文里的任何标识符**。
  例：如果点击请求中的发布者 ID 缺失或者不是整数格式，系统会如何处理？（原文里写的是 pid / PubId）
  考的是：语义检索（dense retrieval，稠密向量检索）能不能跨过「用户词汇」和「文档词汇」的鸿沟。

- 流程型（procedure）15 题：问题本身用词正常，但答案是「按什么顺序判、满足什么条件停、最后取哪个」。
  例：在 smartlink 选单过程中，如果候选列表有多条记录且它们的 ClickCap（点击上限）合计大于 0，但每条都小于合计值，系统最终会选择哪一条单子？
  考的是：小节定位能力——能不能把讲同一套流程的相邻小节区分开，而不是召回一堆同主题的邻近段落。

三类分开统计，是因为聚合分数会互相掩盖：本次字面型和流程型的上下文召回率（Context Recall）在三种召回方式下都接近 1.0，全部差距都来自语义型——语义型从 0.333 → 0.667 → 1.000。如果只看总分，会得出「加 BM25 只涨 0.1，不值」的错误结论。

### 8.2 三档召回方式的指标变化（背这一段）

同一批题、同一套生成 prompt、同样取前 5 条（top_k=5）：

    单路向量（vector） → 加 BM25 双路融合（RRF） → 再加重排（rerank）
    
    上下文召回率（Context Recall）    0.80 → 0.90 → 1.00   漏召回被逐步补上
    上下文精确率（Context Precision） 0.62 → 0.87 → 0.90   排序质量靠融合 + 重排提
    忠实度（Faithfulness）            0.80 → 0.90 → 0.91   资料齐了，模型就不用编
    检索延迟中位数（retrieval p50）   296 → 383 → 797 ms   代价：重排让检索段翻 2.7 倍

一句话收尾：纯向量检索的问题不是「排得不准」，是「根本没召回到」，所以先加 BM25（词面检索）补召回，再用重排（rerank）修排序，代价是检索延迟翻 2.7 倍。

补充两个不用大模型判分、纯程序算的硬指标（被追问「大模型判分抖不抖」时用）：

- 前 5 位命中率（Recall@5）：0.964 → 0.946 → 1.000
- 平均倒数排名（MRR, Mean Reciprocal Rank）：0.793 → 0.893 → 0.958

注意中间那一档命中率略降：融合（RRF, Reciprocal Rank Fusion，倒数排名融合）只看排名不看分数，BM25 会把长段落里的噪声顶上来挤掉正确片段——这正是后面必须接重排做末端纠偏的原因，也是可以主动讲出来的「我知道我这套方案哪里不完美」。

### 8.3 根因：口语问法命中不了文档里的名词

语义型题的失败，不是向量「算错了」，是用户说法和文档写法是两套词：
- 用户问「发布者 ID」，文档那张表里写的是 `pid` / `PubId`；
- 用户问「每日总点击上限」，文档里写的是 `Total.Size`、`Used >= Size`。

这种情况下，向量模型拿到的是「发布者 ID 缺失怎么处理」这句话的整体语义，而标准出处那个 chunk 只有一行表格，它的向量主要承载的是「校验码 / 入口」这类上下文语感——两者在向量空间里并不靠近。真正缺的是词面通道：只有 BM25 命中 `pid` 那类标识符，才能把它捞出来。这也是为什么加 BM25 之后，语义型的上下文召回率从 0.333 直接到 0.667。

### 8.4 为什么没有用「口语改写（query rewriting / HyDE）」来解决

我离线测过，结论是：收益不明显，且容易引入新错。

- 收益是口语型专属：改写（HyDE, Hypothetical Document Embeddings，先生成假答案再检索）能把一条口语 query 从第 7 名拉到第 1 名，但也会把另一条从第 4 名踢到第 21 名——它把「查一下特别慢」写成了通用的「慢查询索引优化」，直接漂到 MySQL 那套文档去了。这是**风格漂移（domain drift）**：改写模型用自己的语言习惯重写，脱离了本项目的术语体系。
- 融合救不回来：原句 + 改写结果的融合（RRF）平均倒数排名 0.704，反而低于原句单独用（0.710）和改写单独用（0.782）。融合的定位是「省等待、做兜底」，不是「提质量」。
- 没法做熔断（用相似度阈值中途拦截）：实测好改写（把第 7 名拉到第 1 那名）与原始问题的相似度是 0.572，坏改写（第 4 名踢到第 21）是 0.563——差 0.009，阈值根本设不出来。原因是结构性的：改写的设计目标本来就是让 query 向量离开原句方向。
- 延迟顶不住：HyDE 生成 100 字假答案本机实测中位 2.95 秒，串在链路上必然超出 2 秒预算。

一句话：口语改写的收益不稳定，失败模式（领域漂移）又很难自动识别，所以在我的语料规模下不划算。

### 8.5 可以尝试的替代方案：把别名知识放在文档侧，而不是查询侧

关键判断是成本量级：查询侧改写是 O(请求数)，每个请求都要一次大模型调用；文档侧标注是 O(chunk 数)，离线跑一次、永久生效。我的 SOP 库才 203 个 chunk、更新很慢，所以明显应该做在文档侧。

具体做法：索引时给每个 chunk 加一个「上下文头 / 别名附注」，也就是上下文检索（contextual retrieval）的做法。

以那张出问题的表为例，索引文本里补一句：

    「本表列出 pid（发布者 ID）、PubId 等请求参数缺失或格式非法时的处理：进校验链前直接返回 HTTP 400，不产生校验码。」

补完之后，用户无论说「发布者 ID」「pid」还是「PubId」，稠密向量检索（dense retrieval）和词面检索（BM25）都能命中这个 chunk——一个离线动作同时修好了两条召回通道，而且不引入任何在线延迟和漂移风险。

别名对照表本身不靠模型「猜」，来源按可靠性排序：

1. 语料内同现抽取（最硬）：SOP 那张表里「中文说明 + 英文标识符」就在同一行同一格，正则 + 同行配对就能挖出「发布者 ID → pid / PubId」的映射，确定性、可复查。
2. 代码与表结构抽取：Go struct 的字段 PubId + json tag pid + 中文注释「发布者ID」，本身就是完整三元组；数据库列注释同理。这是做过业务代码的人才有的语料，通用方案拿不到。
3. 大模型猜 + 回查验证（最后手段）：禁止未经校验就把模型猜的别名塞进查询——猜成 publisher_id / publisherId 就会把召回带偏，必须回到语料里确认这个标识符真实存在才允许使用。

### 8.6 追问预案

- 「就给 10 道题判分，能说明什么？」→ 承认样本小：大模型判分（judge）成本所限只抽了 10 题（字面 4 / 语义 3 / 流程 3），56 题全量只跑了检索与生成。支撑结论更硬的是全量的前 5 位命中率（0.964 → 0.946 → 1.000）和平均倒数排名（0.793 → 0.893 → 0.958）。
- 「重排只把精确率提了 0.028，值吗？」→ 值的是召回率（0.90 → 1.00）和平均倒数排名（0.893 → 0.958），也就是「不再漏 chunk」和「第一条就对了」；精确率已接近天花板，涨不动正常。
- 「精确率高是不是就等于答对了？」→ 不是。有一道语义题精确率 1.0、召回率 0.0：召回片段确实相关（讲 smartlink 判定过程），但缺了 -6 那一行，模型答成了 -13。相关 ≠ 覆盖所需信息，所以精确率和召回率必须成对读。

## 9. 候选池 50 → 31 的实测依据（recall@k 曲线）

> 背景：一开始候选池是拍出来的固定值 50（两路通道各取 50、RRF 融合后保留 50 交重排）。对话中提出疑问——整个库只有 203 个 chunk，每路取 50 是不是太多。本节是用曲线量出来的答案，以及据此改掉生产代码的依据。

### 9.1 方法

- 脚本：`evals/recall_curve.py`（只跑检索，不生成答案；因此没有大模型判分成本，56 题全量跑完约 1 分钟）
- 做法：对每题分别取三种召回方式的**完整候选排序**（不是只取前 5），记录每个 gold chunk（标准出处片段）在排序里的名次，再算：
  - 召回率（recall@k）：top-k 里覆盖了多少 gold，全中为 1.0
  - 命中率（hit@k）：top-k 里是否至少有一个 gold
  - 平均倒数排名（MRR@k）：第一个 gold 的名次的倒数
- 语料与题集不变：25 篇 SOP / 203 chunks；56 题（字面 22 / 语义 19 / 流程 15）

### 9.2 结果：recall@k 曲线（候选池 = 50 时测）

| 召回方式 | recall@5 | recall@10 | recall@20 | recall@30 | recall@50 |
| --- | --- | --- | --- | --- | --- |
| 单路 vector | 0.964 | 0.982 | 0.982 | 1.000 | 1.000 |
| 双路 vector+bm25 | 0.946 | 0.964 | 0.964 | 1.000 | 1.000 |
| 双路+rerank | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

第一个 gold 落在第几名的分布（56 题）：

| 召回方式 | 第 1 名 | 2-5 名 | 6-10 名 | 11-30 名 | 31-50 名 | 最差名次 |
| --- | --- | --- | --- | --- | --- | --- |
| 单路 vector | 38 | 16 | 1 | 1 | 0 | 26 |
| 双路 vector+bm25 | 48 | 5 | 1 | 2 | 0 | 25 |
| 双路+rerank | 52 | 4 | 0 | 0 | 0 | 3 |

### 9.3 结论

- **第 31-50 名区间一个 gold 都没有**：全库 203 个 chunk、56 道题，最晚命中的 gold 出现在第 26 名（单路）和第 25 名（双路）。也就是说固定池 50 里，最后 20 条候选是纯噪声，只花重排的钱。
- **k=10 → k=20 零增益**（单路 0.982 → 0.982，双路 0.964 → 0.964），到 k=30 才补上最后那一题。拐点在 30，不是 20，也不是 50。
- BM25 通道平均只填到 36.2 条（不是 50）：库太小 + 分词过滤，凑不满。「每路 50」这个设定里，BM25 那路本来就有近三成是空的。

### 9.4 生产改动：池大小由语料规模决定

按比例 + 上下限计算，而不是写死：

    候选池 = clamp(0.15 × N, 20, 100)      # N 为该知识库（租户内、指定 kb 范围内）的 chunk 数

- N = 203 → ceil(30.45) = 31，正落在实测拐点上；N ≥ 667 时封顶 100；N ≤ 134 时兜底 20。
- 代码位置：
  - `src/super_ai/retrieval/tool.py`：`recall_pool_size()` + `KnowledgeRetrievalTool._recall_pool()`（按租户 + 知识库缓存 60 秒，避免每次请求都 count）
  - `src/super_ai/vector_store/milvus.py`：`MilvusVectorStore.count_chunks()`（用 `count(*)` + 同一套租户/kb 过滤表达式）
  - 向量通道、BM25 通道、RRF 融合上限统一用这个池大小；`top_k=5` 不变
  - 向量库若不支持 count（测试替身、其他实现），自动回退到 50，不影响可用性（计数失败绝不阻断检索）

### 9.5 改前改后对照（同一批 56 题，只跑检索）

| 候选池 | 单路 recall@5 | 单路 recall@30 | 双路 recall@20 | 双路+rerank recall@5 | 双路+rerank 最差名次 |
| --- | --- | --- | --- | --- | --- |
| 50（改前） | 0.964 | 1.000 | 0.964 | 1.000 | 3 |
| 31（改后） | 0.964 | 1.000 | 1.000 | 1.000 | 3 |

- 零损失：重排后的召回率仍是 1.000，最差名次仍是第 3。
- 双路 recall@20 从 0.964 涨到 1.000：池从 50 缩到 31 后，向量通道尾部那些低分片段不再进入 RRF，融合排序反而更干净——这是「池子大 ≠ 召回好」的一个直接证据。
- 延迟：两轮 p50 受并发与冷启动抖动（同一脚本先后跑出 2262ms 与 1505ms），**不足以用来量化收益**，只能说重排输入条数从 50 降到 31（-38%）。要报数字需要单独做一次预热后的同并发压测。

### 9.6 面试怎么讲这一节

- 我原来的候选池是拍出来的 50。发现库只有 203 个 chunk 之后，我写了一个只跑检索、不生成答案的脚本，把 56 题 gold chunk 的名次全部打出来，画成 recall@k 曲线。
- 曲线告诉我：第 31-50 名里一个 gold 都没有，k=10 到 k=20 完全没增益，拐点在 30。所以我把池改成 clamp(0.15 × N, 20, 100)，这个库上是 31，重排输入少 38%，召回声零损失（1.000 和 1.000）。
- 顺带发现一个反直觉的点：池子从 50 收到 31，双路的 recall@20 反而从 0.964 升到 1.000——尾部噪声进 RRF 会稀释排名。
- 这套阈值不是常数，是随语料规模变的比例，库扩了要重跑曲线（脚本就是 `evals/recall_curve.py`）。

### 9.7 复现

```bash
cd apps/backend
# 只跑检索，输出 recall@k / hit@k / MRR@k 曲线（Milvus 隧道需已开启）
PYTHONPATH=src .venv/Scripts/python.exe -m evals.recall_curve
```

产物：
- `evals/reports/sop-milvus/recall_curve-20260906-000053.json`（池 = 50，改前）
- `evals/reports/sop-milvus/recall_curve-20260906-001135.json`（池 = 31，改后）
