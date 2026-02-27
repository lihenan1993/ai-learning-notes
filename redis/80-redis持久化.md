# Redis 持久化怎么选：RDB、AOF、混合

> 本文以 Redis 7.x 为基准；实现细节以 Redis 7.2.0 官方源码核实。

## 0. 问答总结

### 0.1 RDB 和 AOF 怎么选？

1. **RDB 是时间点快照，恢复快但会丢快照间写入。** 适合可重建缓存。
2. **AOF 记录写命令，丢失窗口由刷盘策略决定。** 7.x 常用 `everysec`；`always` 更耐丢但更慢。
3. **两者都不是业务账本。** 复制默认异步，故障切换仍可能丢已确认写入。

### 0.2 Redis 7 的 Multi-Part AOF 是什么？

1. **AOF 由 manifest、BASE 和 INCR 文件组成。** 启动先加载 BASE，再按清单重放增量。
2. **重写时父进程立即写新的 INCR，子进程生成 BASE。** 这样减少重写缓存和切换阻塞。
3. **它不会自动开启 AOF。** 仍需 `appendonly yes`；混合 RDB 前缀只是 AOF 的 BASE 形态。

## 1. 详细知识点

## 1. RDB：全量快照，默认够缓存场景

**数据可从上游重建、能接受分钟到小时级丢失窗口，默认只开 RDB。日常走 `BGSAVE`（或 `save` 规则触发的后台快照），不要在生产对大实例手敲阻塞式 `SAVE`。**

用途：重启还原、拷到别的机器做副本、留备份。默认文件名 `dump.rdb`，目录由 `dir` 决定。

### `SAVE` 与 `BGSAVE`

| 命令 | 谁写盘 | 主线程 |
|---|---|---|
| `SAVE` | 主进程主线程自己 | 被占住，不能处理命令 |
| `BGSAVE` | `fork` 出的子进程 | 空出来，可继续处理命令 |

自动快照（`save m n`）走 BGSAVE。Redis 7.2 默认更保守，大致是「一小时内至少 1 次改、五分钟内至少 100 次改、一分钟内至少 10000 次改」这类阈值；具体数字面试开口说「有多档 `save`、走后台」即可，不必背死配置行。

### `fork` + COW 长什么样

```
触发 BGSAVE / save 规则
        ↓
主线程 fork 子进程（短暂停：只复制页表，不复制整份物理内存）
        ↓
父子页表指向同一批物理页，标成只读
        ↓
子进程按 fork 瞬间的视图写 temp-<pid>.rdb
主线程继续接写请求
        ↓
主线程改某页 → 缺页 → 内核拷贝该页给父进程（COW）
子进程仍看旧页
        ↓
子进程写完 → 原子替换 dump.rdb
```

日常磁盘 I/O 在子进程，影响相对小。边界要清楚：

- 实例很大（例如 20GB+）时，复制页表也会让主线程停几十到几百毫秒。
- 快照期间写很多，COW 会复制大量脏页，物理内存峰值接近「原内存 + 变更页」，不够会 OOM；生产常给实例留余量给 COW。
- Transparent HugePage（大页）下，COW 可能一次拷 2MB 级页面，放大延迟与内存尖峰；运维上常关掉 THP。细节到「变慢怎么查」再展开，见 `105-线上redis变慢怎么查.md`。

### 丢失窗口与过期键

两次 RDB 之间的写入，宕机就没了。这是选 RDB 时必须接受的窗口。

生成 RDB 时过期键不写入。主库载入时再丢已过期的；从库载入时先原样装上，物理删除等主库的 `DEL`，避免主从数据集分叉。过期策略本身见 `50-redis过期策略.md`。

`stop-writes-on-bgsave-error` 默认倾向「BGSAVE 失败就停写」，避免静默丢持久化能力——这是取舍，不是永远正确。

---

## 2. AOF：追加日志，换更小的丢失窗口

**要把 Redis 当准库、尽量少丢，打开 AOF，刷盘策略默认用 `everysec`。金融级、能接受更慢，再上 `always`。不要默认以为开箱就有 AOF。**

写命令按 Redis 协议追加。路径仍由 `dir` 决定。开了 AOF 后，执行写命令会先改内存，协议内容进 `aof_buf`，事件循环末尾再决定怎么刷到文件。

### 写后执行，还是写前

命令是**先在内存执行成功，再记 AOF**。语法校验、类型检查在执行路径上完成，不会因为「日志还没写」就挡住合法写入的校验。代价是：若进程在「内存已改、AOF 尚未落到磁盘」之间崩溃，那一小段会丢——窗口大小由刷盘策略决定，不是由「写前日志」那种数据库 WAL 语义决定。

### 三种刷盘策略（`appendfsync`）

| 策略 | 做什么 | 丢数据风险 | 性能 |
|---|---|---|---|
| `always` | `aof_buf` 写入并 `fsync` | 最多丢约一条命令量级 | 最差，每条写都等盘 |
| `everysec`（默认） | 先 `write`；约每秒由专门线程 `fsync` | 最多约 1 秒 | 生产常用折中 |
| `no` | 只 `write`，何时 `fsync` 交给 OS | 可能更多 | 最快，失控感强 |

注意：`write` 只到操作系统页缓存；`fsync` / `fdatasync` 才真正落盘。`always` 慢是因为每条写都要 `fsync`，和 RDB 的阻塞 `SAVE` 不是一回事。

### AOF 重写：为什么能变小

AOF 记历史命令，时间越长越大。重写不是拷旧日志，而是按**当前内存最终状态**生成一套最精简的写命令。

```
旧 AOF：SET k 1 → SET k 2 → SET k 3 → ...
重写后：只保留 SET k 3
过期已删的键：直接跳过
多次 SADD：合成一条多 member
```

触发：手动 `BGREWRITEAOF`；或体积超过阈值且相对上次重写增长够大（默认大约「至少 64MB 且翻倍」这一档思路）。重写期间还会再 `fork`，高写入时同样有 COW 压力。

### Redis 7.0+：Multi-Part AOF

7.0 起开了 AOF 后，不再只是单个 `appendonly.aof`，而是一个目录（默认 `appendonlydir`），由清单记下当前文件：

```
appendonlydir/
  appendonly.aof.manifest
  appendonly.aof.1.base.rdb    # BASE：上次重写时的全量（常是 RDB）
  appendonly.aof.1.incr.aof    # INCR：之后的增量命令，可有多个
```

恢复：先加载 BASE，再按 manifest 顺序重放 INCR。

重写时主进程新开一个 INCR 接着记命令，子进程独自生成新 BASE，两边不双写、也不再把增量先堆进重写缓存。两边就绪后原子更新 manifest，旧文件标成 HISTORY 再删。相对老单文件重写：

- **省内存**：不再把重写期间的新命令堆进重写缓存。
- **少堵主进程**：结束时不用把缓存刷进新文件再 `fsync`。
- **少写一遍盘**：新命令只进新开的 INCR。

过期键被真正删除时，AOF 会追加 `DEL`；重写时已过期的键不会写进新 BASE。

---

## 3. 混合持久化与启动加载

**开了 AOF 且启用 RDB 前缀（7.2 里 `aof-use-rdb-preamble` 默认倾向开启）时，重写产出的 BASE 就是 RDB 镜像，后面接增量 AOF。恢复先吃快照头、再重放尾巴。这是「一个逻辑 AOF 里的两段」，不是先读 `dump.rdb` 再读另一份无关的 AOF。**

```
重启加载
        ↓
开了 AOF？
  ├── 是 → 按 manifest 加载 BASE（常为 RDB）再重放 INCR
  └── 否 → 加载 dump.rdb
```

AOF 通常比纯 RDB 更新，所以开了 AOF 就以 AOF 族为准。混合解决的是「纯命令重放太慢」；它不自动替你打开 `appendonly`。

---

## 4. 为什么默认不开 AOF，以及怎么开口选型

**开箱优先性能和缓存场景，而不是「一条都不能丢」。数据可从 MySQL / 上游重建时，只开 RDB；当库、尽量不丢时 `appendonly yes` + `everysec`；极端场景再 `always`。**

不开 AOF 的常见理由：即使 `everysec`，高写入仍吃磁盘与缓冲；恢复时纯 AOF 重放可能远慢于反序列化 RDB；文本协议冗余易把盘写满进而拒写；产品定位长期是缓存优先。

权威数据仍应放数据库。Redis 持久化降低的是**缓存层或热状态**的丢失窗口，不是把 Redis 变成强一致账本。和 MySQL 的职责边界见 `100-redis和mysql怎么保持一致.md`。

Stream / 队列若依赖 Redis 里的消息不丢，写入成功只代表主内存有了，落盘与复制是另一层，见 `85-redis能当消息队列吗.md`、`140-redis高可用.md`。

---

## 补充：RDB、AOF 与混合的边界

| | 本质 | 解决什么 | 不解决什么 | 核心代价 |
|---|---|---|---|---|
| **RDB** | 时间点压缩二进制快照 | 快速恢复、备份、全量同步底稿 | 两次快照间的写入 | `fork` + COW 内存与偶发抖动 |
| **AOF** | 写命令追加日志 | 更小的丢失窗口（常约 1 秒） | 不替代「权威在 MySQL」 | 体积大、重放慢、重写再 `fork` |
| **混合** | AOF 文件头是 RDB，尾是增量命令 | 恢复快一截，又留住增量 | 仍依赖你开了 AOF | 配置与文件形态更绕 |
| **Multi-Part AOF（7.0+）** | base + incr + manifest 目录 | 重写少占内存、少堵主线程 | 仍默认不自动开 AOF | 运维要认目录与清单 |

---

## 对照记

```
只开 RDB（BGSAVE + COW）
  ↓ 解决了快速恢复与备份；两次快照间会丢，fork/HugePage 会抖
AOF everysec
  ↓ 解决了约 1 秒丢失窗口；体积与重放变重，重写再 fork
AOF always
  ↓ 解决了更小的丢失窗口；每条写等盘，吞吐差
混合 + Multi-Part AOF（base/incr/manifest）
  ↓ 解决了恢复速度与重写期内存/堵主问题；仍要你主动开 AOF
把权威放 MySQL / 专用存储
  ↓ Redis 再怎么持久化，也不替代说了算的那一层
```

一句话：**缓存可重建用 RDB；当库少丢开 AOF 默认 `everysec`；认清 `fork`+COW 与刷盘代价；7.2 用 Multi-Part 混合加快恢复，但权威数据别只押在 Redis 上。**

## 99. 官方依据

- Redis 7.2.0 源码：`src/multi.c`（事务入队、EXECABORT、WATCH 冲突）。
- Redis 7.2.0 源码：`src/eval.c`、`src/functions.c`、`src/script.c`（Lua/Functions 串行执行、超时与 SCRIPT KILL 限制）。
- Redis 7.2.0 源码：`src/aof.c`（Multi-Part AOF 重写、BASE/INCR/manifest）。
- Redis 7.2.0 源码：`src/replication.c`（WAIT、WAITAOF 复制与本地 AOF 确认）。
- Redis 官方命令文档：ZSET、Streams、Pub/Sub、Sentinel、Cluster、SET NX/PX。
