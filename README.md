# ProxyPool 代理池

Python 代理池模块，支持多代理源并发获取、地区/协议过滤、权重优先、延迟排序。

## 版本说明

| 版本 | 文件 | 特点 |
|------|------|------|
| V1 | `ProxyPoolV1.py` | 按地区+协议自动分类，返回嵌套结构 |
| V2 | `ProxyPoolV2.py` | filter元组过滤、权重优先、延迟排序、随机检测 |

详细对比见 [DIFF.md](DIFF.md)

---

## 快速开始

### V2 使用（推荐）

```python
from ProxyPoolV2 import ProxyPoolV2

# 获取10条国内http代理
proxies = ProxyPoolV2.main(total=10, filter=('china', 'http'))

# 获取5条海外https代理
proxies = ProxyPoolV2.main(total=5, filter=('abroad', 'https'))

# 导出
ProxyPoolV2.export(fmt='json')  # proxies.json
```

### V1 使用

```python
from ProxyPoolV1 import ProxyPool

# 获取代理，按地区+协议分类
result = ProxyPool.main(perType=5, total=20)

# 导出
ProxyPool.export(fmt='json')
```

---

## 自定义代理源

V2 支持添加自定义代理网站：

```python
from ProxyPoolV2 import ProxyPoolV2, CustomProxySource

# 定义自定义代理源
class MyProxySite(CustomProxySource):
    NAME = '我的代理网站'
    WEIGHT = 4  # 权重越高越优先
    
    @classmethod
    def fetch(cls, region=None, protocols=None):
        """
        :param region: 'china'/'abroad'/None
        :param protocols: ['http']/['https']/['http','https']/None
        :return: 代理列表 ['http://ip:port', ...]
        """
        # 你的爬取逻辑
        proxies = []
        # ... 爬取代码 ...
        return proxies

# 注册自定义源
ProxyPoolV2.register_source(MyProxySite)

# 使用
proxies = ProxyPoolV2.main(total=10, sources=['我的代理网站', '站大爷代理'])
```

---

## 内置代理源

| 名称 | 权重 | 地区过滤 | API |
|------|------|---------|-----|
| 站大爷代理 | 3 | 支持 | http://www.zdopen.com/FreeProxy/Get/ |
| 六六代理 | 2 | 不支持 | http://api.66daili.com/ |
| 云代理 | 1 | 不支持 | http://www.ip3366.net/free/ |

---

## 参数说明

### V2 main() 参数

| 参数 | 说明 |
|------|------|
| `total` | 目标代理总数，达到即停 |
| `filter` | `(region, protocol)` 元组，如 `('china', 'http')` |
| `sources` | 代理源列表，如 `['站大爷代理', '我的代理网站']` |
| `useWeight` | 权重优先模式，高权重源先爬 |
| `shuffle` | 随机打乱检测顺序 |
| `maxWorks` | 并发线程数（默认8） |

### filter 元组

| region | protocol | 示例 |
|--------|----------|------|
| `'china'` | `'http'` | `('china', 'http')` 国内http |
| `'abroad'` | `'https'` | `('abroad', 'https')` 海外https |
| `None` | `('http','https')` | `(None, ('http','https'))` 不限地区http+https |

---

## 导出格式

- `txt`：每行一个代理地址
- `json`：按协议分组，含延迟信息
- `jsonl`：每行一条记录，含延迟信息

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `ProxyPoolV2.py` | V2 主代码 |
| `ProxyPoolV1.py` | V1 主代码 |
| `README_V2.md` | V2 详细文档 |
| `README_V1.md` | V1 详细文档 |
| `DIFF.md` | V1/V2 对比文档 |