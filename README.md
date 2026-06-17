# ProxyPool 代理池模块

## 概述

`ProxyPool` 是一个多源代理获取与验证模块，支持地区/协议过滤、权重优先、延迟排序、随机检测。

---

## 主要方法

### `ProxyPool.main()`

获取并验证代理的主入口。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `total` | int | None | 需要的可用代理总数，达到即停（None=全量检测） |
| `filter` | tuple | None | 过滤条件元组 `(region, protocol)`，见下方详解 |
| `sources` | list | None | 代理源名称列表，如 `['站大爷代理', '云代理']`，None=使用全部 |
| `useWeight` | bool | True | 是否按权重优先爬取，True=高权重源先爬先检测 |
| `shuffle` | bool | False | 是否打乱代理顺序再检测，True=随机顺序检测 |
| `maxWorks` | int | 8 | 并发检测线程数 |

**返回：** 可用代理列表 `['http://ip:port', ...]`（按延迟排序，最快在前）

#### filter 元组详解

| 位置 | 值 | 说明 |
|------|-----|------|
| region | `'china'` | 国内代理 |
| region | `'abroad'` | 海外代理 |
| region | `None` | 不限地区 |
| protocol | `'http'` | 只要http |
| protocol | `'https'` | 只要https |
| protocol | `('http', 'https')` | http+https |
| protocol | `None` | 不限协议 |

> 注意：地区过滤仅站大爷代理支持（API有dalu参数），六六代理和云代理无地区参数会忽略此过滤。

**示例：**

```python
from ProxyPool import ProxyPool

# 获取10条国内http代理
proxies = ProxyPool.main(total=10, filter=('china', 'http'))

# 获取5条海外https代理
proxies = ProxyPool.main(total=5, filter=('abroad', 'https'))

# 获取20条国内http+https代理
proxies = ProxyPool.main(total=20, filter=('china', ('http', 'https')))

# 不限地区，只要http代理
proxies = ProxyPool.main(total=10, filter=(None, 'http'))

# 全量检测，不限地区不限协议
proxies = ProxyPool.main()
```

---

### `ProxyPool.export()`

导出可用代理到文件。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `fmt` | str | 'txt' | 导出格式：`txt`/`json`/`jsonl` |
| `filepath` | str | None | 导出路径，默认当前目录 `proxies.{fmt}` |

**示例：**

```python
ProxyPool.export()                    # proxies.txt
ProxyPool.export(fmt='json')          # proxies.json（含延迟信息）
ProxyPool.export(fmt='jsonl', filepath='D:\\proxies.jsonl')
```

---

## 导出格式

### `txt`

每行一个代理地址，自动去重，按延迟排序：

```
http://5.6.7.8:3128
http://1.2.3.4:8080
https://9.10.11.12:443
```

### `json`

按协议分组，包含延迟信息：

```json
{
  "http": [
    {"proxy": "http://5.6.7.8:3128", "latency_ms": 120},
    {"proxy": "http://1.2.3.4:8080", "latency_ms": 350}
  ],
  "https": [
    {"proxy": "https://9.10.11.12:443", "latency_ms": 450}
  ]
}
```

### `jsonl`

每行一条记录，包含延迟信息：

```jsonl
{"protocol":"http","proxy":"http://5.6.7.8:3128","latency_ms":120}
{"protocol":"http","proxy":"http://1.2.3.4:8080","latency_ms":350}
{"protocol":"https","proxy":"https://9.10.11.12:443","latency_ms":450}
```

---

## 代理源

| 名称 | 权重 | API | 地区过滤 |
|------|------|-----|---------|
| 站大爷代理 | 3（最高） | http://www.zdopen.com/FreeProxy/Get/ | 支持（dalu参数） |
| 六六代理 | 2 | http://api.66daili.com/ | 不支持 |
| 云代理 | 1 | http://www.ip3366.net/free/ | 不支持 |

---

## 自定义代理源

支持添加自定义代理网站：

```python
from ProxyPool import ProxyPool

# 定义自定义代理源
class MyProxySite(ProxyPool.CustomProxySource):
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
ProxyPool.register_source(MyProxySite)

# 使用
proxies = ProxyPool.main(total=10, sources=['我的代理网站', '站大爷代理'])
```

---

## 运行流程

```
1. 验证测速网站 → 移除不可用的，全部不可用则报错
2. 检查参数互斥 → shuffle=True 时自动关闭 useWeight
3. 获取代理 → 权重模式：按权重串行获取；非权重模式：并发获取
4. 排序代理 → shuffle=True：随机打乱；useWeight=True：按权重顺序；否则按并发完成顺序
5. 并发检测代理 → http/https混合检测，实时显示进度和延迟
6. 按延迟排序 → 最快的排最前
7. 返回可用代理列表
```

**参数互斥说明：**

| useWeight | shuffle | 代理检测顺序 |
|-----------|---------|-------------|
| True | False | 按权重排序（站大爷→六六→云代理） |
| False | False | 按并发完成顺序（不确定，取决于响应速度） |
| False | True | 随机打乱 |
| True | True | 自动关闭权重，随机打乱（两者冲突，shuffle优先） |

---

## 注意事项

1. **测速网站验证**：开局自动验证，不可用的自动移除，全部不可用则抛异常
2. **并发安全**：使用线程锁防止竞态条件，不会超过目标数量
3. **自动去重**：获取阶段和检测阶段都会去重
4. **协议修复**：不信任API返回的protocol字段，用请求时指定的协议类型生成代理地址
5. **延迟排序**：可用代理按延迟从快到慢排序，结果和导出都按此顺序
6. **权重优先**：权重高的代理源先爬取先检测，更容易快速达标
7. **地区过滤**：仅站大爷代理支持地区过滤，其他源会忽略此参数
8. **参数互斥**：`shuffle=True` 时自动关闭 `useWeight`，因为打乱顺序后权重排序无意义