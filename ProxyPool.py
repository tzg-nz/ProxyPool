import requests
import random
import time
import json
import os
import threading
from bs4 import BeautifulSoup
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
    _lock = threading.Lock()

    _TEST_URLS = ['https://icanhazip.com/', 'https://myip.ipip.net/', 'https://api.ip.sb/ip']

    _UALIST = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    ]

    def __init__(self, total=None, filter=None, sources=None, useWeight=True, shuffle=False):
        """
        :param total: 需要的可用代理总数，达到即停
        :param filter: 过滤条件元组 (region, protocol)
            region: 'china'/'abroad'/None(全部)
            protocol: 'http'/'https'/('http','https')/None(全部)
            示例：('china', 'http')  ('abroad', ('http', 'https'))  (None, 'https')
        :param sources: 代理源名称列表，None=使用全部
        :param useWeight: 是否按权重优先爬取，True=高权重源优先
        :param shuffle: 是否打乱代理顺序再检测，True=随机顺序检测
        """
        self.total = total
        self.sources = sources
        self.useWeight = useWeight
        self.shuffle = shuffle
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
        """验证测速网站是否可用，移除不可用的"""
        available = []
        for url in cls._TEST_URLS:
            try:
                resp = requests.get(url, timeout=6)
                if resp.ok:
                    print(f'✅测速网站可用：{url}')
                    available.append(url)
                else:
                    print(f'❌测速网站不可用：{url} (状态码 {resp.status_code})')
            except Exception as e:
                print(f'❌测速网站不可用：{url} ({type(e).__name__})')
        if not available:
            raise Exception('⚠️所有测速网站均不可用，无法检测代理')
        cls._TEST_URLS = available
        print()

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

    def _fetchAllProxies(self):
        """获取代理，按权重模式决定并发或串行"""
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
        allProxies = []
        seen = set()

        if self.useWeight:
            # 按权重降序排列，高权重优先爬取（单选地区用对应地区权重，全选用综合权重）
            sortedSources = sorted(
                sourceNames,
                key=lambda name: ProxyPool._getWeight(name, self.region),
                reverse=True
            )
            weightDesc = '综合' if self.region is None else ('国内' if self.region == 'china' else '国外')
            weightStr = ' > '.join(f'{s}({ProxyPool._getWeight(s, self.region):g})' for s in sortedSources)
            print(f'权重模式({weightDesc}权重优先)：{weightStr}')
            for name in sortedSources:
                proxies = self._fetchFromSource(name)
                for p in proxies:
                    if p not in seen:
                        seen.add(p)
                        allProxies.append(p)
        else:
            # 并发获取所有代理源
            with ThreadPoolExecutor(max_workers=len(sourceNames)) as executor:
                futures = {executor.submit(self._fetchFromSource, name): name for name in sourceNames}
                for future in as_completed(futures):
                    try:
                        proxies = future.result()
                        for p in proxies:
                            if p not in seen:
                                seen.add(p)
                                allProxies.append(p)
                    except Exception:
                        continue

        print(f'\n共获取 {len(allProxies)} 条不重复代理')
        ProxyPool.allProxy = allProxies
        return allProxies

    # ==================== 代理检测 ====================

    def _testProxy(self, proxy, target):
        """测试单个代理是否可用，返回 (proxy, elapsed_ms) 或 (None, 0)"""
        ipPort = proxy[proxy.find('://') + 3:]
        proxy_url = f"http://{ipPort}"
        proxies = {'http': proxy_url, 'https': proxy_url}
        for testUrl in self._TEST_URLS:
            try:
                start = time.time()
                response = requests.get(testUrl, proxies=proxies, timeout=6)
                elapsed = (time.time() - start) * 1000
                if response.ok:
                    return (proxy, elapsed)
                return (None, 0)
            except Exception:
                return (None, 0)
        return (None, 0)

    def _checkProxies(self, proxyList, maxWorks=8):
        """并发检测代理，达到total即停"""
        if not proxyList:
            print('⚠️没有代理需要检测')
            return

        target = self.total or len(proxyList)
        total_count = len(proxyList)
        checked = [0]
        available = ProxyPool.availableProxy
        proxyIter = iter(proxyList)

        print(f'开始检测 {total_count} 条代理，目标 {target} 条，并发 {maxWorks} 线程')
        print('-' * 80)

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
                                    print(f'✅ {res} ({elapsed:.0f}ms) | 进度 {checked[0]}/{total_count} | 可用 {len(available)}/{target}')
                                    if len(available) >= target:
                                        print(f'\n✅已达目标数量 {target}')
                                        return
                                else:
                                    print(f'⚠️ {res} 重复 | 进度 {checked[0]}/{total_count} | 可用 {len(available)}/{target}')
                            else:
                                print(f'❌ 无效 | 进度 {checked[0]}/{total_count} | 可用 {len(available)}/{target}')
                    except Exception:
                        continue

    # ==================== 主入口 ====================

    @classmethod
    def main(cls, total=None, filter=None, sources=None, useWeight=True, shuffle=False, maxWorks=8):
        """
        获取并验证代理

        :param total: 需要的可用代理总数，达到即停（None=全量检测）
        :param filter: 过滤条件元组 (region, protocol)
            region: 'china'/'abroad'/None(全部)
            protocol: 'http'/'https'/('http','https')/None(全部)
            示例：('china', 'http')  ('abroad', ('http', 'https'))  (None, 'https')
        :param sources: 代理源名称列表，如 ['站大爷代理', '云代理']，None=使用全部
        :param useWeight: 是否按权重优先爬取，True=高权重源先爬先检测
        :param shuffle: 是否打乱代理顺序再检测，True=随机顺序检测，避免同一网站代理集中检测
        :param maxWorks: 并发检测线程数
        :return: 可用代理列表
        """
        # 重置
        cls.allProxy = []
        cls.availableProxy = []
        cls._proxyLatency = {}

        instance = cls(total, filter, sources, useWeight, shuffle)

        # 0. 验证测速网站
        print('=' * 80)
        print('验证测速网站可用性...')
        print('=' * 80)
        cls._checkTestUrls()

        # shuffle与useWeight互斥：shuffle会打乱权重排好的顺序
        if instance.shuffle and instance.useWeight:
            print('⚠️ shuffle=True 时 useWeight 无意义，已自动关闭权重模式')
            instance.useWeight = False

        # 1. 从所有代理源获取代理
        region_str = instance.region or '全部'
        proto_str = ','.join(instance.protocols) if instance.protocols else '全部'
        print('=' * 80)
        print(f'地区：{region_str} | 协议：{proto_str} | 代理源：{sources or "全部"} | 目标数量：{total or "不限"} | 权重模式：{"开启" if instance.useWeight else "关闭"} | 随机检测：{"开启" if instance.shuffle else "关闭"}')
        print('=' * 80)
        allProxies = instance._fetchAllProxies()

        # 2. 打乱代理顺序
        if instance.shuffle:
            random.shuffle(allProxies)
            print('🔀 已打乱代理检测顺序')
        elif instance.useWeight:
            print('📌 按权重顺序检测（高权重源在前）')
        else:
            print('📌 按获取顺序检测')

        # 3. 并发检测代理
        print('\n开始检测代理可用性...')
        print('=' * 80)
        instance._checkProxies(allProxies, maxWorks)

        # 4. 按延迟排序，最快的在前
        cls.availableProxy.sort(key=lambda p: cls._proxyLatency.get(p, float('inf')))

        print(f'\n{"=" * 80}')
        print(f'检测完成，共 {len(cls.availableProxy)} 条可用代理（按延迟排序）')
        for i, p in enumerate(cls.availableProxy, 1):
            latency = cls._proxyLatency.get(p, 0)
            print(f'  {i}. {p} ({latency:.0f}ms)')
        print('=' * 80)
        return cls.availableProxy

    # ==================== 导出 ====================

    @classmethod
    def export(cls, fmt='txt', filepath=None):
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
            # 按协议分组，包含延迟
            grouped = {'http': [], 'https': []}
            for p in proxies:
                proto = 'https' if p.startswith('https://') else 'http'
                if p not in seen:
                    seen.add(p)
                    grouped[proto].append({
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
        return content

    # ==================== 获取代理 ====================

    @classmethod
    def get_proxy(cls, getNum=1, testNum=5, filter=None, sources=None, useWeight=True, shuffle=False, maxWorks=8):
        """
        快捷获取代理：相当于调用 main() 检测出 testNum 条可用代理，再取延迟最低（最优）的 getNum 条

        :param getNum: 最终获取的代理数量，默认1
        :param testNum: 检测的可用代理数量，默认5（先检测出5条，再从中取最优的）
        :param filter: 过滤条件元组 (region, protocol)，同 main()
            region: 'china'/'abroad'/None(全部)
            protocol: 'http'/'https'/('http','https')/None(全部)
        :param sources: 代理源名称列表，None=使用全部，同 main()
        :param useWeight: 是否按权重优先爬取，同 main()
        :param shuffle: 是否打乱代理顺序检测，同 main()
        :param maxWorks: 并发检测线程数，同 main()
        :return: getNum=1 时返回 {'http': 'http://ip:port', 'https': 'http://ip:port'}；
                 getNum>1 时返回字典列表；无可用代理时 getNum=1 返回 None、getNum>1 返回 []

        使用示例：
            # 检测5条取最优1条
            proxy = ProxyPool.get_proxy()
            resp = requests.get('https://example.com', proxies=proxy, timeout=10)

            # 只要国内http代理，检测出5条后取最优3条
            proxies = ProxyPool.get_proxy(getNum=3, testNum=5, filter=('china', 'http'))
        """
        available = cls.main(total=testNum, filter=filter, sources=sources,
                             useWeight=useWeight, shuffle=shuffle, maxWorks=maxWorks)
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
        """站大爷代理 - protocol_type: 1=http, 2=socks4, 3=socks5, 4=https; dalu: 1=国内, 0=海外"""
        NAME = '站大爷代理'
        # (国内权重, 国外权重)，API支持dalu参数筛选国内/国外，质量对等
        WEIGHT = (3, 3)
        API = "http://www.zdopen.com/FreeProxy/Get/"

        def __init__(self):
            self.app_id = '202606120521419669'
            self.akey = 'bf0c7ca08a8f2fd9'

        @staticmethod
        def fetch(region=None, protocols=None):
            """获取代理列表
            :param region: 'china'/'abroad'/None
            :param protocols: ['http']/['https']/['http','https']/None
            """
            self = ProxyPool.ZdyProxyPool()
            proxies = []
            # 协议映射
            proto_map = {'http': 1, 'https': 4}
            if protocols:
                type_list = [(proto_map[p], p) for p in protocols if p in proto_map]
            else:
                type_list = [(1, 'http'), (4, 'https')]

            # 地区映射：dalu 1=国内, 0=海外
            if region == 'china':
                dalu_list = [1]
            elif region == 'abroad':
                dalu_list = [0]
            else:
                dalu_list = [1, 0]

            for protocol_type, proto_prefix in type_list:
                for dalu in dalu_list:
                    params = {
                        "app_id": self.app_id,
                        "akey": self.akey,
                        "count": 100,
                        "dalu": dalu,
                        "protocol_type": protocol_type,
                        "return_type": 3
                    }
                    headers = {'User-Agent': random.choice(ProxyPool._UALIST)}
                    try:
                        response = requests.get(self.API, params=params, timeout=6, headers=headers)
                        if response.ok:
                            for item in response.json().get('data', {}).get('proxy_list', []):
                                proxy = f"{proto_prefix}://{item.get('ip')}:{item.get('port')}"
                                proxies.append(proxy)
                    except Exception as e:
                        print(f'[站大爷代理] 请求失败：{e}')
                    time.sleep(1)
            return proxies

    class SixSixProxyPool:
        """六六代理 - 仅国内代理（官网地区分类只有中国省份），API不分地区"""
        NAME = '六六代理'
        # (国内权重, 国外权重)，国外为None表示该源没有国外代理，region='abroad'时跳过此源
        WEIGHT = (2, None)
        API = 'http://api.66daili.com/'

        @staticmethod
        def fetch(region=None, protocols=None):
            proxies = []
            if protocols:
                proto_list = protocols
            else:
                proto_list = ['http', 'https']

            for proto in proto_list:
                params = {'num': '60', 'protocol': proto, 'format': 'json'}
                headers = {'User-Agent': random.choice(ProxyPool._UALIST)}
                try:
                    response = requests.get(ProxyPool.SixSixProxyPool.API, params=params, timeout=6, headers=headers)
                    if response.ok:
                        for item in response.json().get('data', []):
                            proxy = f"{proto}://{item.get('ip')}:{item.get('port')}"
                            proxies.append(proxy)
                    elif response.status_code == 429:
                        print('[六六代理] 请求次数过多，稍后重试')
                except Exception as e:
                    print(f'[六六代理] 请求失败：{e}')
                time.sleep(1)
            return proxies

    class YunProxyPool:
        """云代理 - 仅国内代理，爬取ip3366国内高匿页(stype=1)，无国外数据"""
        NAME = '云代理'
        # (国内权重, 国外权重)，国外为None表示该源没有国外代理，region='abroad'时跳过此源
        WEIGHT = (2, None)
        INDEXURL = 'http://www.ip3366.net/free/'

        @staticmethod
        def fetch(region=None, protocols=None):
            proxies = []
            try:
                indexCode = requests.get(ProxyPool.YunProxyPool.INDEXURL, timeout=6).content
                indexSoup = BeautifulSoup(indexCode, 'html.parser')
                lastPage = int(indexSoup.select_one('#listnav a:nth-last-of-type(3)').get_text())
            except Exception as e:
                print(f'[云代理] 获取页数失败：{e}')
                return []

            for page in range(1, lastPage + 1):
                try:
                    if page == 1:
                        soup = indexSoup
                    else:
                        code = requests.get(
                            f'{ProxyPool.YunProxyPool.INDEXURL}?stype=1&page={page}', timeout=6
                        ).content
                        soup = BeautifulSoup(code, 'html.parser')

                    for tr in soup.select('table tbody tr'):
                        tds = tr.find_all('td')
                        if len(tds) < 5:
                            continue
                        ip = tds[0].get_text().strip()
                        port = tds[1].get_text().strip()
                        proto = tds[3].get_text().strip().lower()
                        # 根据protocols参数过滤
                        if protocols and proto not in protocols:
                            continue
                        proxy = f"{proto}://{ip}:{port}"
                        proxies.append(proxy)
                except Exception as e:
                    print(f'[云代理] 第{page}页获取失败：{e}')
            return proxies

    class FreeVpnNodeProxyPool:
        """FreeVPNNode代理 - https://cn.freevpnnode.com/free-proxy/
        综合页含国内外代理（国家代码CN=国内），每页30条，支持http/https/socks4/socks5。
        region='china'时直接爬中国专属页/free-proxy-for-china/效率更高。
        代理池框架仅支持http/https，该站的socks4/socks5代理自动忽略。
        每页请求间隔1秒防封，默认最多爬MAXPAGES页（列表按更新时间排序，越靠前越新鲜）。
        质量：数据量大（约2.4万条）且每3分钟更新，但国内外实测存活率均极低——前几页80端口
        条目多为Cloudflare CDN伪代理（仅回HTTP页面不支持CONNECT），真代理又常被墙，
        (1, 1)仅作补充源"""
        NAME = 'FreeVPNNode代理'
        # (国内权重, 国外权重)，国内外实测均极差
        WEIGHT = (1, 1)
        INDEXURL = 'https://cn.freevpnnode.com/free-proxy/'
        CHINAURL = 'https://cn.freevpnnode.com/free-proxy-for-china/'
        MAXPAGES = 3

        @staticmethod
        def fetch(region=None, protocols=None):
            proxies = []
            proto_list = ['http', 'https']
            if protocols:
                proto_list = [p for p in proto_list if p in protocols]
                if not proto_list:
                    return proxies

            # 地区过滤：None=全部(综合页)，china=只要CN(中国页)，abroad=排除CN(综合页)
            if region == 'china':
                baseurls = [ProxyPool.FreeVpnNodeProxyPool.CHINAURL]
            else:
                baseurls = [ProxyPool.FreeVpnNodeProxyPool.INDEXURL]

            for baseurl in baseurls:
                for page in range(1, ProxyPool.FreeVpnNodeProxyPool.MAXPAGES + 1):
                    try:
                        url = baseurl if page == 1 else f'{baseurl}?page={page}'
                        headers = {'User-Agent': random.choice(ProxyPool._UALIST)}
                        response = requests.get(url, headers=headers, timeout=6)
                        if not response.ok:
                            print(f'[FreeVPNNode代理] 第{page}页状态码异常：{response.status_code}')
                            break
                        response.encoding = 'utf-8'
                        soup = BeautifulSoup(response.text, 'html.parser')
                        trs = soup.select('table.table tbody tr')
                        if not trs:
                            break
                        for tr in trs:
                            tds = tr.find_all('td')
                            if len(tds) < 6:
                                continue
                            ip = tds[0].get_text(strip=True)
                            port = tds[1].get_text(strip=True)
                            proto = tds[5].get_text(strip=True).lower()
                            if proto not in proto_list:
                                continue
                            # 国家代码在第5列（如 CO/US/CN），用于地区过滤
                            countryA = tds[4].find('a')
                            country = countryA.get_text(strip=True) if countryA else ''
                            if region == 'china' and country != 'CN':
                                continue
                            if region == 'abroad' and country == 'CN':
                                continue
                            proxies.append(f'{proto}://{ip}:{port}')
                    except Exception as e:
                        print(f'[FreeVPNNode代理] 第{page}页获取失败：{e}')
                    time.sleep(1)
            return proxies


# 注册内置代理源
ProxyPool.register_source(ProxyPool.ZdyProxyPool)
ProxyPool.register_source(ProxyPool.SixSixProxyPool)
ProxyPool.register_source(ProxyPool.YunProxyPool)
ProxyPool.register_source(ProxyPool.FreeVpnNodeProxyPool)


if __name__ == '__main__':
    # 示例1：获取10条国内http代理
    proxies = ProxyPool.main(total=5, filter=('china', 'http'))
    ProxyPool.export(fmt='jsonl')

    # 示例2：获取5条海外https代理
    # proxies = ProxyPool.main(total=5, filter=('abroad', 'https'))

    # 示例3：获取20条国内http+https代理
    # proxies = ProxyPool.main(total=20, filter=('china', ('http', 'https')))

    # 示例4：不限地区，只要http代理
    # proxies = ProxyPool.main(total=10, filter=(None, 'http'))

    # 示例5：全量检测，不限地区不限协议
    # proxies = ProxyPool.main()
