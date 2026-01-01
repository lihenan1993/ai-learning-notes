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
