# Kafka 的核心概念和为什么快

**Kafka 是一个分布式、持久化的发布-订阅消息系统：Producer 把消息写入 Topic 的 Partition，Consumer Group 并行拉取并处理；Broker 组成集群，Partition 通过副本实现容错，顺序写、批量处理和零拷贝让它兼顾高吞吐与可扩展性。**

---

## 1. Kafka 的核心概念

### 1.1 一条消息怎么流转

Producer 不直接把消息发给某个 Consumer，而是把消息写入指定 Topic。Topic 只是逻辑分类，真正承载数据的是 Partition；Consumer 按 Partition 拉取消息。

```text
Producer
   ↓ 写入
Topic: order-events
   ↓ 按 key 选择 Partition
Partition 0 / Partition 1 / Partition 2
   ↓ Consumer Group 拉取
Consumer → 处理订单消息
```

- **Producer**：生产消息，可以按业务类型写入不同 Topic，也可以通过消息 key 让相关消息进入同一个 Partition。
- **Consumer**：主动拉取消息并处理。Kafka 不把消息直接推送到 Consumer，而是由 Consumer 维护消费进度。
- **Broker**：Kafka 集群中的一个服务节点。一个 Broker 可以承载多个 Topic 的多个 Partition。
- **Topic**：消息的逻辑分类，例如 `order-events`、`payment-events`。
- **Partition**：Topic 的物理分片。消息在一个 Partition 内按 offset 递增追加，Partition 之间通常不保证全局顺序。
- **Offset**：消息在 Partition 中的位置，也是 Consumer 记录消费进度的依据。
- **Consumer Group**：一组共同消费 Topic 的 Consumer。一个 Partition 在同一时刻只会分配给组内一个 Consumer，因此可以并行消费，但组内 Consumer 数量超过 Partition 数量时，多出来的 Consumer 会空闲。

### 1.2 Broker、Partition 副本和 Leader

**Kafka 通过 Partition 副本解决单点故障，但副本不是多个 Topic；它是同一个 Partition 的多份数据。每个 Partition 在副本中选出一个 Leader，Producer 和 Consumer 默认都与 Leader 交互，Follower 负责复制数据并在故障时接替。**

```text
Topic: order-events
  Partition 0
    ├─ Broker 1：Leader
    ├─ Broker 2：Follower
    └─ Broker 3：Follower
```

Follower 主动从 Leader 拉取数据完成复制。Leader 故障后按 ISR 和选举规则选择新 Leader；启用合格领导者副本（Eligible Leader Replicas，ELR）时，也可选择被跟踪的安全候选。副本增加提供冗余，同时增加存储与复制开销。

### 1.3 ZooKeeper 与 KRaft

**Kafka 4.0 起已移除 ZooKeeper 模式，只支持 KRaft 管理元数据。** Controller 仲裁组通过 Raft 维护元数据日志，业务分区仍使用 Leader / Follower 复制。旧集群需先完成受支持的 KRaft 迁移再升级。

---

## 2. Kafka 为什么这么快

### 2.1 顺序写磁盘

**Kafka 不追求把每条消息随机写入不同位置，而是把消息追加到 Partition 的日志文件末尾。顺序写减少了磁盘寻道和随机 I/O，配合批量写入后，即使数据落盘，也能保持较高吞吐。**

Kafka 的数据不是只放在内存中，磁盘日志是主要存储，内存中的 Page Cache 负责加速读写。是否等待数据刷到磁盘、是否等待副本确认，则由可靠性配置决定：确认越严格，通常延迟越高。

### 2.2 批量发送和压缩

Producer 可以把多条消息批量发送，Broker 也能按批次写入和处理，减少网络往返、系统调用和磁盘操作次数。批量数据通常还会压缩，降低网络和磁盘带宽占用。

代价是批量等待会增加少量延迟；压缩还会消耗 CPU。因此实时性要求极高时，不能只追求更大的 batch。

### 2.3 零拷贝：读取时减少用户态拷贝

Consumer 读取已经落在 Page Cache 中的消息时，Kafka 可以借助 `sendfile` 等机制，让数据从内核缓存直接传输到网络 Socket，减少“内核态 → 用户态 → 内核态”的重复拷贝和上下文切换。

Kafka 的 TLS/SSL 数据通路不使用上述 `sendfile` 优化。`mmap` 常用于索引文件，不能与日志数据发送路径混为一谈。**零拷贝减少用户态与内核态的数据搬运，不代表完全没有内存复制。**

### 2.4 分区带来并行能力

一个 Topic 拆成多个 Partition 后，Producer 可以并行写入，多个 Broker 可以共同承载数据，Consumer Group 也可以让多个 Consumer 并行处理不同 Partition。

```text
一个 Topic
   ↓ 拆分
P0 ── Consumer 0
P1 ── Consumer 1
P2 ── Consumer 2
```

传统消费者组中，分区数量限制同时持有分区的消费者数量，不是业务线程数的硬上限，也不适用于共享组。分区增加会提高文件、句柄、选举和协调成本，应按吞吐和扩容需求规划。

### 2.5 Reactor 网络模型

Kafka 的网络层通常采用 Reactor 思路，把连接接入、网络读写和业务处理拆开：

```text
客户端请求
   ↓
Acceptor：接收连接
   ↓
Processor：读写网络、解析请求
   ↓
请求队列
   ↓
Worker：执行业务处理
   ↓
响应队列 → Processor → 客户端
```

网络线程不直接承担全部业务逻辑，Worker 线程负责请求处理，生产者与消费者之间通过队列解耦。这样可以分别调整网络线程和业务线程，避免慢业务处理阻塞连接接入。

---

## 3. 常见说法纠正

| 说法 | 更准确的表述 |
|---|---|
| 副本就是复制出来的 Topic | 副本是同一个 Partition 的多份数据，不是新建了多个 Topic |
| Consumer 订阅后 Broker 主动推送 | Consumer 通过拉取请求主动获取消息 |
| Topic 分区后，Consumer 必须和分区一样多 | 传统组可以启动更多消费者，但超过可订阅分区总数时有成员空闲；共享组允许多人合作消费一个分区 |
| Kafka 只靠内存所以快 | Kafka 主要使用磁盘日志，依靠顺序写、Page Cache、批量和零拷贝获得高吞吐 |
| Kafka 可以保证所有消息全局有序 | Kafka 通常只保证单个 Partition 内有序；需要同一业务键有序时，应让相关消息进入同一 Partition |

---

## 对照记

```text
单 Broker
  ↓ 多 Broker 集群
Partition 分区：解决并行和扩展
  ↓ Partition 副本
Leader / Follower：解决故障接管
  ↓ 批量 + 压缩 + 顺序写 + Page Cache + 零拷贝
高吞吐消息系统
```

一句话：**Kafka 快，不是因为“把数据全放内存”，而是因为消息按 Partition 顺序追加，配合批量、压缩、Page Cache、零拷贝和分区并行；Kafka 可靠，则依靠多 Broker 和 Partition 副本，Leader 负责对外服务，Follower 负责复制和故障接管。**

## Kafka 4.x 的适用范围

Kafka 也是事件流平台。Kafka 4.0 正式发布 KIP-848 新消费者协议，4.2 将共享组队列式消费标为生产就绪。共享组允许多个成员合作处理同一分区中的不同记录，不能套用传统组的消费者并行度限制。机制见 [重平衡与共享组](kafka-重平衡与共享组.md)，来源见 [笔记导航与参考](kafka-笔记导航与参考.md)。
