# ProxyPool vs ProxyPoolV2 对比文档

## 架构差异

| 维度 | ProxyPool (V1) | ProxyPoolV2 |
|------|----------------|-------------|
| 数据结构 | 嵌套dict：`{region: {protocol: [proxy]}}` | 扁平list：`['http://ip:port', ...]` |
| 分类维度 | 按地区+协议4分类（China/http, China/https, abroad/http, abroad/https） | 通过filter元组过滤，结果扁平存储 |
| 代理源注册 | `_WEBURL` 列表 + `eval()` 动态创建 | `_SOURCES` 字典注册表，直接调用类方法 |
| 代理源获取 | 实例方法 `getAllProxys()`，内部嵌套多层函数 | 静态方法 `fetch(region, protocols)`，简洁统一 |
| 线程安全 | 无锁 | `threading.Lock()` 保护共享数据 |

---

## 功能对比

| 功能 | ProxyPool (V1) | ProxyPoolV2 |
|------|----------------|-------------|
| 地区过滤 | 自动按地区分类存储 | `filter=('china', ...)` 参数过滤 |
| 协议过滤 | 无，http/https全量获取 | `filter=(..., 'http')` 参数过滤 |
| https bug | API返回protocol不可靠，https分类会混入http | 已修复，用请求时指定的协议类型 |
| 代理源选择 | 无，只能全量使用 | `sources=['站大爷代理', '云代理']` 指定 |
| 权重优先 | 无 | `useWeight=True`，高权重源先爬先检测 |
| 延迟排序 | 无 | 按延迟从快到慢排序 |
| 延迟信息 | 不记录 | `_proxyLatency` 记录每条代理延迟 |
| 测速网站验证 | 开局验证，但未知错误直接抛异常 | 开局验证，不可用的移除，全部不可用才报错 |
| 导出含延迟 | 不含 | json/jsonl 格式包含 `latency_ms` 字段 |

---

## 参数对比

### main() 方法

| 参数 | V1 | V2 | 说明 |
|------|----|----|------|
| `perType` | 有 | 无 | V1：每个分类的目标数量 |
| `total` | 有 | 有 | V1：4分类总和；V2：全局总数 |
| `speed` | 有 | 无 | V1：快速/串行模式 |
| `noStrict` | 有 | 无 | V1：非严格/严格模式 |
| `filter` | 无 | 有 | V2：`(region, protocol)` 元组过滤 |
| `sources` | 无 | 有 | V2：代理源选择 |
| `useWeight` | 无 | 有 | V2：权重优先模式 |
| `shuffle` | 无 | 有 | V2：打乱代理检测顺序 |
| `maxWorks` | 无 | 有 | V2：并发线程数（默认8） |

### filter 元组格式（V2新增）

```python
filter = (region, protocol)
```

| 位置 | 值 | 说明 |
|------|-----|------|
| region | `'china'` | 国内代理 |
| region | `'abroad'` | 海外代理 |
| region | `None` | 不限地区 |
| protocol | `'http'` | 只要http |
| protocol | `'https'` | 只要https |
| protocol | `('http', 'https')` | http+https |
| protocol | `None` | 不限协议 |

### export() 方法

| 参数 | V1 | V2 | 说明 |
|------|----|----|------|
| `fmt` | txt/json/jsonl | txt/json/jsonl | 相同 |
| `filepath` | 默认当前目录 | 默认当前目录 | 相同 |
| 延迟信息 | 不含 | json/jsonl含`latency_ms` | V2新增 |

---

## 返回值对比

### V1 返回值

```python
{
    'China': {
        'http': ['http://1.2.3.4:8080', ...],
        'https': ['https://5.6.7.8:443', ...]
    },
    'abroad': {
        'http': ['http://9.10.11.12:3128', ...],
        'https': ['https://13.14.15.16:443', ...]
    }
}
```

### V2 返回值

```python
['http://1.2.3.4:8080', 'https://5.6.7.8:443', 'http://9.10.11.12:3128', ...]
# 按延迟排序，最快在前
```

---

## 导出格式对比

### json 格式

**V1：** 按地区+协议分组
```json
{
  "China": {
    "http": ["http://1.2.3.4:8080"],
    "https": ["https://5.6.7.8:443"]
  },
  "abroad": {
    "http": [],
    "https": []
  }
}
```

**V2：** 按协议分组，含延迟
```json
{
  "http": [
    {"proxy": "http://1.2.3.4:8080", "latency_ms": 120}
  ],
  "https": [
    {"proxy": "https://5.6.7.8:443", "latency_ms": 450}
  ]
}
```

### jsonl 格式

**V1：** 含region字段
```jsonl
{"region":"China","protocol":"http","proxy":"http://1.2.3.4:8080"}
```

**V2：** 含延迟，无region
```jsonl
{"protocol":"http","proxy":"http://1.2.3.4:8080","latency_ms":120}
```

---

## 检测流程对比

### V1 流程

```
1. 验证代理网站+测试网站可用性
2. 逐个代理源串行获取 → getAllProxys()
3. 串行检测：先China/http → China/https → abroad/http → abroad/https
4. 每个分类独立计数，达到perType即停
5. 分类间检查total，达标跳过后续
```

### V2 流程

```
1. 验证测速网站可用性
2. 检查参数互斥：shuffle=True 时自动关闭 useWeight
3. 获取代理：权重模式串行 / 非权重模式并发
4. 排序代理：shuffle随机打乱 / useWeight按权重顺序 / 否则按并发完成顺序
5. 并发检测：http/https混合，全局计数
6. 达到total即停
7. 按延迟排序返回
```

---

## 参数互斥（V2）

`shuffle` 与 `useWeight` 互斥，同时为 True 时 shuffle 优先，自动关闭权重模式：

| useWeight | shuffle | 代理检测顺序 |
|-----------|---------|-------------|
| True | False | 按权重排序（站大爷→六六→云代理） |
| False | False | 按并发完成顺序（不确定） |
| False | True | 随机打乱 |
| True | True | 自动关闭权重，随机打乱 |

---

## 代理源权重（V2新增）

| 代理源 | 权重 | 地区过滤 | 说明 |
|--------|------|---------|------|
| 站大爷代理 | 3 | 支持 | 最高优先，代理数量多、质量好，API有dalu参数 |
| 六六代理 | 2 | 不支持 | 中等优先，API无地区参数 |
| 云代理 | 1 | 不支持 | 最低优先，需要爬网页解析 |

权重模式下：站大爷的代理排在列表前面，优先检测，更容易快速达标。

---

## 选用建议

| 场景 | 推荐 | 原因 |
|------|------|------|
| 需要区分国内/海外代理 | V1 或 V2 | V1自动按地区分类；V2用filter过滤 |
| 只需要最快的代理 | V2 | V2按延迟排序 |
| 需要指定地区+协议组合 | V2 | V2用filter元组灵活组合 |
| 需要选择代理源 | V2 | V2有sources参数 |
| 简单快速获取代理 | V2 | V2参数少，用法简单 |
| 需要详细分类数据 | V1 | V1返回结构化嵌套数据 |
