---
last_modified: 2026-06-27
tags: [milvus, mysql, 概念对照]
---

# Milvus 概念对照 MySQL

> 一句话结论：Milvus 的对象模型（database → collection → partition → segment）和 MySQL 的（database → table → partition → extent）几乎一一对应，但**索引是"算法选择器"而不是"加速器"、主键不承担唯一约束、写入不等于可查**这三点是 MySQL 里没有的，也是面试最容易被追问的地方。

## 1. 对象层级对照

| MySQL | Milvus | 类比成立度 | 关键差异（背这一句） |
|---|---|---|---|
| 实例 / 连接 | Milvus 实例（standalone 或 cluster），`uri="http://ip:19530"` | 成立 | 单机模式叫 Milvus Lite，就是一个 `.db` 文件，没有 etcd/MinIO/Kafka 三个依赖 |
| `CREATE DATABASE` | `client.create_database("shop")` | 成立 | 默认上限 64 个库（`maxDatabaseNum` 可调），主要拿来隔离租户 |
| `CREATE TABLE` | `Collection` | 成立 | 官方 glossary 原话：collection 等价于 RDBMS 的表 |
| 表结构 DDL / `DESCRIBE` | `Schema`（`create_schema()` + `add_field()`），`describe_collection()` | 成立 | 建表时就写死向量维度 `dim`，**建完不能改维度**，要改只能新建 collection 再迁数据 |
| `COLUMN` | `Field` | 成立 | 分两类：scalar field（INT64/VARCHAR/JSON…）和 vector field（FLOAT_VECTOR/BINARY_VECTOR/SPARSE_FLOAT_VECTOR），后者是 MySQL 没有的 |
| 行 | `Entity` | 成立 | 没有"行"的物理概念，entity 被打散进 segment 的 binlog |
| `PRIMARY KEY` | `is_primary=True` 的那个 field | **只有一半成立** | Milvus 主键**不做唯一性约束**：官方原话 "insert does not check for duplicate primary keys"。它是"路由 + 定位"用的，不是约束。要幂等得自己用 `upsert` |
| `AUTO_INCREMENT` | `auto_id=True` | 只有一半成立 | AutoID 按时间戳生成，**不连续、不保证单调**，别当业务 ID 用 |
| `VARCHAR(64)` | `VARCHAR, max_length=64` | 成立 | 必须显式给 max_length，写入超长直接报错 |
| `JSON` 列 | `enable_dynamic_field=True` 的 `$meta` | 成立 | 开启动态字段后，schema 里没定义的 key 自动进 `$meta`，查询写 `$meta["k"]` |
| 表别名 / 视图 | `Alias`（`create_alias`） | 别名成立，视图不成立 | alias 是"名字指向 collection"的指针，可以原子切换 —— 线上重建 collection 的标准做法（新建 `docs_v2` → 把别名指过去 → 删旧表），MySQL 里对应的是切库名/切表名，没有原子别名 |
| 一个库多张表 | 一个库多 collection | 成立 | 默认每实例上限 65536 个 collection（官方多租户页） |
| `PARTITION BY HASH` 分区表 | `Partition`（手工 `create_partition`） | 成立 | 每 collection 最多 1024 个 partition；partition 是**物理隔离 + 可整块 load/release**，不参与主键路由 |
| 无 | `Partition Key` | **类比不成立** | 建 schema 时指定 `partition_key_field="tenant"`，Milvus 自动按该字段哈希到 16 个内部物理分区（实测 `_pk_0.._pk_15` + `_default`），你不能再手工建分区 |
| 无（InnoDB extent / page） | `Segment` | 结构类比成立 | growing segment（内存、可搜、无索引）→ sealed segment（flush 到对象存储、建索引）；compaction 合并小 segment，对应 `OPTIMIZE TABLE` + InnoDB purge 的角色 |
| `CREATE INDEX` | `create_index(field, IndexParams)` | 名字同，语义不同 | 见第 3 节：Milvus 索引决定"用哪个算法查"，必须显式建，且 `search` 前要 load |
| `SELECT * FROM t` | `client.query(collection, filter="id > 10", output_fields=[...])` | 成立（只能单表） | 没有 JOIN、没有子查询、没有 GROUP BY/HAVING |
| `WHERE` | `filter="tenant == 't1' and age > 18"` | 成立 | 表达式语法是自有 DSL；没建 scalar 索引时就是暴力过滤 |
| 无 | `Metric Type`（L2 / IP / COSINE） | 类比不成立 | 建索引时绑定，决定"距离怎么算、能不能用这个索引"。相当于 MySQL 的 collation 之于索引，但更硬：metric 和 index type 必须匹配 |
| 无 | `Consistency Level` | 类比不成立 | Strong / Bounded staleness（默认）/ Session / Eventually，本质是 GuaranteeTs 水位，不是 MySQL 的隔离级别 |
| 无 | `Resource Group` | 近似成立 | 把 query node 分组，租户间做资源隔离，对应 MySQL 8 的 `CREATE RESOURCE GROUP`（限 CPU/线程），但 Milvus 分的是"查询节点"而不是线程 |
| `information_schema` / 慢日志 | Attu（Web UI）+ Prometheus + `get_query_segment_info` | 弱 | 运维手段少得多，没有 EXPLAIN 看执行计划 |

## 2. 语句级对照（最快建立直觉）

```text
MySQL                              Milvus(pymilvus)
---------------------------------  -----------------------------------------------
CREATE DATABASE shop;              create_database("shop")
USE shop;                          using_database="shop"
CREATE TABLE doc (...);            create_schema() + add_field() + create_collection()
SHOW TABLES;                       list_collections()
DESCRIBE doc;                      describe_collection("doc")
CREATE INDEX idx ON doc(c1);       create_index("doc", "c1", IndexParams(...))
INSERT INTO doc VALUES (...);      insert("doc", [{"id":1,"vec":[...],...}])
UPDATE doc SET v=1 WHERE id=1;     upsert("doc", {...})   -- 底层是 delete + insert
DELETE FROM doc WHERE id=1;        delete("doc", filter="id == 1")
SELECT * FROM doc WHERE id=1;      query("doc", filter="id == 1", output_fields=["*"])
SELECT c1 FROM doc ORDER BY 距离   search("doc", data=[q_vec], limit=10, output_fields=[...])
TRUNCATE TABLE doc;                delete 全量 filter，或 drop_collection 重建
```

## 3. 索引：为什么"Milvus 索引 ≠ MySQL 索引"

MySQL：索引是可选加速器，不建也能全表扫，语义不变。

Milvus：索引是**算法的选择**，直接决定召回结果怎么算出来。

- `FLAT` = 暴力精确，等价于 MySQL 全表扫 + 排序（`RAG_KNN和ANN.md`），召回 100%、最慢。
- `HNSW` = 近邻图，牺牲召回率换延迟（通常 recall 95%+，靠 `ef`/`M` 调）。
- `IVF_FLAT` / `IVF_PQ` = 先分桶再只在 nprobe 个桶里找，召回率由 `nprobe` 决定。
- `DISKANN` = 磁盘版 HNSW，省内存。
- `AUTOINDEX` = 让 Milvus 自己选（Zilliz Cloud 场景）。
- `INVERTED` = scalar 字段的倒排索引，这时候才真的等价于 MySQL 二级索引。
- `SPARSE_INVERTED_INDEX` + metric `BM25` = 对应 MySQL 的 `FULLTEXT`，但要用 Function 从文本自动生成稀疏向量（见 `milvus_bm25_demo.py`）。

一句话：**MySQL 建不建索引只影响快慢；Milvus 不建索引根本查不了（向量字段必须建索引才能 load），建了哪种索引直接改结果集。**

## 4. 多租户四档（他问的"多租户"就是这四层，官方文档 multi_tenancy.md）

| 档位 | 做法 | 租户上限（官方） | 隔离强度 | 代价 |
|---|---|---|---|---|
| Database 级 | 一租户一 database | 默认 64（`maxDatabaseNum` 可改） | 最强，支持 RBAC、每库独立 schema | 租户数被配置卡死 |
| Collection 级 | 一租户一 collection | 默认 65536 / 实例 | 强，物理隔离，可整表 load/release 做冷热 | 表数量大，元数据与内存压力 |
| Partition 级 | 一 collection 内手工 `create_partition` | 1024 / collection | 中，物理隔离但不支持分区级 RBAC | 必须自己建分区、自己管路由 |
| Partition Key 级 | schema 上 `partition_key_field="tenant"` | 百万级 | 弱（多个租户共享一个物理分区，只是逻辑隔离） | 全租户共用一套 schema；实测 Lite 上就是 16 个 `_pk_*` 分区 |

选择顺序（官方给的）：租户数 万级以上 → partition key；强合规隔离 → database / collection；要在租户间做聚合分析 → partition / partition key。

对应到他的广告业务：这里的"租户"就是**广告主 / 媒体 App / 团队环境**。SSP 场景里 tenant = publisher_id 或 app_id，用 partition key 最自然，因为 publisher 数会到几万。

## 5. 五条"别硬类比"的硬差异

1. **主键不是约束**。MySQL 插重复主键报 `Duplicate entry`；Milvus 照插，产生同 key 多条实体（官方 insert 页原文），只是查询可能只回一条。业务幂等必须自己用 `upsert` 或外部去重。
2. **写进去不等于查得到**。insert 先进 growing segment（内存、无索引、可暴力搜），`flush` 落盘成 sealed segment，建索引，再 `load` 到 query node 才高效可查。MySQL 是写完事务提交即可见，没有 index+load 阶段（这个差异和他熟悉的 Kafka → 落盘 → 建索引 → 上线服务链路更像）。
3. **没有事务**。没有 BEGIN/COMMIT，没有跨 collection 原子性。`upsert` 是 delete+insert 两步，不是原子的。
4. **没有 JOIN / 聚合**。filter 只能在一张 collection 内做标量谓词；跨库关联要在应用层（Go 侧）拼，或者把字段冗余进 collection。
5. **一致性级别不是隔离级别**。Strong / Bounded（默认）/ Session / Eventually 控制的是"查询能看到多新的写入"（GuaranteeTs 水位），不控制并发事务互相看不见。

## 6. 本次实测（2026-06-27，Milvus Lite / pymilvus 3.0.2）

脚本：`$TMPDIR/mv/probe_terms.py`（本机一次性 venv：`pip install pymilvus milvus-lite`）

```text
[create_collection(partition_key)] OK
[describe_collection] num_partitions=17   # 16 个 _pk_* + _default
[list_partitions] ['_default','_pk_0',...,'_pk_15']
[insert pk=1 twice] 两次都 insert_count=1，不报错   ← 主键不查重（官方原文一致）
[create_alias] OK -> ['docs_live']
[release_collection] 后仍能 search                ← Lite 无 query node，load/release 是空操作
```

结论：partition key 的物理分区数**实测是 16**，而 `use-partition-key.md` 里写 "num_partitions 默认 64"，两页不一致，以实跑和多租户页的 16 为准。

## 7. 存疑清单（别直接背）

- **`num_partitions` 默认值**：官方 `multi_tenancy.md` 说 16，`use-partition-key.md` 说 64。实测 Lite 是 16。集群版是否 64 未验证 —— 面试时说"默认十几个，具体看版本和配置"。
- **重复主键的查询表现**：官方说会留下重复实体；Lite 实测 `query(id==1)` 只回 1 条。属于实现差异，结论只能说到"不要依赖主键唯一"。
- **`count(*)` 是否是精确值**：Lite 上返回的是 1，未在有未 flush 数据的场景验证。存疑，别在面试里断言"count 精确"。
- **Milvus 完全无事务**：官方没有 BEGIN/COMMIT 相关页面，属实践结论（无 API），不是抄来的原文。

## 8. 面试答法

**问：Milvus 和 MySQL 有什么区别？**

- 结论：对象模型基本同构（database/collection≈库/表、field≈列、entity≈行），但 Milvus 是"向量索引 + 列式标量存储 + 段式写入"的分析型检索引擎，不是 OLTP 数据库。
- 原理：写入走 WAL → growing segment（内存可搜）→ flush 成 sealed segment → 建向量索引 → load 到 query node 才高效可查；查询是"索引算法 + 标量过滤"两段合成。
- 边界：无事务、无 JOIN、主键不做唯一约束、维度不可改、一致性是可调水位而非隔离级别。
- 示例：知识库用 collection 存 chunk（id/text/embedding/tenant），租户按 partition key 切；写入链路是"Python 侧 batch insert → flush → 建索引"，不是 MySQL 那种写完即查；需要更新的文档走 upsert 而不是 UPDATE。
