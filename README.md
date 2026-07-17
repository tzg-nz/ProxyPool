# ProxyPool 代理池模块

## 概述

`ProxyPool` 是一个多源代理获取与验证模块，支持从多个代理网站获取代理并自动验证可用性。支持按地区（国内/海外）和协议（http/https）过滤，按权重优先爬取或随机顺序检测。

---

## 主要方法

### `ProxyPool.main()`

获取并验证代理的主入口（类方法）。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `total` | int | None | 需要的可用代理总数，达到即停（None=全量检测） |
| `filter` | tuple | None | 过滤条件，格式 `(region, protocol)`，详见下方 |
| `sources` | list | None | 代理源名称列表，None=使用全部注册源 |
| `useWeight` | bool | True | 是否按权重优先爬取，高权重源先爬先检测 |
| `shuffle` | bool | False | 是否打乱代理检测顺序（与 useWeight 互斥） |
| `maxWorks` | int | 8 | 并发检测线程数 |

**filter 参数格式：**
- `region`: `'china'` / `'abroad'` / `None`（全部）
- `protocol`: `'http'` / `'https'` / `('http', 'https')` / `None`（全部）
- 示例：`('china', 'http')`、`('abroad', 'https')`、`(None, ('http', 'https'))`

**返回：** 可用代理列表，已按延迟升序排列

**示例：**

```python
from ProxyPool import ProxyPool

# 获取5个国内http代理
proxies = ProxyPool.main(total=5, filter=('china', 'http'))

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

获取延迟最低的可用代理，返回可直接传给 `requests` 的 `proxies` 参数（类方法）。

**返回：** `{'http': 'http://ip:port', 'https': 'http://ip:port'}` 或 `None`（无可用代理时）

**示例：**

```python
# 先获取代理池
ProxyPool.main(total=10)

# 取延迟最低的代理，直接传给 requests
proxy = ProxyPool.get_proxy()
resp = requests.get('https://example.com', proxies=proxy, timeout=10)
```

---

### `ProxyPool.export()`

导出可用代理到文件（类方法）。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `fmt` | str | 'txt' | 导出格式，可选：`txt`、`json`、`jsonl` |
| `filepath` | str | None | 导出路径，默认当前目录 `proxies.{fmt}` |

**返回：** 导出内容的字符串

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

| 名称 | 类名 | 权重 |
|------|------|------|
| 站大爷代理 | `ZdyProxyPool` | 3 |
| 六六代理 | `SixSixProxyPool` | 2 |
| 云代理 | `YunProxyPool` | 1 |

---

## 自定义代理源

继承 `ProxyPool.CustomProxySource` 并实现 `fetch` 方法，然后注册：

```python
class MyProxySite(ProxyPool.CustomProxySource):
    NAME = '我的代理网站'
    WEIGHT = 4

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
3. **代理池为空**：`get_proxy()` 在无可用代理时返回 `None`
4. **延迟排序**：`main()` 结束后 `availableProxy` 已按延迟升序排列，`get_proxy()` 返回第一个（最低延迟）
5. **超时设置**：所有HTTP请求默认超时6秒
