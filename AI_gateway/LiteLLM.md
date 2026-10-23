---
title: LiteLLM 大模型网关笔记
last_modified: 2026-10-23 22:17
source: https://docs.litellm.ai/docs/
tags:
  - AI Gateway
  - LiteLLM
  - 大模型网关
---

# LiteLLM 大模型网关

## 1. LiteLLM 是什么

LiteLLM 是一个面向大模型应用的统一调用层和网关（Gateway）。它把 OpenAI、Anthropic、Gemini、Azure、Bedrock、Vertex AI、DeepSeek、通义等不同供应商的调用方式，统一为类似 OpenAI API 的接口。

LiteLLM 有两种主要形态：

- **Python SDK**：在应用代码中直接调用不同模型。
- **LiteLLM Proxy**：独立运行一个网关服务，业务系统通过统一的 OpenAI 兼容地址访问模型。

作为网关时，典型调用链为：

`	ext
业务应用 / Agent / LangChain
          |
          v
LiteLLM Proxy
  |       |       |
OpenAI  Claude  DeepSeek / 本地模型
`

核心价值是把“模型供应商差异”从业务代码中抽离出来，同时集中处理路由、密钥、额度、重试、成本、日志和安全策略。

## 2. 主要功能与侧重

LiteLLM 的重点不是简单的 API 转发，而是一个面向生产环境的 **LLM 流量治理层**：

| 功能 | 说明 |
|---|---|
| 统一接口 | 使用 OpenAI 兼容接口调用多个模型供应商 |
| 模型适配 | 统一处理不同供应商的请求、响应、流式输出和参数差异 |
| MCP Gateway | 统一接入 MCP Server，管理工具、资源和提示词的访问及授权 |
| Agent Gateway | 注册和代理 Agent，集中管理调用、授权、日志和成本 |
| 部署过滤 | 按模型组、权限、标签、地域、健康状态和限额等条件筛选候选上游，具体取决于配置 |
| 负载均衡与路由 | 在候选部署中按随机/权重、用量、延迟或成本等策略选择上游；可设置部署优先级 |
| 故障切换 | 上游失败、限流或超时时自动重试、Fallback 或切换 Key |
| 虚拟 Key | 给用户、团队或应用发放网关侧 Key，不暴露上游密钥 |
| 额度管理 | 用户、团队、Key 级预算、速率、模型权限和消费限制 |
| 成本统计 | 记录 Token、请求量、模型价格和消费金额 |
| 日志追踪 | 记录请求、响应、错误、延迟、Token 和调用归属 |
| 可观测性 | 对接 Prometheus、Langfuse、Helicone、OpenTelemetry 等 |
| 安全治理 | API 鉴权、模型访问控制、内容过滤、Guardrails、PII 处理 |
| 缓存 | 对重复请求做缓存，减少延迟和模型成本 |
| 管理后台 | 管理模型、Key、用户、团队、预算、日志和路由 |
| 扩展能力 | 支持自定义回调、插件、路由逻辑和多种部署方式 |

LiteLLM 的侧重点可以概括为：

> **统一模型、MCP 工具和 Agent 接入 + 生产级路由容错 + 访问、使用量和成本治理。**

它比 One API/New API 更偏“企业模型基础设施”；New API 更偏用户、渠道、额度和 API 分发运营。

## 3. 模型源过滤策略

这里的“源”通常指上游模型来源或部署实例，例如多个 OpenAI Key、多个 Azure 部署、多个 DeepSeek 渠道，或同一模型在不同区域的副本。

### 3.1 过滤的基本思路

LiteLLM 会先根据请求中的模型名、模型组和部署配置，找出候选部署；然后过滤掉不满足条件的源，再由路由器选择最终目标。

常见过滤条件包括：

1. **模型名匹配**：请求 gpt-4o，只选择声明支持该模型的部署。
2. **模型组匹配**：把多个部署归入同一个逻辑模型组，业务只依赖逻辑名称。
3. **供应商过滤**：只允许使用某类 Provider，例如 Azure、OpenAI、Bedrock 或本地 OpenAI-compatible 服务。
4. **Key / 部署状态过滤**：排除禁用、失效、冷却中或健康检查失败的部署。
5. **能力过滤**：根据是否支持流式输出、Function Calling、JSON、Embedding、Vision 等能力筛选。
6. **地域和合规过滤**：按区域、数据驻留、网络可达性或租户策略筛选。
7. **预算和权限过滤**：根据用户、团队或 Key 的模型权限及剩余额度过滤。
8. **健康状态过滤**：排除最近持续报错、超时或触发限流的上游。
9. **标签过滤**：可按环境、业务线、GPU 类型、区域等标签做路由约束。

### 3.2 过滤与路由的区别

- **过滤**回答“哪些源可以用”。
- **路由**回答“在可用源中先用哪个”。

建议先做严格过滤，再做路由；否则可能出现把请求发到“不该使用”的源上。

## 4. 路由策略

LiteLLM Router 的路由策略用于在多个候选部署之间选择目标，并在失败时完成重试或切换。

### 4.1 路由策略与故障处理

以下是 Router 的常见 `routing_strategy` 名称；具体可用项和配置以所用版本的官方文档为准。

| 策略名 | 说明 |
|---|---|
| `simple-shuffle` | 随机选择部署；可结合配置的 RPM/TPM 或权重进行分配 |
| `least-busy` | 优先选择当前负载较低的部署 |
| `usage-based-routing` | 根据部署的 RPM/TPM 使用情况选择部署 |
| `usage-based-routing-v2` | 基于使用量的另一种实现，使用共享状态协调路由 |
| `latency-based-routing` | 根据已观测的部署延迟选择上游 |
| `cost-based-routing` | 根据部署的模型成本选择上游 |

部署优先级（`order`）用于控制主备顺序，不是独立的 `routing_strategy`；模型组用于确定候选部署，也不是负载均衡策略。重试、冷却和 Fallback 属于失败处理：它们可以在调用失败或满足配置条件时重试、暂时排除部署或转向备用模型组，而不是上述选择策略本身。
### 4.2 路由设计建议

生产环境建议采用“优先级 + 权重 + Fallback”的组合：

`	ext
主模型组
  ├── 主渠道：优先级 1，权重 80
  ├── 同供应商备用 Key：优先级 1，权重 20
  └── 备用供应商/备用模型：优先级 2
`

同时要区分：

- **可重试错误**：超时、连接失败、部分 5xx、临时限流。
- **不可重试错误**：参数错误、权限错误、模型不存在、内容策略拒绝。

不要对所有错误盲目重试，否则会放大上游压力和成本。

## 5. 虚拟 Key

### 5.1 是什么

虚拟 Key（Virtual Key）是 LiteLLM 网关生成的业务侧访问令牌。业务应用只持有虚拟 Key，LiteLLM 再使用后台保存的 Provider Key 访问上游模型。

`	ext
业务应用 --虚拟 Key--> LiteLLM Proxy --Provider Key--> 模型供应商
`

### 5.2 为什么需要虚拟 Key

- 不向业务代码暴露 OpenAI、Anthropic 等上游密钥。
- 可按用户、团队、应用或环境分别管理。
- 可以为每个 Key 设置模型权限、预算、速率和过期时间。
- 可追踪某个调用来源的请求量和成本。
- 上游 Key 轮换时，业务侧无需修改配置。
- 可以随时禁用或撤销某个应用的访问权限。

### 5.3 管理维度

建议至少区分：

- 用户 Key：面向个人开发者。
- 团队 Key：面向部门或项目组。
- 应用 Key：面向一个具体服务。
- 环境 Key：开发、测试、生产分别使用。
- 临时 Key：用于实验、演示或短期任务。

虚拟 Key 不是“无限权限代理”。生产环境应配合最小权限原则、过期时间、预算上限和来源审计。

## 6. 额度管理

LiteLLM 可以围绕用户、团队、Key 和模型做预算与使用量管理。

### 6.1 常见额度维度

- 总预算：美元金额或等价成本上限。
- 时间预算：按月、按日或按周期限制。
- Token 预算：输入 Token、输出 Token 或总 Token。
- 请求预算：请求次数、并发数或每分钟请求数。
- 模型权限：只允许调用指定模型或模型组。
- 速率限制：RPM、TPM、并发和队列限制。
- 团队预算：多个应用共享团队额度。
- 单次请求上限：限制上下文长度、最大输出 Token 或单次成本。

### 6.2 额度控制流程

`	ext
请求进入
  -> 校验虚拟 Key
  -> 检查用户/团队/Key 状态
  -> 检查模型权限
  -> 检查预算和速率
  -> 选择上游
  -> 调用模型
  -> 根据实际 Token 和价格记账
  -> 超限时拒绝、降级或切换
`

注意：额度管理依赖正确的模型价格配置。自定义模型、代理渠道或本地模型如果没有配置价格，成本统计可能不准确。

## 7. 日志追踪

LiteLLM 的日志追踪用于回答：

- 谁调用了模型？
- 调用了哪个模型和上游？
- 请求耗时多少？
- 输入输出 Token 是多少？
- 花费了多少钱？
- 是否发生重试、Fallback 或限流？
- 哪个团队、应用或用户产生了成本？
- 哪些请求报错最多？

### 7.1 建议记录的字段

| 类别 | 字段示例 |
|---|---|
| 身份 | user、team、virtual_key、api_key_alias |
| 请求 | request_id、trace_id、model、endpoint |
| 上游 | provider、deployment、region |
| 性能 | start_time、latency、time_to_first_token |
| 用量 | prompt_tokens、completion_tokens、total_tokens |
| 成本 | prompt_cost、completion_cost、total_cost |
| 结果 | status_code、finish_reason、error_type |
| 路由 | retry_count、fallback_used、selected_deployment |
| 业务 | application、environment、project、tenant |

### 7.2 日志注意事项

- 默认不要把完整 Prompt 和完整响应无条件落盘。
- 对手机号、邮箱、身份证、订单号等敏感信息脱敏。
- 日志中不要记录 Provider Key 和虚拟 Key 明文。
- 为每次请求生成可跨服务传递的 request ID/trace ID。
- 对日志设置保留周期、访问权限和归档策略。

## 8. 可观测性

LiteLLM 的可观测性可以分成四层：

### 8.1 流量层

关注：

- QPS、RPM、TPM
- 并发请求数
- 成功率、错误率
- 429、5xx、超时比例
- 不同模型和 Provider 的流量分布

### 8.2 性能层

关注：

- 总延迟
- 首 Token 延迟（TTFT）
- Token 生成速度
- 上游连接时间
- 重试和 Fallback 次数
- 队列等待时间

### 8.3 成本层

关注：

- 每个模型的 Token 和费用
- 每个团队、应用、用户的费用
- 预算消耗率
- 最昂贵的请求
- 低价模型和高价模型的使用比例

### 8.4 质量与业务层

关注：

- 模型响应为空或截断的比例
- 工具调用成功率
- JSON/结构化输出解析失败率
- RAG 命中后的回答质量
- 用户反馈和业务转化

### 8.5 常见集成

LiteLLM 可以通过回调或标准观测协议接入：

- Prometheus：指标和告警。
- Grafana：指标看板。
- Langfuse：LLM Trace、Prompt、成本和评估。
- Helicone：请求日志、成本和调用分析。
- OpenTelemetry：跨服务 Trace。
- Datadog、Sentry 等：企业监控和错误追踪。

建议组合：

`	ext
LiteLLM Proxy
  ├── Prometheus/Grafana：基础指标和告警
  ├── Langfuse：LLM 调用链与质量分析
  └── 结构化日志：审计、排障和离线分析
`

## 9. 其他重要功能

### 9.1 统一模型与参数适配

应用可以使用统一的模型名和 OpenAI 风格客户端，LiteLLM 负责转换供应商差异，包括消息结构、流式响应、工具调用和错误格式。

### 9.2 重试、退避与熔断

对临时错误做有限次数重试，结合指数退避、冷却时间和健康状态，避免故障上游被持续打爆。

### 9.3 缓存

对确定性、可缓存的请求启用缓存，可以降低成本和延迟。需要注意：包含用户私密信息、实时数据或强随机要求的请求不应简单缓存。

### 9.4 Guardrails 与内容治理

可在请求进入模型前或响应返回后进行安全检查，例如敏感信息检测、内容审查、格式校验和输出过滤。Guardrails 应与业务合规要求一起设计，不能只依赖模型本身。

### 9.5 管理后台与数据库

生产环境通常会使用数据库保存用户、团队、Key、预算、调用记录和配置。管理后台需要单独做鉴权、网络隔离、审计和备份。

### 9.6 部署方式

常见部署方式包括：

- 本地开发：Python 命令直接启动。
- Docker Compose：适合单机和测试环境。
- Kubernetes：适合多副本、弹性扩缩和服务治理。
- 反向代理/Ingress：统一 TLS、域名、限流和公网入口。

## 10. LiteLLM MCP Gateway 与 Agent Gateway

> 本节按 [MCP 官方文档](https://docs.litellm.ai/docs/mcp) 和 [Agent Gateway / A2A 官方文档](https://docs.litellm.ai/docs/a2a) 整理。这里的 MCP Gateway、Agent Gateway 是 LiteLLM Proxy 提供的具体产品能力，不只是泛指的架构概念。

### 10.1 MCP Gateway

LiteLLM Proxy 提供 MCP Gateway，为 MCP 工具提供**统一固定入口**，并可按 LiteLLM Key、Team、Organization 控制访问。客户端连接 LiteLLM，而不是分别保存和连接每个 MCP Server；LiteLLM 再代理到已配置的 MCP Server。

```text
MCP Client / Agent
        |
        v
LiteLLM MCP Gateway（统一入口、身份与权限）
   |             |              |
GitHub MCP   内部搜索 MCP   数据库 MCP
```

#### 解决的问题

- 多个 MCP Server 的地址、传输方式和认证方式各不相同，客户端需要逐个配置。
- 不同用户、团队或组织应只能看到获准使用的 MCP Server/工具。
- MCP Server 的凭据需要集中保存和管理，避免散落在客户端配置中。
- 需要通过统一入口查看工具、调用工具，并集中治理调用。
- 某些客户端或流程希望不经 LLM，直接通过 REST API 列出或调用 MCP 工具。

#### LiteLLM MCP Gateway 支持

- MCP 操作：列出工具、调用工具、访问 Prompts 和 Resources。
- 传输方式：Streamable HTTP、SSE；也支持 stdio，但 **stdio 默认关闭**，需在 Proxy 进程环境中显式启用 `LITELLM_ENABLE_MCP_STDIO=true`。
- 统一入口：把已配置的多个 MCP Server 汇聚到 LiteLLM Proxy；工具名按 MCP Server 名称加前缀进行命名空间隔离。
- 直接 REST 调用：提供 `/mcp-rest/tools/list` 和 `/mcp-rest/tools/call`，可用 curl 等直接列出或调用工具，不必先经过 LLM。
- 访问控制：可按 Key、Team、Organization 授权；并有用户侧 MCP 访问控制相关配置。
- 身份认证：支持 OAuth（含发现/动态注册流程及自定义配置）、AWS SigV4，以及 API Key、Bearer、Basic、静态 Header 等认证方式；可配置共享或按用户提供的 Server Variables。
- 配置和管理：可通过管理 UI、配置文件等方式添加 MCP Server；启用数据库存储时可将 MCP 配置持久化。
- 协议协商：在 MCP `initialize` 阶段协商协议版本。

**边界**：MCP Gateway 管理的是 MCP Server 接入、协议代理、认证和访问授权；它不等于任意工具的沙箱，也不自动保证工具后端操作安全。数据库权限、网络隔离、危险操作审批等仍需在 MCP Server 和基础设施层落实。

### 10.2 Agent Gateway（A2A）

LiteLLM 文档中的 Agent Gateway 主要指 **通过 A2A（Agent-to-Agent）协议接入和调用 Agent**。它把已注册的 Agent 放到 LiteLLM 网关统一管理和访问，而不是 Agent 工作流编排器，也不是用来替代 LangGraph 等 Agent Runtime。

```text
应用 / Coding Agent
        |
        v
LiteLLM Agent Gateway
        |
   A2A Agent（LangGraph、Vertex AI、Bedrock AgentCore 等）
        |
   Agent 内部可再调用 LiteLLM 模型或 MCP 工具
```

#### 解决的问题

- 应用需要以统一方式发现和调用不同框架或云平台上的 Agent。
- 需要管理哪些 Key、Team 可以调用哪些已注册 Agent。
- 需要为 Agent 调用提供统一日志、流式调用、负载均衡和成本归属。
- 需要把一次 Agent 执行中的后续 LLM 调用关联到同一条 Trace，并将费用归因到 Agent。
- 需要限制 Agent 的迭代/调用预算，并在必要时停止 Agent 调用。

#### LiteLLM Agent Gateway 支持

- Agent 注册：通过管理 UI、API 或配置文件注册 Agent，并维护 Agent Card、调用 URL、协议版本和认证参数。
- Agent 类型/集成：官方文档列出 A2A、Vertex AI Agent Engine、LangGraph、Azure AI Foundry、Bedrock AgentCore、Pydantic AI 等支持项；具体接入方式因 Agent 类型而异。
- A2A 协议代理：支持 A2A 调用和流式调用，并可配置对客户端提供的 A2A 协议版本（文档列出 0.3 和 1.0）。
- 统一认证和授权：调用者使用 LiteLLM Virtual Key；网关可检查该 Key 及其 Team 是否有权调用指定 Agent。Agent 上游还可配置 API Key、Headers 或平台身份凭据。
- 日志和追踪：Agent 请求可记录到 LiteLLM Logs；日志可显示调用者、Key、Team、延迟和成本。配置允许时还能查看请求/响应内容。
- 负载均衡与 Streaming：官方 Agent Gateway 功能表列出负载均衡和流式支持。
- 成本归因与 Trace 关联：支持 Agent 成本追踪；Agent 将 `X-LiteLLM-Trace-Id`、`X-LiteLLM-Agent-Id` 等上下文 Header 继续传递给 LiteLLM 时，可关联 Agent 执行内的模型调用并归因成本。
- Agent Iteration Budgets：可为 Agent 设置迭代预算，控制 Agent 执行中的迭代消耗。
- Agent Kill Switch：提供 Agent Kill Switch 相关能力，用于停止/阻断特定 Agent 的调用。
- Skills Gateway：官方文档也将 Skills Gateway 列在 Agent Gateway 的高级功能中，用于技能相关网关能力。

**边界**：LiteLLM Agent Gateway 的职责是注册、代理、认证授权、负载均衡、日志/成本追踪及预算等网关治理；Agent 的规划、状态管理、工具选择、工作流和业务执行仍由后端 Agent Runtime 负责。

### 10.3 MCP Gateway 与 Agent Gateway 的区别

| 维度 | MCP Gateway | Agent Gateway（A2A） |
|---|---|---|
| 对接对象 | MCP Servers / MCP 工具 | A2A Agent 或文档支持的 Agent 集成 |
| 主要协议/接口 | MCP；另有直接 REST 工具调用接口 | A2A；部分集成按对应平台方式接入 |
| 解决重点 | 工具和资源的统一接入、认证及按 Key/Team/组织授权 | Agent 的注册、调用、授权、负载均衡、日志和成本管理 |
| LiteLLM 的关键能力 | 工具列表/调用、Prompts、Resources、HTTP/SSE/stdio、OAuth、权限控制 | A2A Agent Card/调用、Streaming、负载均衡、Agent 权限、日志、成本归因、迭代预算、Kill Switch |
| 不负责的部分 | 工具本身的业务逻辑、安全沙箱和数据权限 | Agent 内部的规划、编排、状态和业务逻辑 |

### 10.4 两者如何组合

```text
调用方
  |
  v
LiteLLM Gateway
  ├── MCP Gateway：连接和授权 GitHub、数据库、搜索等 MCP 工具
  ├── Agent Gateway：注册、授权和调用 A2A / 平台 Agent
  └── LLM Gateway：管理模型路由、Virtual Key、额度、成本和观测
                   |
                   +--> OpenAI / Anthropic / Gemini / 本地模型
```

如果 Agent 自身要调用 LLM，应让 Agent 使用 LiteLLM 的模型入口，并按官方建议传递 Trace/Agent 上下文 Header，以便在网关日志中关联调用链和成本。MCP Server 的工具权限、Agent 的业务权限仍应在各自服务端做纵深防护。

## 11. 推荐的最小生产架构

`	ext
业务应用
   |
   | OpenAI 兼容 API + Virtual Key
   v
负载均衡 / Ingress
   |
   v
LiteLLM Proxy 多副本
   |             \
   |              \-- Redis：缓存、限流或短期状态
   \-- PostgreSQL：Key、用户、团队、预算、日志元数据
   |
   +-- 模型路由与 Fallback
   +-- Provider 多 Key
   +-- Prometheus/Grafana
   +-- Langfuse/Helicone
`

上线前至少验证：

1. 主渠道失败时能否自动切换。
2. 虚拟 Key 被撤销后是否立即生效。
3. 预算超限是否阻断或按预期降级。
4. 429、超时和 5xx 是否按错误类型重试。
5. 日志是否脱敏，是否能定位到用户、团队和应用。
6. 模型价格配置是否正确。
7. 管理后台和 Provider Key 是否不暴露在公网。
8. 数据库、配置和密钥是否可备份与恢复。

## 12. 一句话总结

LiteLLM 可以理解为：

> **为多模型应用提供统一 API、智能路由、故障切换、虚拟 Key、额度计费、日志追踪和可观测性的 LLM 网关。**

学习和落地时，优先掌握这条主线：

`	ext
Proxy 部署
  -> 模型组与源过滤
  -> 路由、重试和 Fallback
  -> Virtual Key 与预算
  -> 日志、成本和 Trace
  -> 监控、告警和生产安全
`

## 参考资料

- [LiteLLM 官方文档](https://docs.litellm.ai/docs/)
- [LiteLLM Proxy 文档](https://docs.litellm.ai/docs/proxy/quick_start)
- [LiteLLM Router 文档](https://docs.litellm.ai/docs/completion/router)
- [LiteLLM Virtual Keys 文档](https://docs.litellm.ai/docs/proxy/virtual_keys)
- [LiteLLM Observability 文档](https://docs.litellm.ai/docs/observability/observability)
