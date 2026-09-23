# ProxyPool 代理池模块

## 概述

`ProxyPool` 是一个多源代理获取与验证模块，支持从多个代理网站获取代理并自动验证可用性。支持按地区（国内/海外）和协议（http/https）过滤，**按权重逐源「爬一站→测一站→够数即停」**（高权重源先爬先测，达标后面的源不再请求），并可对首轮存活的代理做二次筛选以提升稳定性。

---

## 主要方法

### `ProxyPool.main()`

获取并验证代理的主入口（类方法）。

**签名：**

```python
main(total=None, filter=None, sources=None, maxWorks=8, retest=True)
```

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `total` | int | None | 需要的可用代理总数，达到即停（None=全量检测） |
| `filter` | tuple | None | 过滤条件，格式 `(region, protocol)`，详见下方 |
| `sources` | list | None | 代理源名称列表，None=使用全部注册源 |
| `maxWorks` | int | 8 | 并发检测线程数 |
| `retest` | bool | True | 是否二次筛选：True=对第一次存活的代理再复测一遍，只保留两次都通过的（更稳定，输出分「第一次筛选 / 第二次筛选」两段）；False=单次检测 |

**filter 参数格式：**
- `region`: `'china'` / `'abroad'` / `None`（全部）
- `protocol`: `'http'` / `'https'` / `('http', 'https')` / `None`（全部）
- 示例：`('china', 'http')`、`('abroad', 'https')`、`(None, ('http', 'https'))`
- ⚠️ **必须传元组**，不能传裸字符串：`filter='china'` 会被按字符解析成 `region='c'`、`protocol='h'`，导致匹配不到任何代理

**返回值：** `list` —— 可用代理列表（如 `['http://1.2.3.4:8080', ...]`），已按延迟升序排列（最快的在前）。

同时结果也会写入**全局类属性**（与返回值是同一个列表对象，调用后两种方式等价）：

| 类属性 | 说明 |
|--------|------|
| `ProxyPool.availableProxy` | 检测通过的可用代理，按延迟升序 |
| `ProxyPool.allProxy` | 已爬取源的原始代理（未检测），站内去重 + 跨站 seen 去重；若提前达标停止则仅含已爬的源 |
| `ProxyPool._proxyLatency` | `dict`，代理 → 检测延迟（ms） |
| `ProxyPool._proxySource` | `dict`，代理 → 来源代理源名称 |

每次调用 `main()` 会重置上述状态。`get_proxy()` / `export()` 读取的就是 `ProxyPool.availableProxy`。

**示例：**

```python
from ProxyPool import ProxyPool

# 获取5个国内http代理
proxies = ProxyPool.main(total=5, filter=('china', 'http'))

# 返回值与全局属性是同一个列表
assert proxies is ProxyPool.availableProxy

# 获取10个海外https代理
proxies = ProxyPool.main(total=10, filter=('abroad', 'https'))

# 不限地区，只要http代理
proxies = ProxyPool.main(total=10, filter=(None, 'http'))

# 全量检测，不限条件
proxies = ProxyPool.main()

# 只使用指定代理源
proxies = ProxyPool.main(total=5, sources=['站大爷代理'])
```

---

### `ProxyPool.get_proxy()`

快捷获取代理（类方法）：相当于调用 `main()` 检测出 `testNum` 条可用代理，再取延迟最低（最优）的 `getNum` 条。默认 `retest=True`（对首轮存活代理复测，只留两次都通过的，更稳），不需要可置 `False`。

**签名：**

```python
get_proxy(getNum=1, testNum=5, filter=None, sources=None, maxWorks=8, retest=True)
```

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `getNum` | int | 1 | 最终获取的代理数量 |
| `testNum` | int | 5 | 检测的可用代理数量（先检测出5条，再从中取最优） |
| `filter` | tuple | None | 过滤条件 `(region, protocol)`，同 `main()` |
| `sources` | list | None | 代理源名称列表，同 `main()` |
| `maxWorks` | int | 8 | 同 `main()` |
| `retest` | bool | True | 是否二次筛选，同 `main()`；默认开启对首轮存活代理复测，只留两次都通过的 |

**返回值：**
- `getNum=1`：返回 `{'http': 'http://ip:port', 'https': 'http://ip:port'}`（可直接传给 `requests` 的 `proxies` 参数）；无可用返回 `None`
- `getNum>1`：返回上述字典组成的列表；无可用返回 `[]`

**示例：**

```python
# 检测5条取最优1条
proxy = ProxyPool.get_proxy()
resp = requests.get('https://example.com', proxies=proxy, timeout=10)

# 只要国内http代理，检测出5条后取最优3条
proxies = ProxyPool.get_proxy(getNum=3, testNum=5, filter=('china', 'http'))
```

---

### `ProxyPool.export()`

导出可用代理到文件（类方法）。

**签名：**

```python
export(fmt='txt', filepath=None)
```

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `fmt` | str | 'txt' | 导出格式，可选：`txt`、`json`、`jsonl` |
| `filepath` | str | None | 导出路径，None=当前目录 `proxies.{fmt}` |

**返回值：** 无（`None`）—— 直接将代理写入文件并打印导出条数；无可用代理时不写文件。

**示例：**

```python
ProxyPool.main(total=10)

# 默认导出 txt 到当前目录 proxies.txt
ProxyPool.export()

# 导出 json 到指定路径
ProxyPool.export(fmt='json', filepath=r'D:\out\proxies.json')
```

---

## 导出格式说明

### `txt` 格式

每行一个代理地址，自动去重：

```
http://1.2.3.4:8080
http://5.6.7.8:3128
```

### `json` 格式

按协议分组，包含来源与延迟：

```json
{
  "http": [
    {"source": "站大爷代理", "proxy": "http://1.2.3.4:8080", "latency_ms": 120},
    {"source": "proxyfreeonly代理", "proxy": "http://5.6.7.8:3128", "latency_ms": 350}
  ],
  "https": []
}
```

### `jsonl` 格式

每行一条JSON记录：

```jsonl
{"source":"站大爷代理","protocol":"http","proxy":"http://1.2.3.4:8080","latency_ms":120}
{"source":"站大爷代理","protocol":"https","proxy":"https://9.10.11.12:443","latency_ms":200}
```

---

## 代理源

当前支持的代理网站：

| 名称 | 类名 | 国内权重 | 国外权重 | 综合权重 |
|------|------|----------|----------|----------|
| 站大爷代理 | `ZdyProxyPool` | 3 | 3 | 3 |
| proxyfreeonly代理 | `ProxyFreeOnlyProxyPool` | 2 | 1 | 1.5 |

### 权重机制（国内/国外双权重）

每个代理源配置 `WEIGHT = (国内权重, 国外权重)`（也可写单一数字表示国内外统一）：

- `filter=('china', ...)`：按**国内权重**降序爬取源
- `filter=('abroad', ...)`：按**国外权重**降序爬取源
- 全选（不指定地区）：按**综合权重**（忽略 None 取平均值）降序爬取源
- 权重项为 `None` 表示该源没有对应地区的代理（如某源只有国内），单选该地区时**自动跳过不爬取**，全选时综合权重忽略该 None 项
- **获取策略**：不再一次性把所有源全量爬完，而是按上述顺序**逐源「爬→测」**，累计可用数达到 `total` 立即停止，后续源连请求都不发；`total=None`（全量）则会依次爬测所有源。去重仅在单站内 + 一个跨站 `seen` 集合（避免同一代理重复检测），不做全局预去重

**站大爷代理 说明**（http://www.zdaye.com/）：
- **国内外均有**：走免费 API `http://www.zdopen.com/FreeProxy/Get/`，`count` 上限 100（超出仍按 100 返回），`dalu` 1=大陆/0=海外，`return_type=3` 取 JSON；文档要求调用间隔 ≥1 秒（否则 `code=12002`），已内置 1.1s 节流
- **协议以每条返回的 `protocol` 字段为准**：免费池 `protocol_type` 不可靠（传 4=https 返回的条目 `protocol` 仍是 http），故不按请求参数硬贴标签，`socks` 及非本次请求协议本地剔除；因此请求 https 时若池内无真实 https 会返回 0（`code=12009` 静默跳过）而非错标成 http
- **提量靠 `level_type` 分桶并集**：单查固定只回 100 条且重复调用不轮换（第 2 次起全是旧数据），故按匿名等级 `LEVELS=(1,2,3,4,5)`（高匿/普匿/匿名/透明/未知）逐桶请求再并集，各桶独立 ≤100；实测国内 http 约 204 条、海外 http 约 302 条（单查仅 100）。想关闭分桶把 `LEVELS` 设为 `(None,)` 即可
- **本源无真实 https**：国内/海外池的 https 均返回 0，只能提供 http；需要 https 代理请依赖 proxyfreeonly

**proxyfreeonly代理 说明**（https://proxyfreeonly.com/）：
- **国内外均有**：走前端数据接口 `https://proxyfreeonly.com/api/data/proxy-list`，`GET ?page=1&limit=200&locale=en&where={"country":"china","protocols":"http"}`，返回 `{"items":[...],"totalItems":N}`，**裸请求即可（无需 cookie / CF 盾）**
- **`where.country`（用 slug，如 `china`/`united-states`）、`where.protocols` 与 `limit`/`page` 全部服务端生效**，可分页只取需要的小量（比全量接口 `api/free-proxy-list` 高效得多）：`china` 约 219(http)/21(https) 条一次拉完
- `region='china'` 传 `where.country='china'`；`abroad`/全选只按 `protocols` 请求全国家，再本地排除 CN 与噪声国家 `NOISE`（默认 `LU`，一家占 1.3 万条机房代理）；每协议最多翻 `MAX_PAGES`（默认 5）页 × `PAGE_LIMIT`（默认 200）
- 质量：CN http/https 本机实测 https 隧道存活约 17%、明文约 24%，延迟亚秒，是国内免费源里较好的一档；全球池被 LU 机房代理稀释、跨境延迟 5~10s 且存活极低，故国外权重下调为 1

---

## 自定义代理源

继承 `ProxyPool.CustomProxySource` 并实现 `fetch` 方法，然后注册：

```python
class MyProxySite(ProxyPool.CustomProxySource):
    NAME = '我的代理网站'
    WEIGHT = (4, 3)  # (国内权重, 国外权重)，综合权重=平均值；某项None表示没有该地区代理
                     # 也可写单一数字表示国内外统一

    @classmethod
    def fetch(cls, region=None, protocols=None):
        proxies = []
        # 爬取逻辑 ...
        return proxies

ProxyPool.register_source(MyProxySite)
```

---

## 测试网址

- https://icanhazip.com/
- https://myip.ipip.net/
- https://api.ip.sb/ip

---

## 注意事项

1. **并发检测**：默认8线程并发，`maxWorks` 参数可调整
2. **自动去重**：检测和导出时均自动去重
3. **代理池为空**：`get_proxy()` 在无可用代理时，`getNum=1` 返回 `None`、`getNum>1` 返回 `[]`
4. **延迟排序**：`main()` 结束后 `availableProxy` 已按延迟升序排列，`get_proxy()` 返回其中延迟最低（最优）的一条或多条
5. **超时设置**：代理可用性检测请求超时 6 秒；各代理源拉取列表的超时不同（站大爷 10s、proxyfreeonly 25s，响应较大）
