# Agent 开发笔记

LLM 应用与 Agent 工程的笔记仓库：概念、链路原理、实测数据、工程取舍。

重点放在能落地的东西——一条检索链路怎么切分块、向量检索和 BM25 怎么互补、
重排到底有没有收益、Agent 的状态与记忆怎么落库、工具调用怎么约束参数。
每条结论尽量带样本量和复现条件，而不是只写"XX 更好"。

## 记录方式

每篇尽量回答四件事：

1. **结论先行**：三行内说清解决什么问题、代价是什么
2. **原理/流程**：数据从哪来到哪去，形状怎么变
3. **边界与代价**：什么情况下不适用、成本落在哪一段
4. **类比**：用后端工程里的成熟概念对齐（中间件管道、倒排索引、状态机、连接池）

## 主题

| 目录 | 内容 |
| --- | --- |
| `AgenticAI/` | 智能体设计模式、工具使用、反思、多智能体、评估、MCP |
| `LangGraph/` | StateGraph、控制流、checkpoint 持久化、中断与部署、高级特性 |
| `LangChain/` | 模型创建与输出解析 |
| `RAG/` | 分块、混合检索、召回与重排、Query 改写、检索评估、幻觉与安全、Agentic RAG |
| `milvus/` | 向量库概念对照（collection / segment / partition / 索引） |
| `deep_agents/` | deep agents 技术全景 |
| `skill/` | skill / MCP / tool / subagent 的边界 |
| `prompt/` | Prompt 设计与检索类 prompt 拆解 |
| `fastapi/` | 路由、响应模型、中间件与依赖注入 |
| `openspec/` | 规范驱动开发（SDD）与 OpenSpec 实操 |
| `AI_gateway/` | LiteLLM、new-api 网关与模型路由 |
| `Agent/` | Agent 记忆机制 |

## 推荐阅读路径

- **检索链路**：`RAG/RAG_介绍和架构.md` → `RAG_分块` → `RAG_检索器` → `RAG_召回与重排` → `RAG_检索评估`
- **Agent 组织方式**：`AgenticAI/agent_智能体设计模式.md` → `LangGraph/01-LangGraph基础入门.md` → `LangGraph/03-LangGraph持久化与记忆管理.md` → `LangGraph/04-LangGraph中断与工具与部署.md`
- **工程化落地**：`openspec/SDD与OpenSpec.md`、`AI_gateway/LiteLLM.md`

## 实测环境

- 向量库：Milvus（Zilliz Cloud / Milvus Lite 本地）
- Embedding 与重排：`text-embedding-v4`（1024 维稠密）、`qwen3-rerank`
- 生成模型：DeepSeek 与 qwen 系列
- 评测：自建黄金集 + 检索指标（Hit@k / MRR / NDCG@10），样本量不足的结论会直接标注"只够看方向"

## 说明

课程与书籍的原始 PDF、第三方教程源码不随仓库分发（版权归原作者），
仓库只保留自行整理的文字与配图。

## 全部笔记索引

共 55 篇，按学习顺序排列。


### prompt

| 时间 | 笔记 | 内容 |
| --- | --- | --- |
| 2026-05-09 | [`prompt_预训练知识.md`](prompt/prompt_预训练知识.md) | 大模型预训练知识的边界 |
| 2026-05-12 | [`prompt_web_search.md`](prompt/prompt_web_search.md) | web search prompt 设计 |
| 2026-05-15 | [`prompt_deep_research.md`](prompt/prompt_deep_research.md) | deep research prompt 拆解 |
| 2026-05-18 | [`prompt_AI_Prompting_for_Everyone.md`](prompt/prompt_AI_Prompting_for_Everyone.md) | 《AI Prompting for Everyone》要点 |

### fastapi

| 时间 | 笔记 | 内容 |
| --- | --- | --- |
| 2026-05-20 | [`fastapi_介绍与快速开始.md`](fastapi/fastapi_介绍与快速开始.md) | FastAPI 快速开始（对比 Gin 路由与依赖） |
| 2026-05-23 | [`fastapi_路由.md`](fastapi/fastapi_路由.md) | FastAPI 路由与路径参数 |
| 2026-05-26 | [`fastapi_响应类型.md`](fastapi/fastapi_响应类型.md) | 响应模型与状态码 |
| 2026-05-29 | [`fastapi_装饰器.md`](fastapi/fastapi_装饰器.md) | 装饰器与 app 生命周期 |
| 2026-05-31 | [`fastapi_中间件和依赖注入.md`](fastapi/fastapi_中间件和依赖注入.md) | 中间件与依赖注入（类比 Go 中间件） |

### LangChain

| 时间 | 笔记 | 内容 |
| --- | --- | --- |
| 2026-06-03 | [`langchin_模型创建和输出.md`](LangChain/langchin_模型创建和输出.md) | LangChain 1.x 模型创建与输出解析 |

### LangGraph

| 时间 | 笔记 | 内容 |
| --- | --- | --- |
| 2026-06-06 | [`00-环境配置.md`](LangGraph/00-环境配置.md) | LangGraph 环境配置 |
| 2026-06-10 | [`01-LangGraph基础入门.md`](LangGraph/01-LangGraph基础入门.md) | LangGraph 基础入门 — StateGraph 与节点 |
| 2026-06-13 | [`02-LangGraph控制流与节点执行.md`](LangGraph/02-LangGraph控制流与节点执行.md) | 条件边与控制流 |
| 2026-06-17 | [`03-LangGraph持久化与记忆管理.md`](LangGraph/03-LangGraph持久化与记忆管理.md) | checkpoint 持久化与记忆管理 |
| 2026-06-20 | [`04-LangGraph中断与工具与部署.md`](LangGraph/04-LangGraph中断与工具与部署.md) | 中断、工具调用与部署 |
| 2026-06-24 | [`05-LangGraph高级特性.md`](LangGraph/05-LangGraph高级特性.md) | 高级特性 — 子图、流式、并行 |

### milvus

| 时间 | 笔记 | 内容 |
| --- | --- | --- |
| 2026-06-27 | [`Milvus_概念对照MySQL.md`](milvus/Milvus_概念对照MySQL.md) | Milvus 概念对照 MySQL — collection/segment/partition |

### AgenticAI

| 时间 | 笔记 | 内容 |
| --- | --- | --- |
| 2026-07-01 | [`agent_智能体AI.md`](AgenticAI/agent_智能体AI.md) | 什么是智能体（Agentic AI） |
| 2026-07-04 | [`agent_智能体设计模式.md`](AgenticAI/agent_智能体设计模式.md) | 智能体设计模式 |
| 2026-07-07 | [`agent_工具使用.md`](AgenticAI/agent_工具使用.md) | Agent 工具使用与 JSON Schema 参数 |
| 2026-07-10 | [`agent-反思.md`](AgenticAI/agent-反思.md) | 反思模式与外部反馈 |
| 2026-07-13 | [`agent_多智能体协作.md`](AgenticAI/agent_多智能体协作.md) | 多智能体协作 — 线性规划与分工 |
| 2026-07-16 | [`agent_构建高度自主工作流.md`](AgenticAI/agent_构建高度自主工作流.md) | 构建高自主度工作流 |
| 2026-07-20 | [`agent_高效搭建工作流的技巧.md`](AgenticAI/agent_高效搭建工作流的技巧.md) | 高效搭建工作流的技巧 |
| 2026-07-23 | [`agent_eval智能体评估.md`](AgenticAI/agent_eval智能体评估.md) | 智能体评估 — 客观指标与主观量表 |
| 2026-07-26 | [`agent-mcp.md`](AgenticAI/agent-mcp.md) | MCP 协议与客户端/服务端交互 |

### deep_agents

| 时间 | 笔记 | 内容 |
| --- | --- | --- |
| 2026-07-29 | [`deep_agents_介绍.md`](deep_agents/deep_agents_介绍.md) | deep agents 技术全景 |

### skill

| 时间 | 笔记 | 内容 |
| --- | --- | --- |
| 2026-08-01 | [`skill_为什么要用skill.md`](skill/skill_为什么要用skill.md) | 为什么要用 skill |
| 2026-08-04 | [`skill_skill_mcp_tool_subagent.md`](skill/skill_skill_mcp_tool_subagent.md) | skill、MCP、tool、subagent 的区别 |

### RAG

| 时间 | 笔记 | 内容 |
| --- | --- | --- |
| 2026-08-08 | [`RAG_介绍和架构.md`](RAG/RAG_介绍和架构.md) | RAG 整体架构与链路 |
| 2026-08-10 | [`RAG_分块.md`](RAG/RAG_分块.md) | 分块（chunking）策略 |
| 2026-08-14 | [`RAG_KNN和ANN.md`](RAG/RAG_KNN和ANN.md) | KNN 与 ANN 检索 — HNSW / IVF / PQ |
| 2026-08-17 | [`RAG_检索器.md`](RAG/RAG_检索器.md) | 检索器设计 — 稠密 + BM25 混合 |
| 2026-08-20 | [`RAG_重新排名.md`](RAG/RAG_重新排名.md) | 重排（rerank） |
| 2026-08-23 | [`RAG_召回与重排.md`](RAG/RAG_召回与重排.md) | 召回与重排的关系（实测对比） |
| 2026-08-26 | [`召回和重排算法.md`](RAG/召回和重排算法.md) | 召回与重排算法梳理 |
| 2026-08-30 | [`RAG_Query改写.md`](RAG/RAG_Query改写.md) | Query 改写 — HyDE、多查询、RRF |
| 2026-09-03 | [`RAG_查询解析.md`](RAG/RAG_查询解析.md) | 查询解析与元数据过滤 |
| 2026-09-06 | [`RAG_检索评估.md`](RAG/RAG_检索评估.md) | 检索评估指标 — Hit@k、MRR、NDCG |
| 2026-09-09 | [`RAG_幻觉.md`](RAG/RAG_幻觉.md) | RAG 幻觉来源与抑制 |
| 2026-09-13 | [`RAG_安全.md`](RAG/RAG_安全.md) | RAG 安全 — 提示注入与数据越权 |
| 2026-09-16 | [`RAG_量化.md`](RAG/RAG_量化.md) | 向量量化在 RAG 中的取舍 |
| 2026-09-19 | [`RAG_成本延迟与响应质量.md`](RAG/RAG_成本延迟与响应质量.md) | 成本、延迟与响应质量的取舍 |
| 2026-09-23 | [`RAG_生产落地挑战.md`](RAG/RAG_生产落地挑战.md) | RAG 生产落地挑战 |
| 2026-09-27 | [`RAG_可观测系统.md`](RAG/RAG_可观测系统.md) | 可观测与持续评测 |
| 2026-09-30 | [`RAG_代理RAG.md`](RAG/RAG_代理RAG.md) | Agentic RAG — 代理式检索 |
| 2026-10-04 | [`RAG_多模态RAG.md`](RAG/RAG_多模态RAG.md) | 多模态 RAG |
| 2026-10-07 | [`agent_py检索层_gate与rerank降级.md`](RAG/agent_py检索层_gate与rerank降级.md) | agent_py 检索层 gate 阈值与 rerank 降级 |

### openspec

| 时间 | 笔记 | 内容 |
| --- | --- | --- |
| 2026-10-10 | [`课程_规范驱动开发SDD.md`](openspec/课程_规范驱动开发SDD.md) | 规范驱动开发（SDD）理念 |
| 2026-10-13 | [`SDD与OpenSpec.md`](openspec/SDD与OpenSpec.md) | OpenSpec 实操 — proposal / specs / tasks |

### AI_gateway

| 时间 | 笔记 | 内容 |
| --- | --- | --- |
| 2026-10-17 | [`new_api.md`](AI_gateway/new_api.md) | new-api 网关部署与功能 |
| 2026-10-20 | [`new_api_功能面试速记.md`](AI_gateway/new_api_功能面试速记.md) | 整理 new-api 面试速记 |
| 2026-10-23 | [`LiteLLM.md`](AI_gateway/LiteLLM.md) | LiteLLM 网关与模型路由 |
| 2026-10-26 | [`LiteLLM_功能面试速记.md`](AI_gateway/LiteLLM_功能面试速记.md) | 整理 LiteLLM 面试速记 |

### Agent

| 时间 | 笔记 | 内容 |
| --- | --- | --- |
| 2026-10-30 | [`记忆.md`](Agent/记忆.md) | Agent 记忆机制 |
