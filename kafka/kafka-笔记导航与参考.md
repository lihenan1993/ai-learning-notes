# Kafka 4.x 笔记导航与参考

本组笔记区分 Kafka Broker 的能力、Java 客户端配置和 IBM Sarama 的实际接口。Kafka 4.x 新功能要看具体小版本，Sarama 配置默认值按 v1.60.2 核对，不能相互替代。

## 阅读顺序

| 笔记 | 内容 |
|---|---|
| [基础知识](kafka-基础知识.md) | Topic、分区、副本、KRaft、消费进度与消息语义 |
| [KRaft 控制器入门](kafka-KRaft控制器入门.md) | 从零理解控制器、元数据复制、选举、快照、动态仲裁组与排查 |
| [概念和特性](kafka-概念和特性.md) | 顺序写、缓存、批量、零拷贝与并行的性能边界 |
| [Broker 常用参数](kafka-broker常用参数.md) | 保留策略、日志片段、复制与消息大小 |
| [生产者常用参数](kafka-生产者常用参数.md) | Sarama 默认值、推荐配置与发送示例 |
| [消费者配置](kafka-消费者配置与再均衡.md) | Sarama 配置、位点提交、生命周期与默认代码 |
| [重平衡与共享组](kafka-重平衡与共享组.md) | 经典策略、静态成员、KIP-848、Share Groups 与重平衡风暴 |

## 教程参考范围

优先参考 [waylau/apache-kafka-tutorial《跟老卫学 Apache Kafka 开发》](https://github.com/waylau/apache-kafka-tutorial)。2026-05-06 已读取其 README 目录及作者的 [Kafka 4.0 Windows 安装文章](https://waylau.com/installation-and-use-of-apache-kafka-4-on-windows/)。

仓库主体提供文章外链，不是全部章节正文。消费者设计、消息传递语义和效率等华为页面在本次访问中只返回动态页面外壳，未能读取正文，因此不能声称已经逐章核对全部教程；以下条目作为待阅读入口，具体修订另以已读取的官方文档佐证：

- [设计原理之消费者](https://developer.huawei.com/consumer/cn/blog/topic/03911823255370132)
- [设计原理之消息传递语义](https://developer.huawei.com/consumer/cn/blog/topic/03912690198990147)
- [设计原理之效率](https://developer.huawei.com/consumer/cn/blog/topic/03907502106980111)

教程目录也包含历史 ZooKeeper 章节，不能把所有章节当作 Kafka 4.x 配置。安装文章的静态 Controller 配置是一种部署方式，不代表动态仲裁组也必须使用 `controller.quorum.voters`；新集群按对应版本官方快速入门配置。不要将旧目录重新格式化作为升级步骤。

## 版本结论与核对资料

| 变化 | 适用范围 |
|---|---|
| KRaft 取代 ZooKeeper | 4.0 起移除 ZooKeeper 模式；升级前完成迁移 |
| KIP-848 新消费者组协议 | 4.0 GA，需客户端支持并选择新协议；不同于经典协作黏性 |
| 合格领导者副本 ELR | 4.0 可选，4.1 新建集群默认启用；升级集群核对特性级别 |
| Share Groups 队列式消费 | 4.0 早期访问、4.1 预览、4.2 生产就绪 |

官方核对来源：

- [Kafka 4.0 升级说明](https://kafka.apache.org/40/getting-started/upgrade/)
- [Kafka 4.0 快速入门](https://kafka.apache.org/40/getting-started/quickstart/)
- [Kafka 4.1 ELR 说明](https://kafka.apache.org/41/operations/eligible-leader-replicas/)
- [Kafka 4.2 设计：效率、语义、复制、共享组与日志压缩](https://kafka.apache.org/42/design/design/)
- [Kafka 4.2 Broker 参数](https://kafka.apache.org/42/configuration/broker-configs/)
- [Kafka 新消费者协议](https://kafka.apache.org/42/operations/consumer-rebalance-protocol/)
- [Kafka 4.2 发布公告](https://kafka.apache.org/blog/2026/02/17/apache-kafka-4.2.0-release-announcement/)
- [Sarama v1.60.2 配置源码](https://github.com/IBM/sarama/blob/v1.60.2/config.go)
