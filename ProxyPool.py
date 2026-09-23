import requests
import random
import time
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


class ProxyPool:
    SUPPORTFORMAT = ['txt', 'json', 'jsonl']
    # 代理源注册表：名称 -> 类
    _SOURCES = {}

    # ==================== 自定义代理源基类 ====================

    class CustomProxySource:
        """
        自定义代理源基类，继承此类并实现 fetch 方法

        示例：
        class MyProxySite(ProxyPool.CustomProxySource):
            NAME = '我的代理网站'
            WEIGHT = (4, 3)  # (国内权重, 国外权重)，综合权重=两者平均；某项None表示没有对应地区代理
                             # 也可写单一数字表示国内外统一权重

            @classmethod
            def fetch(cls, region=None, protocols=None):
                # 你的爬取逻辑
                proxies = []
                # ... 爬取代码 ...
                return proxies  # ['http://ip:port', ...]

        ProxyPool.register_source(MyProxySite)
        """
        NAME = 'CustomProxySource'
        WEIGHT = 0

        @classmethod
        def fetch(cls, region=None, protocols=None):
            """
            获取代理列表
            
            :param region: 'china'/'abroad'/None (地区过滤)
            :param protocols: ['http']/['https']/['http','https']/None (协议过滤)
            :return: 代理列表 ['http://ip:port', 'https://ip:port', ...]
            """
            raise NotImplementedError('请实现 fetch 方法')

    @classmethod
    def register_source(cls, source_class):
        """
        注册自定义代理源

        :param source_class: 继承 CustomProxySource 的类
        """
        name = getattr(source_class, 'NAME', source_class.__name__)
        cls._SOURCES[name] = source_class
        w = getattr(source_class, 'WEIGHT', 0)
        if isinstance(w, (tuple, list)) and len(w) >= 2:
            cn = 'None' if w[0] is None else w[0]
            ab = 'None' if w[1] is None else w[1]
            # 综合权重：忽略None项取平均
            vals = [x for x in w if isinstance(x, (int, float))]
            total = sum(vals) / len(vals) if vals else 0
            wDesc = f'国内 {cn} / 国外 {ab} / 综合 {total:g}'
        else:
            wDesc = f'统一 {w}'
        print(f'✅ 已注册代理源：{name} ({wDesc})')

    @classmethod
    def _getWeight(cls, sourceName, region=None):
        """
        获取代理源在指定地区下的权重

        WEIGHT 支持两种形式：
            数字：国内外统一权重
            (国内权重, 国外权重) 元组：单选地区取对应权重，None(全选)取综合权重=两者平均
            元组中某项为None表示该源没有对应地区的代理，单选该地区时此源会被跳过不爬取

        :param region: 'china'/'abroad'/None
        :return: 权重数字或None(该源没有指定地区的代理)
        """
        w = getattr(cls._SOURCES[sourceName], 'WEIGHT', 0)
        if isinstance(w, (tuple, list)) and len(w) >= 2:
            if region == 'china':
                return w[0]
            if region == 'abroad':
                return w[1]
            # 综合权重：忽略None项取平均
            vals = [x for x in w if isinstance(x, (int, float))]
            return sum(vals) / len(vals) if vals else 0
        return w

    allProxy = []
    availableProxy = []
    _proxyLatency = {}  # proxy -> latency_ms
    _proxySource = {}  # proxy -> 来源代理源名称
    _lock = threading.Lock()

    _TEST_URLS_POOL = ['https://myip.ipip.net/', 'https://icanhazip.com/', 'https://api.ip.sb/ip']  # 候选测速网站
    _TEST_URLS = _TEST_URLS_POOL  # 当前生效的测速网站（_checkTestUrls 会收窄为其中第一个可用的）

    _UALIST = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    ]

    def __init__(self, total=None, filter=None, sources=None):
        """
        :param total: 需要的可用代理总数，达到即停
        :param filter: 过滤条件元组 (region, protocol)
            region: 'china'/'abroad'/None(全部)
            protocol: 'http'/'https'/('http','https')/None(全部)
            示例：('china', 'http')  ('abroad', ('http', 'https'))  (None, 'https')
        :param sources: 代理源名称列表，None=使用全部
        """
        self.total = total
        self.sources = sources
        # 解析filter元组
        if filter is None:
            self.region = None
            self.protocols = None
        else:
            self.region = filter[0]  # 'china'/'abroad'/None
            proto = filter[1] if len(filter) > 1 else None
            if proto is None:
                self.protocols = None
            elif isinstance(proto, (list, tuple)):
                self.protocols = list(proto)
            else:
                self.protocols = [proto]

    # ==================== 测速网站验证 ====================

    @classmethod
    def _checkTestUrls(cls):
        """从候选池顶部往下测，逐个输出可用情况，命中第一个可用即作为本次唯一测速站点并单独提示（不再逐个全测）"""
        for url in cls._TEST_URLS_POOL:
            try:
                resp = requests.get(url, timeout=6)
                if resp.ok:
                    print(f'✅测速网站可用：{url}\n')
                    cls._TEST_URLS = [url]
                    print(f'🚀当前测速网站：{url}')
                    return
                print(f'❌测速网站不可用：{url} (状态码 {resp.status_code})')
            except Exception as e:
                print(f'❌测速网站不可用：{url} ({type(e).__name__})')
        raise Exception('⚠️所有测速网站均不可用，无法检测代理')

    # ==================== 代理获取 ====================

    def _fetchFromSource(self, sourceName):
        """从单个代理源获取原始代理列表"""
        if sourceName not in self._SOURCES:
            print(f'❌未知代理源：{sourceName}')
            return []
        source = self._SOURCES[sourceName]
        try:
            proxies = source.fetch(region=self.region, protocols=self.protocols)
            print(f'[{sourceName}] 获取到 {len(proxies)} 条代理')
            return proxies
        except Exception as e:
            print(f'[{sourceName}] 获取失败：{e}')
            return []

    def _resolveSources(self):
        """按权重降序解析待用代理源名称列表（含跳过无该地区的源），不在此爬取"""
        sourceNames = self.sources or list(self._SOURCES.keys())
        # 单选地区时，跳过该地区权重为None的源（该源没有此地区代理，爬了也是浪费请求）
        if self.region is not None:
            skipped = [n for n in sourceNames if ProxyPool._getWeight(n, self.region) is None]
            for name in skipped:
                print(f'⏭️ [跳过] {name}：没有{"国外" if self.region == "abroad" else "国内"}代理')
            sourceNames = [n for n in sourceNames if n not in skipped]
            if not sourceNames:
                print(f'⚠️ 指定的代理源均无{"国外" if self.region == "abroad" else "国内"}代理，无法获取')
                return []

        # 按权重降序排列，高权重优先爬取（单选地区用对应地区权重，全选用综合权重）
        sortedSources = sorted(
            sourceNames,
            key=lambda name: ProxyPool._getWeight(name, self.region),
            reverse=True
        )
        weightDesc = '综合' if self.region is None else ('国内' if self.region == 'china' else '国外')
        weightStr = ' > '.join(f'{s}({ProxyPool._getWeight(s, self.region):g})' for s in sortedSources)
        print(f'权重模式({weightDesc}权重优先)：{weightStr}')
        return sortedSources

    # ==================== 代理检测 ====================

    def _testProxy(self, proxy, target):
        """测试单个代理是否可用，返回 (proxy, elapsed_ms) 或 (None, 0)"""
        ipPort = proxy[proxy.find('://') + 3:]
        proxy_url = f"http://{ipPort}"
        proxies = {'http': proxy_url, 'https': proxy_url}
        for testUrl in self._TEST_URLS:
            try:
                response = requests.get(testUrl, proxies=proxies, timeout=6)
                if response.ok:
                    # 用 requests 内置的 response.elapsed（请求发出到响应内容下载的耗时）
                    return (proxy, response.elapsed.total_seconds() * 1000)
                return (None, 0)
            except Exception:
                return (None, 0)
        return (None, 0)

    def _checkProxies(self, sourceProxyMap, maxWorks=8):
        """并发检测 sourceProxyMap 内的代理，累计达到 total 即停
        :param sourceProxyMap: 有序的 {源名: [代理,...]}，每源开始处打印一次网站名
        """
        total_count = sum(len(v) for v in sourceProxyMap.values())
        if total_count == 0:
            return

        target = self.total or total_count
        checked = [0]
        available = ProxyPool.availableProxy

        for srcName, proxyList in sourceProxyMap.items():
            if len(available) >= target:
                break
            if not proxyList:
                continue
            # 按权重逐源检测，故只在每源开始处标明网站，后续每行不再重复来源
            print(f'\n🌐 {srcName}（{len(proxyList)} 条）')
            proxyIter = iter(proxyList)
            with ThreadPoolExecutor(max_workers=maxWorks) as executor:
                futures = []
                while True:
                    # 提交任务
                    while len(futures) < maxWorks:
                        try:
                            proxy = next(proxyIter)
                            futures.append(executor.submit(self._testProxy, proxy, target))
                        except StopIteration:
                            break

                    if not futures:
                        break

                    # 处理结果
                    for future in as_completed(futures):
                        futures.remove(future)
                        try:
                            res, elapsed = future.result()
                            with ProxyPool._lock:
                                checked[0] += 1
                                if res is not None:
                                    if len(available) >= target:
                                        return
                                    if res not in available:
                                        available.append(res)
                                        ProxyPool._proxyLatency[res] = elapsed
                                        print(
                                            f'✅ {res} ({elapsed:.0f}ms) | 进度 {checked[0]}/{total_count} | 可用 {len(available)}/{target}')
                                        if len(available) >= target:
                                            print(f'\n✅已达目标数量 {target}')
                                            return
                                    else:
                                        print(
                                            f'⚠️ {res} 重复 | 进度 {checked[0]}/{total_count} | 可用 {len(available)}/{target}')
                                else:
                                    print(f'❌ 无效 | 进度 {checked[0]}/{total_count} | 可用 {len(available)}/{target}')
                        except Exception:
                            continue

    # ==================== 主入口 ====================

    @classmethod
    def main(cls, total=None, filter=None, sources=None, maxWorks=8, retest=True):
        """
        获取并验证代理（按权重逐源「爬→测」，累计达到 total 即停，达标后面的源不再爬取）

        :param total: 需要的可用代理总数，达到即停（None=全量检测）
        :param filter: 过滤条件元组 (region, protocol)
            region: 'china'/'abroad'/None(全部)
            protocol: 'http'/'https'/('http','https')/None(全部)
            示例：('china', 'http')  ('abroad', ('http', 'https'))  (None, 'https')
        :param sources: 代理源名称列表，如 ['站大爷代理']，None=使用全部
        :param maxWorks: 并发检测线程数
        :param retest: 是否二次筛选，True=对第一次存活的代理再复测一遍，只保留两次都通过的（更稳，输出分"第一次筛选/第二次筛选"）；False=单次检测
        :return: 可用代理列表
        """
        # 重置
        cls.allProxy = []
        cls.availableProxy = []
        cls._proxyLatency = {}
        cls._proxySource = {}

        instance = cls(total, filter, sources)

        # 0. 验证测速网站
        print('=' * 80)
        print('验证测速网站可用性...')
        print('=' * 80)
        cls._checkTestUrls()

        # 1. 解析代理源顺序（按权重降序，跳过无该地区的源）——此处不预爬
        region_str = instance.region or '全部'
        proto_str = ','.join(instance.protocols) if instance.protocols else '全部'
        print('=' * 80)
        print(
            f'地区：{region_str} | 协议：{proto_str} | 代理源：{sources or "全部"} | 目标数量：{total or "不限"} | 二次筛选：{"开启" if retest else "关闭"}')
        print('=' * 80)
        sortedSources = instance._resolveSources()

        # 2. 第一次筛选：按权重逐源"爬→测"，够数即停（达标的后续源不再爬取）
        if retest:
            print('\n' + '=' * 80)
            print('第一次筛选'.center(80))
            print('=' * 80)
        else:
            print('\n开始逐源获取并检测代理...')
            print('=' * 80)
        available = cls.availableProxy
        seen = set()
        for name in sortedSources:
            if total and len(available) >= total:
                break
            proxies = instance._fetchFromSource(name)
            batch = []
            for p in proxies:
                if p not in seen:
                    seen.add(p)
                    cls._proxySource[p] = name
                    batch.append(p)
            cls.allProxy.extend(batch)
            if not batch:
                continue
            instance._checkProxies({name: batch}, maxWorks)

        # 3. 二次筛选：对第一次存活的代理复测，只保留两次都通过的（剔除抖动/偶发可用）
        if retest and cls.availableProxy:
            survivors = list(cls.availableProxy)
            reMap = {}
            for p in survivors:
                reMap.setdefault(cls._proxySource.get(p, '?'), []).append(p)
            print('\n' + '=' * 80)
            print(f'第二次筛选（对第一次存活的 {len(survivors)} 条复测）'.center(80))
            print('=' * 80)
            # 重置可用与延迟，复测结果覆盖；不设 target 上限，把存活项全部复测完
            cls.availableProxy = []
            cls._proxyLatency = {}
            savedTotal = instance.total
            instance.total = None
            instance._checkProxies(reMap, maxWorks)
            instance.total = savedTotal

        # 4. 按延迟排序，最快的在前
        cls.availableProxy.sort(key=lambda p: cls._proxyLatency.get(p, float('inf')))

        print(f'\n{"=" * 80}')
        print(f'检测完成，共 {len(cls.availableProxy)} 条可用代理（按延迟排序）')
        for i, p in enumerate(cls.availableProxy, 1):
            latency = cls._proxyLatency.get(p, 0)
            src = cls._proxySource.get(p, '?')
            print(f'  {i}. [{src}] {p} ({latency:.0f}ms)')
        print('=' * 80)
        return cls.availableProxy

    # ==================== 导出 ====================

    @classmethod
    def export(cls, fmt='jsonl', filepath=None):
        if fmt not in cls.SUPPORTFORMAT:
            raise ValueError(f'不支持的导出格式: {fmt}，可选: {cls.SUPPORTFORMAT}')

        proxies = cls.availableProxy
        if not proxies:
            print('⚠️没有可用代理，请先调用 main() 获取')
            return

        seen = set()
        if fmt == 'txt':
            lines = [p for p in proxies if not (p in seen or seen.add(p))]
            content = '\n'.join(lines)
        elif fmt == 'json':
            # 按协议分组，包含来源与延迟
            grouped = {'http': [], 'https': []}
            for p in proxies:
                proto = 'https' if p.startswith('https://') else 'http'
                if p not in seen:
                    seen.add(p)
                    grouped[proto].append({
                        'source': cls._proxySource.get(p, ''),
                        'proxy': p,
                        'latency_ms': round(cls._proxyLatency.get(p, 0))
                    })
            content = json.dumps(grouped, ensure_ascii=False, indent=2)
        elif fmt == 'jsonl':
            lines = []
            for p in proxies:
                if p not in seen:
                    seen.add(p)
                    proto = 'https' if p.startswith('https://') else 'http'
                    lines.append(json.dumps({
                        'source': cls._proxySource.get(p, ''),
                        'protocol': proto,
                        'proxy': p,
                        'latency_ms': round(cls._proxyLatency.get(p, 0))
                    }, ensure_ascii=False))
            content = '\n'.join(lines)

        if filepath is None:
            filepath = os.path.join(os.getcwd(), f'proxies.{fmt}')

        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'✅已导出 {len(seen)} 条不重复代理到 {filepath}')

    # ==================== 读取文件并测速 ====================

    @staticmethod
    def _ensure_scheme(proxy):
        """补全协议前缀；无 :// 视为 http，返回去空白的代理串（非法则返回 ''）"""
        proxy = (proxy or '').strip()
        if not proxy:
            return ''
        if '://' not in proxy:
            proxy = f'http://{proxy}'
        return proxy

    @classmethod
    def check_file(cls, filepath=None, total=None, maxWorks=8):
        """
        读取已导出的 jsonl 代理文件并逐个测速（单次检测，不做二次筛选）。
        结果写入全局状态（availableProxy / _proxyLatency / _proxySource），
        因此测完后照常可调用 export() 重新导出。

        :param filepath: 代理 jsonl 文件路径，None=当前目录 proxies.jsonl
        :param total: 需要的可用代理数量，达到即停；None=全部检测
        :param maxWorks: 并发检测线程数
        :return: 可用代理列表（按延迟升序）

        jsonl 每行形如 {"source","protocol","proxy","latency_ms"}
        """
        if filepath is None:
            filepath = os.path.join(os.getcwd(), 'proxies.jsonl')
        if not os.path.isfile(filepath):
            print(f'❌文件不存在：{filepath}')
            return []

        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()

        # 解析为 (proxy, source) 列表
        pairs = []
        try:
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                pairs.append((cls._ensure_scheme(obj.get('proxy', '')), obj.get('source', '')))
        except Exception as e:
            print(f'❌解析文件失败（jsonl）：{e}')
            return []

        # 重置状态并按来源分组去重
        cls.allProxy = []
        cls.availableProxy = []
        cls._proxyLatency = {}
        cls._proxySource = {}
        seen = set()
        sourceMap = {}
        for proxy, src in pairs:
            if not proxy or proxy in seen:
                continue
            seen.add(proxy)
            name = src or '文件导入'
            cls.allProxy.append(proxy)
            cls._proxySource[proxy] = name
            sourceMap.setdefault(name, []).append(proxy)

        print('=' * 80)
        print(f'读取 {filepath}：解析到 {len(seen)} 条不重复代理，开始测速（目标 {total or "全部"}）')
        print('=' * 80)
        if not seen:
            print('⚠️文件无有效代理')
            return []

        cls._checkTestUrls()
        instance = cls(total)
        instance._checkProxies(sourceMap, maxWorks)

        # 按延迟排序，最快的在前
        cls.availableProxy.sort(key=lambda p: cls._proxyLatency.get(p, float('inf')))
        print(f'\n{"=" * 80}')
        print(f'测速完成，共 {len(cls.availableProxy)} 条可用代理（按延迟排序）')
        for i, p in enumerate(cls.availableProxy, 1):
            latency = cls._proxyLatency.get(p, 0)
            src = cls._proxySource.get(p, '?')
            print(f'  {i}. [{src}] {p} ({latency:.0f}ms)')
        print('=' * 80)
        return cls.availableProxy

    # ==================== 获取代理 ====================

    @classmethod
    def get_proxy(cls, getNum=1, testNum=5, filter=None, sources=None, maxWorks=8, retest=True):
        """
        快捷获取代理：相当于调用 main() 检测出 testNum 条可用代理，再取延迟最低（最优）的 getNum 条

        :param getNum: 最终获取的代理数量，默认1
        :param testNum: 检测的可用代理数量，默认5（先检测出5条，再从中取最优的）
        :param filter: 过滤条件元组 (region, protocol)，同 main()
            region: 'china'/'abroad'/None(全部)
            protocol: 'http'/'https'/('http','https')/None(全部)
        :param sources: 代理源名称列表，None=使用全部，同 main()
        :param maxWorks: 并发检测线程数，同 main()
        :param retest: 是否二次筛选，同 main()；默认 True（对首轮存活代理复测，只留两次都通过的，更稳），不需要可置 False
        :return: getNum=1 时返回 {'http': 'http://ip:port', 'https': 'http://ip:port'}；
                 getNum>1 时返回字典列表；无可用代理时 getNum=1 返回 None、getNum>1 返回 []

        使用示例：
            # 检测5条取最优1条
            proxy = ProxyPool.get_proxy()
            resp = requests.get('https://example.com', proxies=proxy, timeout=10)

            # 只要国内http代理，检测出5条后取最优3条
            proxies = ProxyPool.get_proxy(getNum=3, testNum=5, filter=('china', 'http'))
        """
        available = cls.main(total=testNum, filter=filter, sources=sources, maxWorks=maxWorks, retest=retest)
        if not available:
            print('⚠️ 没有可用代理')
            return None if getNum == 1 else []
        result = []
        for proxy in available[:getNum]:
            ip_port = proxy[proxy.find('://') + 3:]
            result.append({'http': f'http://{ip_port}', 'https': f'http://{ip_port}'})
        return result[0] if getNum == 1 else result

    # ==================== 代理源实现 ====================

    class ZdyProxyPool:
        """站大爷免费代理API - http://www.zdopen.com/FreeProxy/Get/
        参数：count 最大100(超出仍按100返回)、dalu(必选) 1=大陆/0=海外、
        protocol_type 1=http/2=socks4/3=socks5/4=https、level_type 1高匿/2普匿/3匿名/4透明/5未知、return_type 3=JSON；
        文档要求调用间隔≥1秒(否则 code=12002)。
        重要坑：① 免费池 protocol_type 不可靠——传 4(https) 返回条目的 protocol 字段仍是 http，故协议一律以每条
        item 的 protocol 字段为准，绝不按请求参数硬贴标签，socks 及非本次请求协议本地剔除；
        ② 单查固定只回 100 条且重复调用不轮换(第2次起全旧数据)，要提量只能按 level_type 分桶并集：
        各匿名等级是独立的 ≤100 桶，LEVELS 全并集实测国内 http 约 200+ 条(单查仅 100)。"""
        NAME = '站大爷代理'
        # (国内权重, 国外权重)，API支持dalu参数筛选国内/国外，质量对等
        WEIGHT = (3, 3)
        API = "http://www.zdopen.com/FreeProxy/Get/"
        APP_ID = '202606120521419669'
        AKEY = 'bf0c7ca08a8f2fd9'
        COUNT = 100  # 接口单次上限
        INTERVAL = 1.1  # 文档要求 ≥1 秒调一次
        # 匿名等级分桶(1高匿/2普匿/3匿名/4透明/5未知)并集提量；设为 (None,) 则关闭分桶仅单查100
        LEVELS = (1, 2, 3, 4, 5)

        @staticmethod
        def fetch(region=None, protocols=None):
            """获取代理列表
            :param region: 'china'/'abroad'/None
            :param protocols: ['http']/['https']/['http','https']/None
            """
            # 期望协议（小写），None=都要 http/https；框架仅支持 http/https，socks 忽略
            want = {p.lower() for p in protocols} if protocols else {'http', 'https'}
            want &= {'http', 'https'}
            if not want:
                return []
            # 地区：dalu 1=大陆, 0=海外
            if region == 'china':
                daluList = [1]
            elif region == 'abroad':
                daluList = [0]
            else:
                daluList = [1, 0]
            # protocol_type 仅用于提高命中密度；最终以返回体 protocol 字段过滤，避免协议错标
            typeMap = {'http': 1, 'https': 4}
            # level_type 各匿名等级为独立 ≤100 桶，逐桶并集以提量；LEVELS=(None,) 时不分桶
            levels = ProxyPool.ZdyProxyPool.LEVELS or (None,)

            seen = set()
            proxies = []
            for dalu in daluList:
                for proto in sorted(want):
                    for level in levels:
                        params = {
                            'app_id': ProxyPool.ZdyProxyPool.APP_ID,
                            'akey': ProxyPool.ZdyProxyPool.AKEY,
                            'count': ProxyPool.ZdyProxyPool.COUNT,
                            'dalu': dalu,
                            'protocol_type': typeMap[proto],
                            'return_type': 3,
                        }
                        if level is not None:
                            params['level_type'] = level
                        headers = {'User-Agent': random.choice(ProxyPool._UALIST)}
                        try:
                            response = requests.get(ProxyPool.ZdyProxyPool.API, params=params, timeout=10,
                                                    headers=headers)
                            result = response.json()
                        except Exception as e:
                            print(f'[站大爷代理] 请求失败：{e}')
                            time.sleep(ProxyPool.ZdyProxyPool.INTERVAL)
                            continue
                        code = str(result.get('code'))
                        # 10001 成功；12009 该条件无代理(免费池https常空) 静默跳过；其余异常提示
                        if code not in ('10001', '12009'):
                            print(f'[站大爷代理] dalu={dalu} {proto} level={level} 返回 code={code}')
                        for item in (result.get('data') or {}).get('proxy_list', []):
                            real = (item.get('protocol') or '').lower()
                            if real != proto:  # 以实际协议为准，过滤错标与 socks
                                continue
                            proxy = f"{proto}://{item.get('ip')}:{item.get('port')}"
                            if proxy not in seen:  # 跨桶去重
                                seen.add(proxy)
                                proxies.append(proxy)
                        time.sleep(ProxyPool.ZdyProxyPool.INTERVAL)
            return proxies

    class ProxyFreeOnlyProxyPool:
        """proxyfreeonly代理 - https://proxyfreeonly.com/
        前端数据接口：GET https://proxyfreeonly.com/api/data/proxy-list
          ?page=1&limit=200&locale=en&where={"country":"china","protocols":"http"}
        返回 {"items":[{ip,port,protocols[],country:{countryCode,...},upTime,...}],"totalItems":N}。
        裸请求即可(无需 cookie/CF盾)，且 where.country(用 slug 如 china/united-states)、where.protocols
        与 limit/page 均在服务端生效，可分页取小量，远优于全量接口 /api/free-proxy-list。
        本框架：region='china' 传 where.country='china' 并按协议分别请求(数据量小一次拉完)；
        abroad/None 只按协议请求全国家再本地排除 CN 与噪声国家 NOISE(默认LU机房刷量)；只留 http/https，socks 忽略。
        质量：CN http/https 本机实测 https 隧道存活约17%、明文约24%，延迟亚秒，是国内免费源较好档；
        全球池被海量 LU 机房代理稀释、跨境延迟5~10s 且存活极低，故国外权重下调"""
        NAME = 'proxyfreeonly代理'
        # (国内权重, 国外权重)，CN 为强项，国外因噪声国家多而下调
        WEIGHT = (2, 1)
        API = 'https://proxyfreeonly.com/api/data/proxy-list'
        NOISE = ('LU',)  # abroad 时本地剔除的数据中心刷量国家(countryCode)
        PAGE_LIMIT = 200  # 单次服务端返回条数(实测 limit 生效)
        MAX_PAGES = 5  # 每个协议最多翻页数，防止 abroad 拉太多
        TIMEOUT = 25

        @staticmethod
        def fetch(region=None, protocols=None):
            proto_list = [p for p in (protocols or ['http', 'https']) if p in ('http', 'https')]
            noise = ProxyPool.ProxyFreeOnlyProxyPool.NOISE
            proxies = []
            for proto in proto_list:
                where = {'protocols': proto}
                if region == 'china':
                    where['country'] = 'china'  # 接口用 slug 而非 ISO-2 码
                whereStr = json.dumps(where, separators=(',', ':'))
                for page in range(1, ProxyPool.ProxyFreeOnlyProxyPool.MAX_PAGES + 1):
                    params = {'page': page, 'limit': ProxyPool.ProxyFreeOnlyProxyPool.PAGE_LIMIT,
                              'locale': 'en', 'where': whereStr}
                    try:
                        response = requests.get(
                            ProxyPool.ProxyFreeOnlyProxyPool.API, params=params,
                            timeout=ProxyPool.ProxyFreeOnlyProxyPool.TIMEOUT,
                            headers={'User-Agent': random.choice(ProxyPool._UALIST),
                                     'Accept': 'application/json, text/plain, */*',
                                     'Referer': 'https://proxyfreeonly.com/zh/free-proxy-list'}
                        )
                        j = response.json()
                    except Exception as e:
                        print(f'[proxyfreeonly代理] 第{page}页获取失败：{e}')
                        break
                    items = j.get('items', [])
                    if not items:
                        break
                    for it in items:
                        # china 已由服务端过滤；仅 abroad 本地排除 CN 与噪声国家
                        if region == 'abroad':
                            code = (it.get('country') or {}).get('countryCode')
                            if code == 'CN' or code in noise:
                                continue
                        proxies.append(f"{proto}://{it.get('ip')}:{it.get('port')}")
                    if page * ProxyPool.ProxyFreeOnlyProxyPool.PAGE_LIMIT >= j.get('totalItems', 0):
                        break
            return proxies


# 注册内置代理源
ProxyPool.register_source(ProxyPool.ZdyProxyPool)
ProxyPool.register_source(ProxyPool.ProxyFreeOnlyProxyPool)

if __name__ == '__main__':
    ProxyPool.check_file()
