# Redis 能当消息队列吗

> 本文以 Redis 7.x 为基准；实现细节以 Redis 7.2.0 官方源码核实。

## 0. 问答总结

### 0.1 Redis 能不能当消息队列？

1. **能，但按可靠性和积压规模选结构。** List 做简单任务，Stream 做消费组和确认，Pub/Sub 只做在线通知。
2. **Redis Stream 是至少一次投递。** ACK 前宕机会重投，业务必须幂等。
3. **长期积压、分区扩展和历史回放优先 Kafka 等专业 MQ。** Redis 的持久化和异步复制也有丢失边界。

### 0.2 Stream 的 ACK 会删除消息吗？

1. **不会。** `XACK` 只移除消费组的待确认记录。
2. **消息仍在 Stream 中。** 用 `XDEL` 或 `XTRIM` 控制长度。
3. **超时未确认要认领。** 用 `XPENDING`、`XCLAIM` 或 `XAUTOCLAIM`，并设置重试和死信策略。

## 1. 详细知识点

## 1. List：简单的点对点队列

任务数量不大、积压时间较短，且失败后可以重新查询数据库或重新计算时，可以使用 List。生产者用 `LPUSH` 入队，消费者用 `BRPOP` 阻塞出队：

```text
LPUSH jobs:audit creative:10086
BRPOP jobs:audit 5
```

`BRPOP` 是原子操作，消息取出后立即从 List 删除。消费者在处理过程中宕机，消息就会丢失，因为 List 没有 ACK。

如需提高可靠性，可以先将消息移动到“处理中”队列，处理成功后再删除：

```text
BLMOVE jobs:audit jobs:audit:doing LEFT RIGHT 5
成功 → LREM jobs:audit:doing 1 creative:10086
失败 → 消息仍在 jobs:audit:doing，等待清理或重试
```

这种方案仍需业务自行处理超时清理、重复消费和重试次数。List 只能实现竞争消费，不能广播；消息取出后也不能直接回放。积压过多还会形成大 key，详见 `60-redis为什么不能存大key.md`。

## 2. Pub/Sub：在线通知，不是消息队列

Pub/Sub 只保证发布时在线的订阅者能够收到消息。Redis 不会保存 Pub/Sub 消息，因此订阅者断线、Redis 重启，或订阅发生在发布之后，都无法补收。

```text
SUBSCRIBE cache:invalidate
PUBLISH cache:invalidate item:10086
```

它适合发送缓存失效、配置变更等实时通知，不适合投递必须执行的业务任务。Pub/Sub 没有积压、消费进度和 ACK；慢消费者还可能因输出缓冲区堆积而被 Redis 断开。

Redis 7 提供分片 Pub/Sub：`SPUBLISH` 和 `SSUBSCRIBE`，可以减少集群中的传播开销，但仍然**不落盘、不补发**。

## 3. Stream：支持消费组和确认

当任务需要消费组、ACK 和失败重试时，应使用 Stream。典型流程如下：

```text
XADD stream:ad:click * click_id c_10086 uid 1001
XGROUP CREATE stream:ad:click cg:billing 0 MKSTREAM
XREADGROUP GROUP cg:billing worker-1 COUNT 10 STREAMS stream:ad:click >
XACK stream:ad:click cg:billing 1730000000000-0
```

Stream 是追加日志结构。每条消息都有唯一 ID。同一消费组中的消费者会竞争消费，一条消息只分配给一个消费者；不同消费组可以分别读取同一条消息。

消费组通过 PEL（Pending Entries List）记录“已投递但未确认”的消息。消费者宕机后，其他消费者可以用 `XPENDING` 查找长时间未确认的消息，再用 `XCLAIM` 或 `XAUTOCLAIM` 转移并重试。

**ACK 不会删除 Stream 中的消息。** ACK 只表示当前消费组不再需要重新投递；要删除消息，需要使用 `XDEL` 或 `XTRIM`。

Stream 本质上是一个 Redis key，在集群中通常位于同一个槽，因此写入和积压会集中到一个节点。生产环境应定期使用 `XTRIM` 控制长度，否则消息会持续占用内存。

## 4. 可靠性要分三层理解

### 消息是否持久化

`XADD` 成功只表示消息已写入主节点内存。能否在重启后恢复，取决于 RDB 和 AOF 配置。Redis 主从复制默认是异步的：主节点返回成功后，如果尚未同步到从节点就发生切换，刚写入的消息仍可能丢失。`WAIT` 可以缩小风险窗口，但不能等同于同步复制。Pub/Sub 消息不进入 key 空间，因此不受持久化和复制保护。

### 消息是否能够重试

Stream 只能保证未 ACK 的消息仍可被重新处理；业务仍需定期检查 `XPENDING`，并使用 `XCLAIM` 或 `XAUTOCLAIM` 认领超时消息。使用 `NOACK` 会跳过 PEL，可靠性会下降到接近 List 直接出队的水平。

### 是否支持恰好一次

Redis Stream 提供的是**至少一次投递**，不是恰好一次。消费者可能已经完成业务处理，却在 ACK 前宕机，恢复后同一条消息会再次投递。因此，扣库存、加积分、回调等业务必须具备幂等性。

Redis 没有内置死信队列。达到最大重试次数后，应由业务将消息写入独立的 DLQ Stream，或保存到数据库供人工处理。

## 5. 什么时候不应使用 Redis

以下场景更适合 Kafka 或 RocketMQ：消息需要保存数天或数周、积压规模较大、需要分区扩展、需要长期历史回放，或需要自动再均衡、死信队列和消费延迟监控。

广告点击、曝光等高吞吐且需要长期保存的数据，通常使用 Kafka 或 RocketMQ；Redis 更适合保存热状态和处理短期任务。

## 6. 记忆要点

```text
List：竞争出队，简单但无 ACK；
Pub/Sub：在线广播，不落盘、不补发；
Stream：追加日志，支持消费组、ACK 和重试；
Kafka / RocketMQ：适合长期积压、分区扩展和完整治理。
```

一句话总结：**简单任务用 List，实时通知用 Pub/Sub，需要确认和重试用 Stream；需要长期保存、持续积压或大规模扩展时，使用 Kafka 或 RocketMQ。**

## 99. 官方依据

- Redis 7.2.0 源码：`src/multi.c`（事务入队、EXECABORT、WATCH 冲突）。
- Redis 7.2.0 源码：`src/eval.c`、`src/functions.c`、`src/script.c`（Lua/Functions 串行执行、超时与 SCRIPT KILL 限制）。
- Redis 7.2.0 源码：`src/aof.c`（Multi-Part AOF 重写、BASE/INCR/manifest）。
- Redis 7.2.0 源码：`src/replication.c`（WAIT、WAITAOF 复制与本地 AOF 确认）。
- Redis 官方命令文档：ZSET、Streams、Pub/Sub、Sentinel、Cluster、SET NX/PX。
