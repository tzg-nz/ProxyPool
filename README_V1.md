# ProxyPool 代理池模块

## 概述

`ProxyPool` 是一个多源代理获取与验证模块，支持从多个代理网站获取代理并自动验证可用性。按地区（国内/海外）和协议（http/https）分类存储。

---

## 主要方法

### `ProxyPool.main()`

获取并验证代理的主入口方法。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `perType` | int | None | 每个分类的目标数量（China/http, China/https, abroad/http, abroad/https 共4个分类） |
| `total` | int | None | 所有分类代理总和目标，达到此数即停止检测 |
| `speed` | bool | True | 快速模式，True=并发检测，False=串行检测 |
| `noStrict` | bool | True | 非严格模式，True=随机顺序遍历代理源，False=严格顺序 |

**返回：**

```python
{
    'China': {'http': [...], 'https': [...]},
    'abroad': {'http': [...], 'https': [...]}
}
```

**示例：**

```python
from utils.proxyPool.ProxyPoolV1 import ProxyPool

# 每个分类各拿5个（最多20个）
proxies = ProxyPool.main(perType=5)

# 总共只要10个，自动分配到各分类
proxies = ProxyPool.main(total=10)

# 每个分类最多3个，总量达到15就停
proxies = ProxyPool.main(perType=3, total=15)

# 不限数量，全量检测
proxies = ProxyPool.main()
```

---

### `ProxyPool.export()`

导出可用代理到文件。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `fmt` | str | 'txt' | 导出格式，可选：`txt`、`json`、`jsonl` |
| `filepath` | str | None | 导出路径，默认为当前工作目录下的 `proxies.{fmt}` |

**返回：** 导出内容的字符串

**示例：**

```python
# 默认导出到当前目录 proxies.txt
ProxyPool.export()

# 导出为JSON格式
ProxyPool.export(fmt='json')

# 自定义路径
ProxyPool.export(fmt='jsonl', filepath='D:\\my_proxies.jsonl')
```

---

## 导出格式说明

### `txt` 格式

每行一个代理地址，自动去重：

```
http://1.2.3.4:8080
http://5.6.7.8:3128
https://9.10.11.12:443
```

### `json` 格式

完整结构化JSON，按region/protocol分类：

```json
{
  "China": {
    "http": ["http://1.2.3.4:8080", "http://5.6.7.8:3128"],
    "https": ["https://9.10.11.12:443"]
  },
  "abroad": {
    "http": [],
    "https": []
  }
}
```

### `jsonl` 格式

每行一条JSON记录，包含region/protocol/proxy字段：

```jsonl
{"region":"China","protocol":"http","proxy":"http://1.2.3.4:8080"}
{"region":"China","protocol":"https","proxy":"https://9.10.11.12:443"}
```

---

## 代理源

当前支持的代理网站：

| 名称 | 类名 | API地址 | protocol_type映射 |
|------|------|---------|-------------------|
| 站大爷代理 | `ZdyProxyPool` | http://www.zdopen.com/FreeProxy/Get/ | 1=http, 2=socks4, 3=socks5, 4=https |
| 六六代理 | `SixSixProxyPool` | http://api.66daili.com/ | protocol参数: http/https |
| 云代理 | `YunProxyPool` | http://www.ip3366.net/free/ | 网页HTML字段 |

---

## 测试网址

代理可用性测试使用以下网址：

- https://icanhazip.com/
- https://myip.ipip.net/
- https://api.ip.sb/ip

---

## 使用流程

```python
# 1. 获取代理
proxies = ProxyPool.main(total=20)

# 2. 使用代理
import requests
proxy = proxies['China']['http'][0]
resp = requests.get('https://example.com', proxies={'http': proxy, 'https': proxy})

# 3. 导出代理
ProxyPool.export(fmt='json')
```

---

## 注意事项

1. **并发竞态**：内部使用线程池并发测试代理，已加锁防止超过目标数量
2. **自动去重**：检测阶段和导出时都会去重
3. **API限制**：部分代理源有请求频率限制，触发429时会打印警告
4. **超时设置**：所有HTTP请求默认超时6秒
5. **总量控制**：设置 `total` 参数后，达到总数即停止检测，自动跳过后续分类
6. **协议字段**：站大爷API返回的 `protocol` 字段不可靠（请求https仍返回http），代码中已用请求的 `protocol_type` 修正
