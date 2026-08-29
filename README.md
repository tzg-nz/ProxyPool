# ProxyPool 代理池模块

## 概述

`ProxyPool` 是一个多源代理获取与验证模块，支持从多个代理网站获取代理并自动验证可用性。支持按地区（国内/海外）和协议（http/https）过滤，按权重优先爬取或随机顺序检测。

---

## 主要方法

### `ProxyPool.main()`

获取并验证代理的主入口（类方法）。

**签名：**

```python
main(total=None, filter=None, sources=None, useWeight=True, shuffle=False, maxWorks=8)
```

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `total` | int | None | 需要的可用代理总数，达到即停（None=全量检测） |
| `filter` | tuple | None | 过滤条件，格式 `(region, protocol)`，详见下方 |
| `sources` | list | None | 代理源名称列表，None=使用全部注册源 |
| `useWeight` | bool | True | 是否按权重优先爬取，高权重源先爬先检测 |
| `shuffle` | bool | False | 是否打乱代理检测顺序（与 useWeight 互斥，True 时自动关闭权重模式） |
| `maxWorks` | int | 8 | 并发检测线程数 |

**filter 参数格式：**
- `region`: `'china'` / `'abroad'` / `None`（全部）
- `protocol`: `'http'` / `'https'` / `('http', 'https')` / `None`（全部）
- 示例：`('china', 'http')`、`('abroad', 'https')`、`(None, ('http', 'https'))`

**返回值：** `list` —— 可用代理列表（如 `['http://1.2.3.4:8080', ...]`），已按延迟升序排列（最快的在前）。

同时结果也会写入**全局类属性**（与返回值是同一个列表对象，调用后两种方式等价）：

| 类属性 | 说明 |
|--------|------|
| `ProxyPool.availableProxy` | 检测通过的可用代理，按延迟升序 |
| `ProxyPool.allProxy` | 爬取到的原始代理（未检测），去重后 |
| `ProxyPool._proxyLatency` | `dict`，代理 → 检测延迟（ms） |

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

快捷获取代理（类方法）：相当于调用 `main()` 检测出 `testNum` 条可用代理，再取延迟最低（最优）的 `getNum` 条。

**签名：**

```python
get_proxy(getNum=1, testNum=5, filter=None, sources=None, useWeight=True, shuffle=False, maxWorks=8)
```

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `getNum` | int | 1 | 最终获取的代理数量 |
| `testNum` | int | 5 | 检测的可用代理数量（先检测出5条，再从中取最优） |
| `filter` | tuple | None | 过滤条件 `(region, protocol)`，同 `main()` |
| `sources` | list | None | 代理源名称列表，同 `main()` |
| `useWeight` | bool | True | 同 `main()` |
| `shuffle` | bool | False | 同 `main()` |
| `maxWorks` | int | 8 | 同 `main()` |

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

**返回值：** `str` —— 导出内容的字符串；无可用代理时不导出并返回 `None`

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

按协议分组，包含延迟：

```json
{
  "http": [
    {"proxy": "http://1.2.3.4:8080", "latency_ms": 120},
    {"proxy": "http://5.6.7.8:3128", "latency_ms": 350}
  ],
  "https": []
}
```

### `jsonl` 格式

每行一条JSON记录：

```jsonl
{"protocol":"http","proxy":"http://1.2.3.4:8080","latency_ms":120}
{"protocol":"https","proxy":"https://9.10.11.12:443","latency_ms":200}
```

---

## 代理源

当前支持的代理网站：

| 名称 | 类名 | 国内权重 | 国外权重 | 综合权重 |
|------|------|----------|----------|----------|
| 站大爷代理 | `ZdyProxyPool` | 3 | 3 | 3 |
| 六六代理 | `SixSixProxyPool` | 2 | None（无国外） | 2 |
| 云代理 | `YunProxyPool` | 2 | None（无国外） | 2 |
| FreeVPNNode代理 | `FreeVpnNodeProxyPool` | 1 | 1 | 1 |

### 权重机制（国内/国外双权重）

每个代理源配置 `WEIGHT = (国内权重, 国外权重)`（也可写单一数字表示国内外统一）：

- `filter=('china', ...)`：按**国内权重**降序爬取源
- `filter=('abroad', ...)`：按**国外权重**降序爬取源
- 全选（不指定地区）：按**综合权重**（忽略 None 取平均值）降序爬取源
- 权重项为 `None` 表示该源没有对应地区的代理（如六六/云代理只有国内），单选该地区时**自动跳过不爬取**，全选时综合权重忽略该 None 项

**FreeVPNNode代理 说明**（https://cn.freevpnnode.com/free-proxy/）：
- 综合页含国内外代理（国家代码 CN=国内），`region='abroad'` 时自动剔除中国代理；默认爬取前 3 页（每页 30 条），可通过 `ProxyPool.FreeVpnNodeProxyPool.MAXPAGES` 调整
- `region='china'` 时自动改爬中国专属页 `/free-proxy-for-china/`
- 该站还有 socks4/socks5 代理，但代理池框架仅支持 http/https，会自动忽略
- 质量评估：数据量大（约 2.4 万条）且每 3 分钟更新，但实测存活率极低（80 端口条目多为 CDN 伪代理、真代理常被墙），权重设为 1 仅作补充源

**六六代理 说明**（https://www.66daili.com/）：
- **仅国内代理**：官网地区分类只有中国省份，国外权重为 None，`region='abroad'` 时自动跳过此源
- API 无地区/协议过滤参数，每次返回 60 条；实测限流较严（频繁 429"请求次数过多"）

**云代理 说明**（http://www.ip3366.net/）：
- **仅国内代理**：爬取国内高匿页（stype=1），实测 100% 中国 IP，国外权重为 None，`region='abroad'` 时自动跳过此源

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
5. **超时设置**：所有HTTP请求默认超时6秒
