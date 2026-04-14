# Kafka 生产者常用参数：Go Sarama

以下仅列出 [IBM/sarama](https://github.com/IBM/sarama) 提供的配置项。Kafka 4.x 是 Broker 版本，客户端默认值由所用 Sarama 版本决定；本文默认值已按 IBM/sarama v1.60.2 的 `NewConfig()` 核对，部署时请锁定依赖版本。

## 1. 时间与批量配置

| Sarama 配置 | 默认值 | 作用与推荐配置 |
|---|---|---|
| `Producer.Flush.Frequency` | `0` | 批量发送的时间触发条件；默认不设置周期等待。可从 `5 * time.Millisecond` 开始平衡延迟和吞吐，它不是消息交付的总超时 |
| `Producer.Flush.Bytes` | `0` | 按累计字节数触发发送的尽力阈值；默认不设置字节阈值。需要批量优化时再结合时间阈值压测调整，不是单条消息大小上限 |
| `Producer.Flush.Messages` | `0` | 按消息数量触发发送的尽力阈值；默认尽快发送。提高该值时建议配合 `Flush.Frequency`，避免低流量下等待凑批 |
| `Producer.Timeout` | `10 * time.Second` | Produce 请求中传给 Broker 的确认等待时间，主要用于 `WaitForAll`（-1）的副本确认；不是网络读取或整个发送生命周期超时。一般保留默认，若增大应为 `Net.ReadTimeout` 留出额外网络余量 |
| `Net.ReadTimeout` | `30 * time.Second` | 网络读取超时，等待 Broker 响应时相关；一般保留默认，调整时为服务端处理和网络延迟留出余量 |
| `Net.WriteTimeout` | `30 * time.Second` | 网络写入超时；一般保留默认，不能用它限制整次重试生命周期 |
| `Net.DialTimeout` | `30 * time.Second` | 建立连接的超时；按网络条件与业务故障发现要求调整 |
| `Producer.Retry.Max` | `3` | 发送失败后的最大重试次数；一般保留默认或按可靠性要求调整，次数越多可能等待越久 |
| `Producer.Retry.Backoff` | `100 * time.Millisecond` | 重试发送前的等待时间；一般保留默认，避免故障时密集重试 |

## 2. 推荐起点

下面以同步 Producer 为例，开启幂等发送，同时补齐其必要配置；时间和批量参数从默认值或小幅调整开始。

```go
config := sarama.NewConfig()
config.Producer.RequiredAcks = sarama.WaitForAll
config.Producer.Idempotent = true
config.Net.MaxOpenRequests = 1
config.Producer.Return.Successes = true
config.Producer.Retry.Max = 3
config.Producer.Retry.Backoff = 100 * time.Millisecond
config.Producer.Timeout = 10 * time.Second
config.Producer.Flush.Frequency = 5 * time.Millisecond
```

示例需导入 `github.com/IBM/sarama` 和 `time`，创建 Producer 前可调用 `config.Validate()` 检查配置。仅设置时间触发条件不保证每条消息固定等待 5 ms，实际发送还受批量条件、负载和网络状态影响。

## 3. 使用边界

- `SendMessage` 会等待发送结果，但不接收 `context.Context`。应用超时停止等待，不代表已经取消客户端内部发送；重试业务操作前要考虑结果未知和重复消息。
- 异步 Producer 在启用 `Return.Successes` 或 `Return.Errors` 时，必须持续读取对应的结果通道，避免阻塞；同步 Producer 会在内部处理这些通道。
- Producer 成功只表示满足所配置的 Broker 确认条件，不表示消费者已完成业务处理。
- 日志保留、分区和副本参数见 [Broker 常用参数](kafka-broker常用参数.md)。

## 4. 可靠性、大小、压缩与路由配置

| Sarama 配置 | v1.60.2 默认值 | 作用与推荐 |
|---|---|---|
| `Producer.RequiredAcks` | `sarama.WaitForLocal`（1） | 默认仅等待 Leader 确认；关键事件推荐 `WaitForAll`（-1），配合 Broker / Topic `min.insync.replicas=2` 和 3 副本 |
| `Producer.Idempotent` | `false` | 关键事件建议开启，减少客户端重试造成的重复；要求 `WaitForAll`、`Retry.Max>=1`、`Net.MaxOpenRequests=1`。不替代业务去重 |
| `Net.MaxOpenRequests` | `5` | 单连接允许的未完成请求数；启用本版本 Sarama 幂等生产者时必须设为 1 |
| `Producer.MaxMessageBytes` | `1048576`（1 MiB） | 客户端消息大小限制；按实际记录编码与开销校验，并与 Broker / Topic 消息限制配合。源码旧注释的 1000000 不是本版实际默认值 |
| `Producer.Compression` | `sarama.CompressionNone` | 默认不压缩；带宽 / 吞吐优先可评估 Snappy、LZ4 或 ZSTD，权衡 CPU 成本 |
| `Producer.CompressionLevel` | `sarama.CompressionLevelDefault` | 使用所选压缩算法的默认级别；不同算法允许值不同 |
| `Producer.Partitioner` | 按 key 哈希（Hash） | 默认带 key 时按 key 哈希，无 key 时随机选择；同 key 顺序依赖分区数和发送处理方式。不是 Java 客户端分区器的完全等价实现 |
| `Producer.Flush.MaxMessages` | `0` | 单个 Broker 请求的消息数量不设此上限；与触发发送的 Messages 阈值不同 |
| `Producer.Return.Successes` | `false` | 默认不返回成功通道结果；同步 Producer 必须设 true |
| `Producer.Return.Errors` | `true` | 异步 Producer 必须持续读取 Errors；同步 Producer 内部处理，保留 true |
| `ChannelBufferSize` | `256` | 通道缓冲条数，不是整体内存字节上限 |
| `ClientID` | `"sarama"` | 建议改为业务 / 实例标识，便于日志、指标和配额识别 |

## 5. 可复制的默认配置代码

以下显式列出本篇全部参数及 Producer 配置中的重试、事务、拦截器字段，方便修改。基于 **IBM/sarama v1.60.2**；除了协议版本设为 Kafka 4.0，其余赋值都是库默认值。TLS / SASL 等连接认证信息按部署单独配置，不使用通用示例值。

`Version` 的库默认值是 `V2_8_0_0`，此处主动改为 `V4_0_0_0` 以使用 Kafka 4.0 协议能力。默认配置不启用幂等性，也不满足同步 Producer 对成功回执的要求，后面的发送示例会明确覆盖这些设置。

```go
package kafkaconfig

import (
	"time"

	"github.com/IBM/sarama"
)

func NewProducerConfig() (*sarama.Config, error) {
	config := sarama.NewConfig()

	// 唯一的场景覆盖：Kafka 4.x；不是 Sarama 原始默认版本。
	config.Version = sarama.V4_0_0_0
	config.ApiVersionsRequest = true
	config.ClientID = "sarama"
	config.ChannelBufferSize = 256

	// 网络操作超时与单连接并发请求数。
	config.Net.DialTimeout = 30 * time.Second
	config.Net.ReadTimeout = 30 * time.Second
	config.Net.WriteTimeout = 30 * time.Second
	config.Net.MaxOpenRequests = 5 // 开启幂等性时必须改为 1。

	// 消息限制与写入确认。
	config.Producer.MaxMessageBytes = 1024 * 1024
	config.Producer.RequiredAcks = sarama.WaitForLocal // 默认只等 Leader。
	config.Producer.Timeout = 10 * time.Second
	config.Producer.Idempotent = false

	// 压缩与分区选择。
	config.Producer.Compression = sarama.CompressionNone
	config.Producer.CompressionLevel = sarama.CompressionLevelDefault
	config.Producer.Partitioner = sarama.NewHashPartitioner

	// 批量发送：0 表示不设置相应阈值 / 周期，默认尽快发送。
	config.Producer.Flush.Bytes = 0
	config.Producer.Flush.Messages = 0
	config.Producer.Flush.Frequency = 0   // 可改为 5 * time.Millisecond。
	config.Producer.Flush.MaxMessages = 0 // 单请求消息数量不设此上限。

	// 普通发送重试。
	config.Producer.Retry.Max = 3
	config.Producer.Retry.Backoff = 100 * time.Millisecond
	config.Producer.Retry.BackoffFunc = nil   // 自定义函数优先于固定 Backoff。
	config.Producer.Retry.MaxBufferLength = 0 // 不限制重试桥接缓冲消息数。
	config.Producer.Retry.MaxBufferBytes = 0  // 不限制重试桥接缓冲字节数。
	// 如配置正值，过小的数量 / 字节上限会分别被提高到 4096 / 32 MiB。

	// 返回通道：同步 Producer 需要把 Successes 改为 true。
	config.Producer.Return.Successes = false
	config.Producer.Return.Errors = true
	config.Producer.Interceptors = nil

	// 事务：ID 为空，默认不开启事务。
	config.Producer.Transaction.ID = ""
	config.Producer.Transaction.Timeout = time.Minute
	config.Producer.Transaction.Retry.Max = 50
	config.Producer.Transaction.Retry.Backoff = 100 * time.Millisecond
	config.Producer.Transaction.Retry.BackoffFunc = nil
	// 开启事务还需启用幂等性、设置合适的稳定事务 ID，
	// 并调用事务开始 / 提交 / 中止 API；只填 ID 不构成完整事务流程。

	if err := config.Validate(); err != nil {
		return nil, err
	}
	return config, nil
}
```

## 6. 同步发送代码示例：启用幂等性

与上面的函数放在同一 package 中，下面的文件导入 `fmt` 和 Sarama。`NewProducerConfig()` 保留默认值，此例显式覆盖关键事件的可靠性配置。`brokers`、`topic` 和消息内容由调用方传入，没有统一默认值。

```go
package kafkaconfig

import (
	"fmt"

	"github.com/IBM/sarama"
)

// SendOne 演示创建、发送和关闭流程。
// 生产服务应长期复用 Producer，不要为每条消息创建连接。
func SendOne(brokers []string, topic, key, value string) (err error) {
	config, err := NewProducerConfig()
	if err != nil {
		return fmt.Errorf("create producer config: %w", err)
	}
	config.Producer.RequiredAcks = sarama.WaitForAll
	config.Producer.Idempotent = true
	config.Net.MaxOpenRequests = 1
	config.Producer.Return.Successes = true
	if err := config.Validate(); err != nil {
		return fmt.Errorf("validate producer config: %w", err)
	}

	producer, err := sarama.NewSyncProducer(brokers, config)
	if err != nil {
		return fmt.Errorf("create producer: %w", err)
	}
	defer func() {
		if closeErr := producer.Close(); closeErr != nil && err == nil {
			err = fmt.Errorf("close producer: %w", closeErr)
		}
	}()

	_, _, err = producer.SendMessage(&sarama.ProducerMessage{
		Topic: topic,
		Key:   sarama.StringEncoder(key),
		Value: sarama.StringEncoder(value),
	})
	if err != nil {
		return fmt.Errorf("send message: %w", err)
	}
	return nil
}
```

顺序调用同步发送通常难以积累较大批次；吞吐优先时可评估批量 `SendMessages` 或异步 Producer。异步模式需要持续处理启用的结果通道并正确关闭；同步模式由库内部消费这些通道。

发送超时或连接中断时，Broker 可能已经写入，应用不能仅凭返回错误判断消息一定未落盘。幂等生产者减少协议重试重复，但应用重新构造发送或跨进程重试仍需业务唯一标识与去重。

## 7. 相关文档与来源

- [Broker 常用参数](kafka-broker常用参数.md)
- [消费者配置与再均衡](kafka-消费者配置与再均衡.md)
- [Sarama v1.60.2 配置与默认值源码](https://github.com/IBM/sarama/blob/v1.60.2/config.go)
- [Sarama 同步 Producer 接口](https://github.com/IBM/sarama/blob/v1.60.2/sync_producer.go)

## 8. 客户端差异与顺序边界

教程的 Java 配置不能直接当作 Sarama 默认值。例如 Kafka 4.0 Java Producer 的批量等待默认改为 5 ms，本文 Sarama `Producer.Flush.Frequency` 仍为 0；Java 的默认幂等行为也不能代替 Sarama 显式开启幂等性。

顺序要求同时取决于 key 路由、分区数、并发请求和重试。未开启幂等性时，多请求并发配合重试可能使后批先成功；本版 Sarama 幂等配置要求 `Net.MaxOpenRequests=1`。Broker 日志有序也不代表消费端无序并发处理后的业务完成顺序相同。

教程索引和已核对的来源见 [笔记导航与参考](kafka-笔记导航与参考.md)。
