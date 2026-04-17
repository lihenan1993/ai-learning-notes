# Kafka Broker 常用参数：作用与推荐配置

本文整理 8 个常用 Broker 参数。默认值以 Apache Kafka 3.x / 4.x 常见配置为参考，发行版和实际部署可能覆盖默认值，应以所用版本文档及集群有效配置为准。推荐值是调优起点，不是所有业务的统一标准。

以下保留策略说明以本地日志、`cleanup.policy=delete` 为前提；仅使用 `compact` 的 Topic 不按普通时间 / 容量保留策略删除历史片段，启用分层存储时还需区分本地与远端保留配置。

## 1. 参数速查

| Broker 参数 | 作用 | 常见默认值 | 推荐配置与适用条件 |
|---|---|---|---|
| `num.partitions` | 创建 Topic 未指定分区数时使用的默认分区数 | `1` | 小型业务可从 `3` 开始；生产 Topic 显式指定，按吞吐与消费并行度压测确定 |
| `default.replication.factor` | 自动创建 Topic，以及创建请求使用默认副本因子时采用的副本数，包含 Leader | `1` | 至少 3 个 Broker 的生产集群推荐 `3`；单节点开发环境用 `1` |
| `log.retention.ms` | 日志按时间保留的期限，清理以日志片段为单位 | 未显式设置；回退到分钟 / 小时配置，最终通常为 7 天 | 普通业务可从 `604800000`（7 天）开始；至少覆盖最长消费故障恢复和回放窗口 |
| `log.retention.bytes` | 每个分区允许保留的日志大小，按片段清理 | `-1`，不按容量限制 | 必须保留完整时间窗口时可用 `-1` 并做好容量规划；需要控制磁盘占用时，按每分区预算设上限 |
| `log.segment.bytes` | 单个日志片段的目标大小上限，触发滚动 | `1073741824`（1 GiB） | 高吞吐通常保留 1 GiB；低吞吐且希望片段更细时可试 `134217728`（128 MiB），结合滚动时间设置 |
| `log.roll.ms` | 日志片段按时间滚动的间隔，即使没有达到大小上限也可滚动 | 未显式设置；回退到 `log.roll.hours=168`（7 天） | 高吞吐可保留默认；低吞吐可从 `3600000`（1 小时）到 `86400000`（1 天）选择 |
| `min.insync.replicas` | `acks=all` 写入所需的最少 ISR 副本数，包含 Leader | `1` | 3 副本生产 Topic 推荐 `2`，同时配置 Producer `acks=all`；单副本开发环境用 `1` |
| `message.max.bytes` | Broker 接收的最大 record batch 大小，启用压缩时按压缩后的 batch 判断 | `1048588`，约 1 MiB | 普通事件保留默认，并把业务消息控制在明显低于 1 MiB；大消息优先存对象存储，Kafka 只传引用 |

`log.retention.ms` 优先于 `log.retention.minutes`，后者优先于 `log.retention.hours`；`log.roll.ms` 优先于 `log.roll.hours`。未设置毫秒参数不代表没有时间限制。

## 2. num.partitions：分区数决定并行能力

分区是 Kafka 存储、复制和消费者组分工的基本单位。同一个消费者组里，一个分区同一时刻只交给一个消费者，因此 3 个分区最多支持 3 个消费者同时承担分区消费。

- 按峰值生产吞吐、单分区实测吞吐和消费处理能力估算分区数，并预留余量。
- 分区越多，日志文件、索引、复制连接和元数据管理成本越高，不建议无依据地设置成几百个。
- 增加分区可能改变 key 到分区的映射；历史数据不会自动重分布，依赖 key 顺序的业务需要规划迁移。
- 修改该默认值不会改变已有 Topic 的分区数；已有 Topic 可以增加分区，通常不能直接减少。

## 3. default.replication.factor：副本数决定冗余成本

副本因子为 `3` 表示每个分区共保存 3 份，通常是 1 个 Leader 加 2 个 Follower。3 个分区、3 个副本共有 9 份分区副本，存储和复制流量也相应增加。

生产环境通常使用 3 副本，并尽量跨故障域部署。副本数不能超过可用 Broker 数；只增加副本数并不能独立保证消息可靠性，还需要配合确认机制和 ISR 门槛。

修改默认副本因子不会给已有 Topic 自动增加副本；已有 Topic 需要通过副本重新分配调整。内部 Topic 还可能有独立的副本配置。

## 4. log.retention.ms 与 log.retention.bytes：保留多久、保留多少

### 时间保留

`log.retention.ms=604800000` 表示配置 7 天时间保留。Kafka 按日志片段清理，不会逐条删除到期消息，也不会因为消息已被消费就立即删除。

现代消息格式下，时间清理通常依据片段内最大的消息时间戳判断整个片段是否过期。使用默认的 `CreateTime` 时，生产者时间戳异常可能影响清理；它不是简单地从片段关闭时开始一个新的保留期。

### 容量保留

`log.retention.bytes` 是**每个分区**的限制，不是整个 Topic 或整个 Broker 的限制。例如 6 个分区，每分区 10 GiB，单份逻辑日志预算约 60 GiB；副本因子为 3 时，集群保存这些副本需要约 180 GiB，还要额外预留索引、活动片段、清理延迟和磁盘余量。

时间与容量条件是“任一满足即可触发删除”，不是必须同时满足。例如同时设置保留 7 天和每分区 10 GiB，流量大时可能不到 7 天就因容量限制删除数据。

这些配置不是精确的磁盘硬配额。清理按片段和周期执行，实际使用量可能暂时超过上限；容量规划还应考虑流量倾斜、压缩率和副本迁移。

## 5. log.segment.bytes：日志片段大小

消息到达 Broker 后，会被追加到对应分区的当前活动日志片段。继续追加将超过 `log.segment.bytes` 等滚动条件时，Kafka 会关闭当前片段并打开新片段。

**日志保留和滚动相关参数作用于日志片段，而不是逐条消息；`message.max.bytes` 则限制消息批次，不能把这 8 个参数都理解为片段参数。**

片段越小，文件创建、关闭、索引和清理操作越频繁，可能降低整体效率；片段越大，删除粒度越粗，较早写入的消息可能需要等待同一片段里较晚写入的消息也过期。

### 每天 100 MiB，为什么可能保留约 17 天？

假设**一个分区**每天写入 100 MiB 的实际日志，片段大小为 1 GiB，仅按容量滚动，且消息时间戳正常：

1. 填满片段约需 `1024 / 100 = 10.24` 天。
2. 最早写入的消息在第 7 天达到保留期限，但同片段较晚的消息还没有过期。
3. 最后一批消息约在第 10.24 天写入；整个片段到约第 17.24 天才满足 7 天时间保留条件。

所以“约 17 天”可以解释片段粒度带来的额外保留，但**不是默认配置下的最大值**。它要求时间滚动没有提前触发，也忽略了其他滚动条件和清理延迟。默认时间滚动约为 7 天，在持续写入且时间戳正常的情况下会先于容量条件滚动，上述例子里最早消息通常约在第 14 天附近具备整段清理条件。

这里也不是“关闭片段后重新计时 7 天”：计算依据是片段内消息时间戳。若 100 MiB 是整个 Topic 的日流量，还应先换算成各分区流量，不能直接套用上述计算。

## 6. log.roll.ms：低流量分区也要及时滚动

大小滚动和时间滚动哪个先满足，就可能先触发片段切换。因此低流量 Topic 不一定需要把片段改得很小，也可以缩短 `log.roll.ms`。

例如保留 7 天、时间滚动 1 天，在持续写入和正常时间戳的简化条件下，较早消息的实际保留时间可粗略估算为 7～8 天，再加清理检查与文件删除延迟。若时间滚动为 1 小时，这部分额外等待通常会更短，但文件数量会增加。

时间滚动不能理解为精确的定时关文件任务：常规滚动在追加时检查，空闲分区的处理还受 Kafka 版本和保留清理逻辑影响。清理检查间隔 `log.retention.check.interval.ms` 常见默认是 5 分钟，文件删除延迟 `log.segment.delete.delay.ms` 常见默认是 1 分钟，因此不要把上述估算当作严格删除时限。

## 7. min.insync.replicas：写入可靠性的最低门槛

生产环境常见组合是：

```text
副本因子 = 3
min.insync.replicas = 2
Producer acks = all
```

ISR 包含 Leader。正常有 3 个同步副本时，`acks=all` 等待当前 ISR 满足复制确认条件，不是只等待固定 2 个副本；`min.insync.replicas=2` 只是最低门槛。

剩下 2 个同步副本时仍可写入；只剩 1 个同步副本时写入会失败，以牺牲写可用性保护可靠性。Producer 需正确处理错误和重试。若使用 `acks=1`，这个参数不能提供同样的多副本确认保护。

单节点环境设置为 `2` 会导致 `acks=all` 写入无法满足条件。该组合也不等于每条消息都已在各副本强制刷盘，生产者幂等性和非干净 Leader 选举策略仍需单独考虑。

## 8. message.max.bytes：限制消息批次，不是日志文件

该参数限制 Broker 接受的 record batch 大小，batch 可包含多条记录和协议开销；启用压缩时，Broker 按压缩后的 batch 大小判断。因此不能把它当成业务 value 可以刚好占满的单条消息额度。

确需提高限制时，需要共同检查：

| 配置位置 | 参数 | 需要注意的配合关系 |
|---|---|---|
| Topic | `max.message.bytes` | 可以覆盖 Broker 的 `message.max.bytes` |
| Producer | `max.request.size` | 限制请求大小，并实际约束未压缩 batch 大小；应留出协议开销 |
| Broker 副本拉取 | `replica.fetch.max.bytes`、`replica.fetch.response.max.bytes` | 检查每分区和整体响应预算是否适合目标 batch |
| Consumer | `max.partition.fetch.bytes`、`fetch.max.bytes` | 检查每分区和整体响应预算，并评估并发消费内存 |

现代 Kafka 拉取接口对首个超限 batch 有确保消费进度的例外，因此拉取大小不全是严格硬上限；也不能因此忽略内存和网络预算。放大消息会增加复制、重试和垃圾回收成本，大文件更适合放对象存储。

## 9. 推荐配置示例

以下示例适用于至少 3 个 Broker、普通业务事件、期望保留 7 天本地日志的生产环境。低吞吐 Topic 可使用一天滚动作为起点；分区数仍需按业务验证。

```properties
# Broker 默认配置；Topic 可覆盖其中的日志与消息配置
num.partitions=3
default.replication.factor=3
log.retention.ms=604800000
# 不用容量条件提前清理，必须规划磁盘容量并设置监控告警
log.retention.bytes=-1
log.segment.bytes=1073741824
log.roll.ms=86400000
min.insync.replicas=2
message.max.bytes=1048588
```

Producer 需配合以下确认与幂等设置；Go 配置详见 [生产者常用参数](kafka-生产者常用参数.md)：

```properties
acks=all
enable.idempotence=true
```

单节点本地开发时，将副本因子和 `min.insync.replicas` 都改为 `1`，分区数可用 `1`。生产环境应监控磁盘剩余量、消费延迟、ISR 缩减和写入错误，确认保留窗口足够支撑故障恢复。

## 10. Broker 默认值与 Topic 覆盖项

| Broker 参数 | Topic 对应配置 / 操作 |
|---|---|
| `num.partitions` | 创建时指定分区数；已有 Topic 单独增加分区 |
| `default.replication.factor` | 创建时指定副本因子；已有 Topic 通过副本重新分配调整 |
| `log.retention.ms` | `retention.ms` |
| `log.retention.bytes` | `retention.bytes` |
| `log.segment.bytes` | `segment.bytes` |
| `log.roll.ms` | `segment.ms` |
| `min.insync.replicas` | `min.insync.replicas` |
| `message.max.bytes` | `max.message.bytes` |

已有 Topic 若显式配置了覆盖项，应以 Topic 的有效配置为准。Broker 参数能否动态修改需查看具体版本的 Update Mode；直接编辑配置文件不等于运行中的 Broker 已生效。

参考：[Apache Kafka 4.0 Broker 配置](https://kafka.apache.org/40/configuration/broker-configs/)、[Topic 配置](https://kafka.apache.org/40/configuration/topic-configs/)、[Producer 配置](https://kafka.apache.org/40/configuration/producer-configs/)、[Consumer 配置](https://kafka.apache.org/40/configuration/consumer-configs/)。

## 11. Kafka 4.x 的 ELR 与日志压缩补充

合格领导者副本（Eligible Leader Replicas，ELR，KIP-966）在 4.0 可选启用，4.1 新建集群默认启用。控制器跟踪可安全接任的副本，ISR 为空时也可能安全恢复服务；升级集群应核对实际特性级别，不能只看版本号。

ELR 配合严格最小 ISR 规则：ISR 数量低于 `min.insync.replicas` 时高水位不能推进。`acks=1` 不能保证消息已成为可消费的已提交数据。开启 ELR 后，动态最小 ISR 配置应在集群默认级或 Topic 级管理，不能单独按 Broker 动态覆盖；变更还可能清理 ELR 状态。详见 [官方 ELR 说明](https://kafka.apache.org/41/operations/eligible-leader-replicas/)。

| Topic `cleanup.policy` | 行为 | 适用场景 |
|---|---|---|
| `delete`（默认） | 按时间 / 容量删除旧片段 | 一段完整事件历史 |
| `compact` | 按 key 后台清理旧版本，保留最新状态 | 根据 key 恢复状态的变更日志 |
| `compact,delete` | 同时压缩旧版本、按保留条件删除 | 状态日志也有时间 / 容量上限 |

日志压缩（Log Compaction）不是 Snappy / ZSTD 的字节压缩。它异步执行，不保证随时每个 key 只剩一条；删除不重新编号 offset，因此读取位置可能不连续。带 key、value 为 null 的记录是删除标记（Tombstone）；状态恢复消费者需在删除标记被清理前完成扫描，窗口受 `delete.retention.ms` 等配置影响。

参考 [笔记导航与参考](kafka-笔记导航与参考.md) 与 [Kafka 官方设计](https://kafka.apache.org/42/design/design/)。
