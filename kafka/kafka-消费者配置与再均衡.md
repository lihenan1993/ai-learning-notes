# Kafka 消费者配置：Go Sarama

本文面向 Kafka 4.x 集群和 **`github.com/IBM/sarama v1.60.2`**，于 2026-04-20 对照该发布版本源码整理。只列 Sarama 可配置的消费者选项；Java Consumer 参数仅作为对应关系提示，不可直接复制到 Go 配置中。旧版 Sarama 不一定具备本文的 `Fetch.MaxBytes` 和协作黏性策略，请先检查 `go.mod`。


重平衡原理、策略配置与迁移、静态成员，以及 Kafka 4.2 共享组已拆至 [重平衡与共享组](kafka-重平衡与共享组.md)。本文件保留消费参数、提交和生命周期使用说明。

## 1. 消费者常用配置

默认值以 v1.60.2 的 `NewConfig()` 实际赋值为准。例如 `Consumer.MaxWaitTime` 的源码注释仍写 250 ms，但实际默认值为 **500 ms**。

| Sarama 配置 | Kafka 对应概念 | Sarama 默认值 | 作用与推荐 |
|---|---|---|---|
| `Consumer.Fetch.Min` | `fetch.min.bytes` | `1` 字节 | Broker 尽量积累到该字节数再响应。低延迟保留默认；吞吐优先可从 16～64 KiB 压测，配合最大等待时间 |
| `Consumer.MaxWaitTime` | `fetch.max.wait.ms` | `500ms` | 数据不足时 Broker 最多等待多久；不是每次拉取固定等待。常用 100～500 ms，低延迟可从 100 ms 开始 |
| `Consumer.Fetch.MaxBytes` | `fetch.max.bytes` | `50 MiB` | 一次 Fetch 请求跨分区的响应预算。默认通常足够，内存紧张可降低；首个大 batch 可能突破预算以保证进度，另受全局响应限制约束 |
| `Consumer.Fetch.Default` | 每分区拉取大小，与 `max.partition.fetch.bytes` 近似 | `1 MiB` | 每分区初始拉取预算，不是固定硬上限；遇到较大消息时客户端可调整。一般保留默认，按实际 batch 大小评估 |
| `Consumer.Fetch.Max` | 每分区拉取增长上限 | `0`，不设此上限 | 限制上述增长，过小可能无法消费大消息。通常保留默认；不是整个请求的 `Fetch.MaxBytes` |
| `Consumer.Group.Session.Timeout` | `session.timeout.ms` | `10s` | 心跳失联后移除成员的检测窗口。一般 10～45 s；静态成员按重启耗时留余量，同时接受更慢故障接管，值需满足 Broker 允许范围 |
| `Consumer.Group.Heartbeat.Interval` | `heartbeat.interval.ms` | `3s` | 后台心跳间隔，必须小于会话超时，通常不超过其三分之一；默认 3 s / 10 s 可作为起点 |
| `Consumer.Group.Rebalance.Timeout` | 再均衡完成预算 | `60s` | 成员退出旧会话、清理并重新入组的预算。默认起步；业务处理和收尾必须及时完成，不能靠无限增大掩盖阻塞 |
| `Net.ReadTimeout` / `Net.WriteTimeout` / `Net.DialTimeout` | 网络读取 / 写入 / 建连超时 | 各 `30s` | 通常保留默认；读取超时应为 Fetch 等待和网络开销留出余量，不能当成整个消费 API 的总超时 |
| `Consumer.Offsets.Initial` | `auto.offset.reset` 的 earliest / latest | `sarama.OffsetNewest` | 没有可用提交位点时的起点。不能漏历史数据的新业务组一般选 `OffsetOldest`；只关心新增数据才选默认值 |
| `Consumer.Group.ResetInvalidOffsets` | 无效位点重置开关 | `true` | 位点失效时允许按 Initial 重置；不能接受自动跳转时设 false，并告警、人工决定恢复位置 |
| `Consumer.Offsets.AutoCommit.Enable` | `enable.auto.commit` | `true` | 后台周期提交应用已标记的进度，不代表收到消息就自动处理成功 |
| `Consumer.Offsets.AutoCommit.Interval` | 自动提交周期 | `1s` | 常用 1～5 s；越短请求越多，越长故障后可能重复处理越多 |
| `Consumer.Group.Rebalance.GroupStrategies` | `partition.assignment.strategy` | 范围分配（Range） | 支持范围分配（Range）、轮询分配（Round Robin）、黏性分配（Sticky）、协作黏性分配（Cooperative Sticky）。通过策略列表配置，具体示例见 [重平衡与共享组](kafka-重平衡与共享组.md)；已有组切换为协作黏性需分阶段迁移 |
| `ClientID` | `client.id` | `"sarama"` | 日志、指标与配额识别名。建议使用业务和实例标签；不是消费者组身份，也不是静态成员 ID |
| `RackID` | `client.rack` | `""` | 声明机架 / 可用区；只有 Broker 配置、副本布局及副本选择策略配套时，才可能就近读取 |
| `Consumer.Group.InstanceId` | `group.instance.id` | `""`，动态成员 | 设置后启用静态成员。同组唯一、重启稳定；适合身份固定的实例，详见 [重平衡与共享组](kafka-重平衡与共享组.md) |
| `Consumer.Return.Errors` | 异步错误反馈 | `false` | 生产建议设 true 并持续读取 `group.Errors()`，监控提交失败、心跳和消费错误 |
| `ChannelBufferSize` | 客户端通道缓冲条数 | `256` | 缓冲不是字节预算，也不是每次拉取记录数。大消息时需估算各分区缓冲占用 |
| `Consumer.MaxProcessingTime` | 向消息通道投递的背压控制 | `100ms` | 应用消费通道太慢时暂停继续拉取；不是处理单条业务的强制超时，也不是心跳存活检测。通常保留默认 |

配置单位要分清：字节字段是整数，时间字段使用 `time.Duration`。Kafka 集群升级到 4.x 不会把 Sarama 默认值自动变成 Java Consumer 默认值。

## 2. 提交与偏移量：标记不等于提交

分区日志的 offset、应用当前处理进度和组已提交进度是不同概念。Kafka 保存的提交位点表示**下一条应读取的位置**。

处理完成 offset=42 的消息后：

```go
session.MarkMessage(msg, "") // 内部标记 msg.Offset + 1
// 若明确操作某分区：
session.MarkOffset("orders", 0, 43, "")
```

这两个操作只更新客户端待提交状态，不立即向 Broker 提交。标记必须发生在业务成功之后。先标记后处理可能跳过失败消息；处理成功后、提交前崩溃则可能重复，所以数据库写入、扣款等仍需业务幂等。

### 自动提交

默认 `AutoCommit.Enable=true`、间隔 1 s，后台提交已经标记的位点。它不会替你判断业务成功；没有调用标记方法，就不能指望正确推进业务进度。更短间隔降低重复窗口，但增加提交请求。

### 手动同步提交当前已标记进度

关闭自动提交后，在批次处理完成时调用：

```go
session.MarkMessage(msg, "")
session.Commit() // 阻塞式提交所有已标记分区进度，不仅是 msg 所在分区
```

`Commit()` 没有 error 返回值，不能把函数返回视为所有位点持久化成功的凭证。启用并读取 `group.Errors()`，结合日志和监控观察提交失败。每条消息同步提交通常开销较大，建议按数量或时间形成受控批次。

### 异步与同步组合

Sarama 没有 Java 风格的带回调 `commitAsync()`。实践中可使用“后台自动提交 + 退出 / 再均衡清理时 `session.Commit()`”降低日常阻塞，同时尽力收尾。不要简单开无界 goroutine 调用 `Commit()` 来模拟异步提交，这会引入生命周期和顺序管理问题。

**v1.60.2 关闭 OffsetManager 时的最终自动 flush 受 AutoCommit.Enable 控制。** 若关闭自动提交，必须自己在有效会话内完成提交，不能假设 `Close()` 总会替你提交最后一批位点。

### 提交特定偏移量与并行处理

`MarkOffset(topic, partition, nextOffset, metadata)` 可以指定分区进度，但 `Commit()` 会提交所有已标记进度，并没有只提交该参数分区的重载。

`MarkOffset` 只向前推进；向后重置使用 `ResetOffset`。同分区并行处理时，只能推进到**连续成功处理的前缀末尾 + 1**。例如 42 尚未完成、43 已完成，不能提交 44，否则 42 在故障恢复时可能被跳过。

## 3. 再均衡回调与正确退出

Sarama 通过 `ConsumerGroupHandler` 生命周期方法组织消费：

| 方法 / 信号 | 时机 | 应做什么 |
|---|---|---|
| `Setup(session)` | 新会话处理开始前 | 初始化本轮状态、记录 Claims；确需改变起点时在此处理 |
| `ConsumeClaim(session, claim)` | 每个分区一个消费 goroutine | 处理消息、成功后标记；不同分区可并发，共享状态需同步 |
| `session.Context().Done()` | 会话结束 / 取消 | 尽快停止本轮处理和派生任务，不继续使用旧 session 标记 |
| `Cleanup(session)` | 本轮所有 ConsumeClaim 退出后 | 收尾并按提交策略提交已完成进度；必须在再均衡预算内完成 |

这些不是 Java 分区 revoked / assigned listener 的一对一替代，不应在 Cleanup 假设所有业务都成功，也不要等待永不结束的后台任务。

应用应循环调用 `group.Consume(ctx, topics, handler)`：一次会话因再均衡返回后，只要应用上下文仍有效，就继续消费；对错误做分类、记录与适度退避。不可把第一次返回当作整个进程永久结束，也不能吞掉错误无延迟重试。

优雅退出顺序：

1. 捕获退出信号，停止接收新的应用任务并取消消费上下文。
2. `ConsumeClaim` 响应取消；为在途业务设置有界退出时间，只标记真正完成的连续进度。
3. 在本轮 Cleanup 中按需要同步提交，等待 Consume 返回。
4. 调用 `group.Close()` 并检查返回错误；开启错误通道时持续读取至其关闭。

正常流程的“取消 → 清理 → 提交 → 关闭”必须落在部署平台的终止宽限期内，也要满足再均衡期限。强杀、网络故障或提交失败下仍可能重复消费。

## 4. 从指定位置读取

| 需求 | Sarama 方式 | 注意 |
|---|---|---|
| 新组读取全部仍保留的数据 | `Consumer.Offsets.Initial = sarama.OffsetOldest` | 已有有效提交位点时不会覆盖它 |
| 新组只看启动后的数据 | `sarama.OffsetNewest` | 可能主动跳过历史积压，不是“从已有提交位置继续”的配置 |
| 当前组指定分区起点 | 在 `Setup` 中对本轮持有分区调用 `session.ResetOffset(topic, partition, target, "")` | 在 claim 开始前执行；在运行中的消息循环里重置不等于立即 seek |
| 按时间寻找位置 | `client.GetOffset(topic, partition, timestampMillis)` 得到 offset 后再应用 | 处理查询错误、无匹配及日志已清理的边界 |
| 独立回放工具 | 底层 `Consumer.ConsumePartition(topic, partition, offset)` | 不参与 ConsumerGroup 的自动分配和提交，需要自行管理分区 |

不要每次 Setup 都无条件重置到同一历史 offset，否则每次再均衡都重新回放。生产组大范围回退通常先停止成员、通过管理工具调整组位点，再启动；只读回放更适合独立 group ID。

## 5. 提交位点保留：Broker 参数

`offsets.retention.minutes` 是 Broker 配置，不是 Sarama Consumer 配置；Kafka 4.x 常见默认是 `10080` 分钟（7 天）。对普通订阅消费者组，组变空后提交位点保留达到期限可被清理；不再订阅某 Topic 等情况也有对应到期规则。不能理解为活跃组每条提交固定 7 天后都被删除。

它决定组恢复时还能否找到提交进度，不决定 Topic 消息的存储期限。位点已清理时按 Initial 选择起点；即使位点仍在，日志已删除也可能出现无效位点并触发重置。

Sarama 的历史 `Consumer.Offsets.Retention` 字段不能当作 Kafka 4.x 上覆盖该 Broker 参数的可靠手段：现代 OffsetCommit 协议版本不携带旧 retention 字段。这里不把它列为推荐消费者配置。离线恢复窗口较长时，应分别规划**提交位点保留**与**Topic 数据保留**。

## 6. 配置起点

以下为新组的配置片段，需导入 `time` 和 `github.com/IBM/sarama`，与前述 Handler 和消费循环配合使用：

```go
config := sarama.NewConfig()
config.Version = sarama.V4_0_0_0 // 使用 Kafka 4.0 协议能力，按目标集群核对
config.ClientID = "order-worker-vm03"
config.Consumer.Return.Errors = true
config.Consumer.Fetch.Min = 1
config.Consumer.MaxWaitTime = 100 * time.Millisecond
config.Consumer.Fetch.MaxBytes = 50 * 1024 * 1024
config.Consumer.Group.Session.Timeout = 30 * time.Second
config.Consumer.Group.Heartbeat.Interval = 3 * time.Second
config.Consumer.Group.Rebalance.Timeout = 60 * time.Second
config.Consumer.Group.Rebalance.GroupStrategies = []sarama.BalanceStrategy{
    sarama.NewBalanceStrategyCooperativeSticky(),
}
config.Consumer.Offsets.Initial = sarama.OffsetOldest
config.Consumer.Offsets.AutoCommit.Enable = true
config.Consumer.Offsets.AutoCommit.Interval = time.Second
// 仅给身份稳定、组内唯一的实例配置；同 ID 不可并发运行。
config.Consumer.Group.InstanceId = "order-worker-vm03-slot0"
```

创建 ConsumerGroup 前检查 `config.Validate()`。此例使用自动提交，仍须业务成功后调用 MarkMessage，并持续读取错误通道。观察消费 lag、处理耗时、提交失败、心跳异常、再均衡次数和耗时后再调整参数。

## 7. 核对来源

- [Sarama v1.60.2 发布记录](https://github.com/IBM/sarama/releases/tag/v1.60.2)
- [配置定义与 NewConfig 默认值](https://github.com/IBM/sarama/blob/v1.60.2/config.go)
- [ConsumerGroup、JoinGroup 与静态成员关闭逻辑](https://github.com/IBM/sarama/blob/v1.60.2/consumer_group.go)
- [会话、标记、提交和 Handler 生命周期](https://github.com/IBM/sarama/blob/v1.60.2/consumer_group_session.go)
- [协作黏性分配及迁移说明](https://github.com/IBM/sarama/blob/v1.60.2/balance_strategy_cooperative_sticky.go)
- [OffsetManager 关闭与提交协议](https://github.com/IBM/sarama/blob/v1.60.2/offset_manager.go)
- [Kafka 4.0 Broker 配置](https://kafka.apache.org/40/configuration/broker-configs/)

## 8. 可复制的默认配置代码（Go / Kafka 4.x / Sarama v1.60.2）

此例显式列出本文全部消费者配置，并补充消费者重试、隔离级别等配置，方便以后直接修改对应行。数值均为 **Sarama v1.60.2 默认值**；唯一主动覆盖的是 `Version`，为了连接 Kafka 4.x 设为 Kafka 4.0 协议版本。Sarama 原始默认是 `V2_8_0_0`，不要将协议版本选择误认为库默认值。

这是消费者配置文件，不是 Sarama 全部功能的配置全集：生产者、Admin、TLS / SASL 等按实际部署另行设置。废弃字段以及 Kafka 4.x 上不适用的旧位点保留覆盖项不列入示例。Broker 地址、group ID、Topic 属于创建和使用消费者时传入的参数，没有统一默认值。

```go
package kafkaconfig

import (
	"time"

	"github.com/IBM/sarama"
)

// NewConsumerConfig 返回用于 Kafka 4.x 的消费者配置。
// 除协议版本外，显式赋值均保留 Sarama v1.60.2 的默认值。
func NewConsumerConfig() (*sarama.Config, error) {
	config := sarama.NewConfig()

	// 协议版本：此行为 Kafka 4.x 场景覆盖值，不是 Sarama 默认值。
	// Sarama v1.60.2 原默认为 sarama.V2_8_0_0。
	config.Version = sarama.V4_0_0_0
	config.ApiVersionsRequest = true // 默认查询 Broker 支持的 API 版本。

	// 客户端身份与缓冲。
	config.ClientID = "sarama"     // 可改成 "order-consumer-vm03"，便于排查。
	config.RackID = ""             // 需要就近读取时填写实际机架 / 可用区。
	config.ChannelBufferSize = 256 // 通道缓冲条数，不是字节数。

	// 网络超时：均为单类网络操作的超时，不是整个消费生命周期超时。
	config.Net.DialTimeout = 30 * time.Second
	config.Net.ReadTimeout = 30 * time.Second
	config.Net.WriteTimeout = 30 * time.Second

	// 拉取大小与等待时间。
	config.Consumer.Fetch.Min = 1                              // 字节；低延迟可保留。
	config.Consumer.Fetch.Default = 1024 * 1024                // 每分区初始预算：1 MiB。
	config.Consumer.Fetch.Max = 0                              // 不设每分区增长上限。
	config.Consumer.Fetch.MaxBytes = 50 * 1024 * 1024          // 跨分区请求预算：50 MiB。
	config.Consumer.MaxWaitTime = 500 * time.Millisecond       // 可改为 100 ms。
	config.Consumer.MaxProcessingTime = 100 * time.Millisecond // 通道背压控制。

	// 分区消费失败重试。
	config.Consumer.Retry.Backoff = 2 * time.Second
	config.Consumer.Retry.BackoffFunc = nil // 设置自定义函数后优先于固定 Backoff。
	config.Consumer.Retry.Max = 0           // 连续分发失败重试不设次数上限。

	// 心跳与成员失联检测。
	config.Consumer.Group.Session.Timeout = 10 * time.Second
	config.Consumer.Group.Heartbeat.Interval = 3 * time.Second

	// 再均衡时间预算与重试。
	config.Consumer.Group.Rebalance.Timeout = 60 * time.Second
	config.Consumer.Group.Rebalance.Retry.Max = 4
	config.Consumer.Group.Rebalance.Retry.Backoff = 2 * time.Second

	// 默认策略：范围分配（Range）。
	config.Consumer.Group.Rebalance.GroupStrategies = []sarama.BalanceStrategy{
		sarama.NewBalanceStrategyRange(),
	}
	// 修改时替换上面的列表元素即可，其他支持的策略为：
	// sarama.NewBalanceStrategyRoundRobin()        // 轮询（Round Robin）。
	// sarama.NewBalanceStrategySticky()            // 黏性（Sticky）。
	// sarama.NewBalanceStrategyCooperativeSticky() // 协作黏性（Cooperative Sticky）。
	// 已有组切换到协作黏性，需要按《重平衡与共享组》的策略迁移说明分两次滚动部署。

	// 静态身份与成员附加信息。
	config.Consumer.Group.InstanceId = "" // 默认动态成员。
	// 固定 VM 槽位可改为 "order-consumer-vm03-slot0"，同组唯一且重启稳定。
	config.Consumer.Group.Member.UserData = nil // 默认不带自定义成员信息。

	// 起点：没有可用提交位点时，默认从最新位置开始。
	config.Consumer.Offsets.Initial = sarama.OffsetNewest
	// 如需读取仍保留的历史消息，改为 sarama.OffsetOldest。
	config.Consumer.Group.ResetInvalidOffsets = true

	// 提交：默认每秒自动提交应用已经标记的位点。
	config.Consumer.Offsets.AutoCommit.Enable = true
	config.Consumer.Offsets.AutoCommit.Interval = time.Second
	config.Consumer.Offsets.Retry.Max = 3 // 关闭阶段失败提交的重试次数。
	// 手动模式改为 false，并在有效会话内主动 session.Commit()。
	// 无论是否自动提交，业务成功后仍须 MarkMessage / MarkOffset。

	// 事务隔离：默认也可能读到未提交 / 已中止事务中的记录。
	config.Consumer.IsolationLevel = sarama.ReadUncommitted
	// 只读取已提交事务数据时改为 sarama.ReadCommitted。
	config.Consumer.Interceptors = nil // 默认无消息拦截器。

	// 错误通道：默认关闭；生产建议改为 true 并持续读取 group.Errors()。
	config.Consumer.Return.Errors = false

	if err := config.Validate(); err != nil {
		return nil, err
	}
	return config, nil
}
```

使用时，调用 `NewConsumerConfig()` 检查返回错误，再将配置传入 `sarama.NewConsumerGroup(brokers, groupID, config)`；处理创建错误后启动消费循环，退出时关闭 ConsumerGroup。默认值是方便对照的基线，不代表适合所有业务，例如默认最新起点可能跳过新组的历史消息，默认动态成员也不会保留稳定实例身份。

## 9. 事务可见性与消费积压排查

`Consumer.IsolationLevel` 默认未提交读（Read Uncommitted）；已提交读（Read Committed）过滤中止事务，且只能读取最后稳定偏移量（Last Stable Offset，LSO）之前的记录。未完成事务可能阻挡后续可见进度，即使日志末尾已有更新数据。

排查积压应区分日志末尾偏移量（LEO）、高水位（HW）、LSO、应用读取进度与组已提交位点。提交位点落后可能来自处理慢、提交间隔或提交失败；已提交读停顿还需检查未结束事务。不能一概通过扩容解决，更不能用跳到最新位点代替故障恢复。

教程中的 Java poll / commit 接口不能替代 Sarama 的会话与标记接口。来源及访问限制见 [笔记导航与参考](kafka-笔记导航与参考.md)。
