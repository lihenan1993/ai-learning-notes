# 线上 Redis 变慢如何排查

## 0. 问答总结

### 0.1 线上 Redis 变慢如何排查 的核心结论是什么？

1. **先说结论：** Redis 出现延迟升高时，应按照“业务链路 → 命令和数据 → 延迟事件 → 机器与网络 → 持久化和复制”的顺序排查。首先确认问题确实发生在 Redis，不要在没有定位原因前直接重启实例。
2. **版本边界：** 本文以 Redis 7.x 为基准；配置、默认值和实现细节以注明的 7.2.0 依据为准。
3. **落地边界：** 方案要结合流量、数据规模和一致性要求验证，不能把经验阈值当成 Redis 保证。

Redis 出现延迟升高时，应按照“业务链路 → 命令和数据 → 延迟事件 → 机器与网络 → 持久化和复制”的顺序排查。首先确认问题确实发生在 Redis，不要在没有定位原因前直接重启实例。

相关知识：`20-redis单线程模型.md`、`60-redis为什么不能存大key.md`、`65-redis热key.md`、`80-redis持久化.md`。

## 1. 先确认是否是 Redis 本身变慢

业务接口变慢，不一定意味着 Redis 变慢。应先对比客户端访问 Redis 的耗时、连接池等待时间、下游 MySQL 耗时和网络延迟。

- 只有访问某个 key 或某个 slot 的接口变慢：优先检查热 key 和大 key；
- 整个实例的命令耗时同时升高：检查 Redis 主线程和机器资源；
- 本机 `redis-cli` 很快，但远程应用很慢：优先检查网络路径、连接池和跨可用区访问。

确认问题范围后再进入 Redis 实例排查，避免误重启导致故障扩大。

## 2. 查看慢日志：定位执行时间过长的命令

`SLOWLOG` 记录 Redis 主线程执行时间超过阈值的命令，适合发现 `KEYS`、无游标的 `HGETALL` / `SMEMBERS`，以及操作超大集合等 O(N) 命令。

```text
redis-cli SLOWLOG GET 10
redis-cli SLOWLOG LEN
```

重点查看命令、执行耗时和客户端信息：

| 命令模式 | 主要问题 | 改进方向 |
|---|---|---|
| `KEYS creative:*` | 扫描全部 key，阻塞主线程 | 使用 `SCAN`，生产环境禁止使用 `KEYS` |
| `HGETALL user:{1001}:profile` | 一次返回过多 field | 拆分 key，或只读取所需 field |
| 对大 List / ZSet 做全量读取 | 单次操作成本过高 | 分页读取，使用小批量 Pipeline |

`SLOWLOG` 只记录 Redis 内部执行时间，不包括网络排队和客户端序列化时间。因此，未发现慢日志并不能排除短时延迟尖刺，还需要结合 `LATENCY` 和客户端监控判断。

## 3. 检查大 key 和热 key

大 key 是单次操作成本高；热 key 是单个 key 的访问量过大，导致某个线程、节点或 slot 持续承受高负载。

```text
redis-cli --bigkeys
redis-cli --hotkeys
redis-cli MEMORY USAGE creative:{10086}:info
```

`--bigkeys` 和 `--hotkeys` 都会扫描实例数据，线上应控制执行频率，避免在高峰期对大型实例进行无节制扫描。`MEMORY USAGE` 可以进一步确认单个 key 的内存占用。

常见排查链路是：慢日志发现 `HGETALL` → 使用 `MEMORY USAGE` 或 `HLEN` 确认 field 数量过多 → 拆分 Hash 或改为按需读取。热 key 的处理方式通常包括拆分 key、增加本地缓存或调整访问模型，详见 `65-redis热key.md`。

## 4. 使用 LATENCY 分析延迟事件

当命令本身并不复杂，但延迟会周期性出现尖峰时，应查看 Redis 的延迟事件：

```text
redis-cli LATENCY LATEST
redis-cli LATENCY DOCTOR
```

`LATENCY LATEST` 展示近期各类延迟事件的峰值和发生时间；`LATENCY DOCTOR` 提供延迟原因的分类提示，例如命令执行、AOF 或 fork。它们用于初步分诊，具体处理仍需回到对应层面。

Redis 7.2 还可以结合 `INFO commandstats`，查看各类命令的累计调用次数和耗时。

## 5. 检查操作系统和网络

如果 Redis 内部命令耗时正常，但客户端请求仍然变慢，应检查运行环境。

### SWAP

物理内存不足时，操作系统会将数据换出到磁盘。Redis 依赖内存读写，一旦频繁使用 SWAP，延迟可能从微秒级升高到毫秒级甚至更高。应结合 `INFO memory` 和系统 `vmstat` 查看内存及换页情况。解决方向是扩容、减少数据量或降低负载，而不是简单调高慢日志阈值。

### Transparent Huge Pages

Linux 的 THP 可能放大 Redis 执行 `fork` 时的内存和页表开销。当 RDB 快照或 AOF 重写触发 fork 时，可能产生明显的延迟尖峰。生产环境通常会关闭 Redis 所在机器的 THP，相关原理见 `80-redis持久化.md`。

### 网络

本机 `redis-cli` 访问正常而远程应用变慢时，应检查带宽、丢包、重传、连接数、跨可用区访问以及网卡是否达到上限。热 key 造成单节点出流量过高，也可能表现为网络层面的 Redis 变慢。

## 6. 检查持久化和主从复制

写入量增加、磁盘延迟升高或副本执行全量同步时，延迟可能来自持久化和复制，而不是业务命令复杂度。

```text
redis-cli INFO persistence
redis-cli INFO replication
```

重点关注以下情况：

| 现象 | 优先检查 | 处理方向 |
|---|---|---|
| 写请求延迟周期性升高 | AOF `fsync`、磁盘延迟 | 调整持久化策略，使用更快的磁盘，错峰重写 |
| 所有命令同时短暂卡顿 | fork 耗时、THP、实例内存过大 | 控制实例规模，关闭 THP，错峰执行重写 |
| 从库重连后主库明显抖动 | 全量复制 | 尽量使用增量同步，检查复制带宽和相关参数 |

持久化和复制的具体机制见 `80-redis持久化.md` 与 `140-redis高可用.md`。

## 7. 排查顺序总结

```text
确认慢在 Redis 往返
  ↓ 排除客户端、连接池和下游服务
SLOWLOG
  ↓ 定位 O(N) 命令和大对象操作
bigkeys / hotkeys / MEMORY USAGE
  ↓ 定位大 key 与热 key
LATENCY LATEST / LATENCY DOCTOR
  ↓ 判断命令、fork 或 AOF 延迟
SWAP / THP / 网络
  ↓ 检查操作系统与网络瓶颈
AOF fsync / fork / 全量复制
  ↓ 定位持久化和复制造成的实例抖动
```

一句话总结：**Redis 变慢时，先确认慢在 Redis，再依次检查慢日志、大 key 与热 key、延迟事件、机器网络以及持久化和复制；常见根因是重命令、fork、fsync、SWAP、THP 或网络资源耗尽。**


## 99. 官方依据

- Redis 7.2.0 官方源码与配置：`notes/.redis-rewrite-sources/redis-7.2.0.conf` 及对应源码缓存。
- Redis 命令参考：https://redis.io/docs/latest/commands/
