import requests
import random
import time
import json
import os
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed


class ProxyPool:
    SUPPORTFORMAT = ['txt', 'json', 'jsonl']
    allProxy = {
        'China': {
            'http': [],
            'https': []
        },
        'abroad': {
            'http': [],
            'https': []
        }
    }
    _WEBURL = {
        'proxy': [('http://www.zdopen.com/FreeProxy/Get/', 'ProxyPool.ZdyProxyPool()'),
                  ('https://www.66daili.com/', 'ProxyPool.SixSixProxyPool()'),
                  ('http://www.ip3366.net/free/', 'ProxyPool.YunProxyPool()')],
        'test': ['https://icanhazip.com/', 'https://myip.ipip.net/', 'https://api.ip.sb/ip']
    }
    _UALIST = [
        # Chrome 桌面端（Windows）
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",

        # Chrome 桌面端（Mac）
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",

        # Edge 浏览器
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",

        # Firefox 火狐
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/118.0",

        # Safari 苹果浏览器
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",

        # 安卓手机 Chrome
        "Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 12; Mi 11) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",

        # iPhone 手机 Safari
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",

        # 安卓平板
        "Mozilla/5.0 (Linux; Android 13; Lenovo TB-J706F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    availableObject = []
    availableProxy = {
        'China': {
            'http': [],
            'https': []
        },
        'abroad': {
            'http': [],
            'https': []
        }
    }

    def __init__(self, perType=None, total=None):
        self.perType = perType
        self.total = total
        self._checkWebAvailable()
        if len(ProxyPool._WEBURL.get('proxy')) == 0:
            raise Exception('⚠️可用代理网址网址全部失效/连接超时，请添加新的代理网址/重新发送请求\n')
        elif len(ProxyPool._WEBURL.get('test')) == 0:
            raise Exception('⚠️可用测试网址网址全部失效/连接超时，请添加新的测试网址/重新发送请求\n')
        self._createInnerClass()

    def _checkWebAvailable(self):
        # 代理网址
        for urlInfo in self._WEBURL.get('proxy'):
            url = urlInfo[0]
            try:
                print(f'正在检测代理网址：{url}是否可用')
                response = requests.get(url, timeout=6)
                if not response.ok:
                    print(f'❌代理网址失效：{url}\n')
                    self._WEBURL.get('proxy').remove(urlInfo)
                else:
                    print(f'✅当前代理网址可访问：{url}\n')

            except requests.exceptions.ConnectTimeout:
                self._WEBURL.get('proxy').remove(urlInfo)
                print(f'❌代理网址连接超时：{url}\n')
        # 测试网址
        for url in self._WEBURL.get('test'):
            try:
                print(f'正在检测测试网址：{url}是否可用')
                response = requests.get(url, timeout=6)
                if not response.ok:
                    print(f'❌测试网址失效：{url}\n')
                    self._WEBURL.get('test').remove(url)
                else:
                    print(f'✅当前测试网址可访问：{url}\n')
            except requests.exceptions.ConnectTimeout:
                self._WEBURL.get('test').remove(url)
                print(f'❌测试网址连接超时：{url}\n')
            except requests.exceptions.ReadTimeout:
                self._WEBURL.get('test').remove(url)
                print(f'❌测试网址读取超时：{url}\n')
            except:
                self._WEBURL.get('test').remove(url)
                raise Exception(f'❌️测试网址未知错误：{url}\n')
        print('=' * 200 + '\n')

    def _createInnerClass(self):
        for addressInfo in ProxyPool._WEBURL.get('proxy'):
            innerObject = eval(addressInfo[-1])
            ProxyPool.availableObject.append(innerObject)

    def _requestTest(self, itemProxy):
        ipPort = itemProxy[itemProxy.find('://') + 3:]
        proxy_url = f"http://{ipPort}"
        proxy = {
            'http': proxy_url,
            'https': proxy_url
        }
        for testUrl in self._WEBURL.get('test'):
            try:
                print(f'请求网址{testUrl} | 测试代理：{itemProxy}\n')
                response = requests.get(testUrl, proxies=proxy, timeout=6)
                if response.ok:
                    print(f"✅有效代理 {itemProxy}\n")
                    return itemProxy
                print(f'❌无效代理：{itemProxy}\n')
                return None
            except requests.exceptions.ProxyError:
                print(f'❌连接服务器地址失败：{itemProxy}\n')
                return None
            except requests.exceptions.ConnectTimeout:
                print(f'❌连接超时：{itemProxy}\n')
                return None
            except requests.exceptions.ReadTimeout:
                print(f'❌读取超时：{itemProxy}\n')
                return None
            except Exception as e:
                print(f'❌️代理网址未知错误：{itemProxy}\n')
                print(e)
                return None
        return None

    def _asyncCheckProxy(self, proxyList, region, protocol, perType, maxWorks=4):
        proto = protocol.lower()
        availableProxyList = ProxyPool.availableProxy.get(region).get(proto, [])
        if perType:
            if len(availableProxyList) >= perType:
                return
            proxyIter = iter(proxyList)
            with ThreadPoolExecutor(max_workers=maxWorks) as executor:
                futures = []
                while True:
                    # 线程池未满，持续提交新任务
                    while len(futures) < maxWorks:
                        try:
                            proxy = next(proxyIter)
                            futures.append(executor.submit(self._requestTest, proxy))
                        except StopIteration:
                            break

                    # 没有待处理任务，结束
                    if not futures:
                        print(f'已遍历完{region}中{proto}列表')
                        break

                    # 逐个处理已完成任务
                    for future in as_completed(futures):
                        futures.remove(future)
                        # 捕获异常，防止单任务报错崩掉整体
                        try:
                            res = future.result()
                            # 只追加非None的有效代理，过滤空值，去重
                            if res is not None and res not in availableProxyList:
                                availableProxyList.append(res)
                                # 凑够数量直接退出
                                if len(availableProxyList) >= perType:
                                    print(f'✅️{region}的{proto}成功获取数量：{perType}')
                                    return
                        except Exception:
                            continue
        else:
            with ThreadPoolExecutor(max_workers=maxWorks) as executor:
                for itemProxy in executor.map(self._requestTest, proxyList):
                    if itemProxy and itemProxy not in availableProxyList:
                        availableProxyList.append(itemProxy)

    def _currentTotal(self):
        return sum(len(v) for region in ProxyPool.availableProxy.values() for v in region.values())

    def checkChinaProxy(self, perType):
        httpProxyList = ProxyPool.allProxy.get('China').get('http')
        httpsProxyList = ProxyPool.allProxy.get('China').get('https')

        def _checkChinaHttpProxys():
            self._asyncCheckProxy(httpProxyList, 'China', 'http', perType)

        def _checkChinaHttpsProxys():
            self._asyncCheckProxy(httpsProxyList, 'China', 'https', perType)

        _checkChinaHttpProxys()
        if self.total and self._currentTotal() >= self.total:
            return
        _checkChinaHttpsProxys()

    def checkAbroadProxy(self, perType):
        httpProxyList = ProxyPool.allProxy.get('abroad').get('http')
        httpsProxyList = ProxyPool.allProxy.get('abroad').get('https')

        def _checkAbroadHttpProxys():
            self._asyncCheckProxy(httpProxyList, 'abroad', 'http', perType)

        def _checkAbroadHttpsProxys():
            self._asyncCheckProxy(httpsProxyList, 'abroad', 'https', perType)

        _checkAbroadHttpProxys()
        if self.total and self._currentTotal() >= self.total:
            return
        _checkAbroadHttpsProxys()

    def checkAllProxy(self):
        if self.total and not self.perType:
            self.perType = -(-self.total // 4)
        self.checkChinaProxy(self.perType)
        if self.total and self._currentTotal() >= self.total:
            print(f'✅已达总量目标 {self.total}，跳过海外代理检测')
            return
        self.checkAbroadProxy(self.perType)

    @classmethod
    def main(cls, perType=None, total=None, speed=True, noStrict=True):
        cls.availableObject.clear()
        instance = cls(perType, total)
        if speed and (not noStrict == False):
            for obj in cls.availableObject:
                print('=' * 200)
                print(f'当前代理网站：{obj.NAME}')
                obj.getAllProxys()
                instance.checkAllProxy()
        elif speed:
            obj = cls.availableObject[0]
            print('=' * 200)
            print(f'当前代理网站：{obj.NAME}')
            obj.getAllProxys()
            instance.checkAllProxy()
        elif noStrict:
            random.shuffle(cls.availableObject)
            for obj in cls.availableObject:
                print('=' * 200)
                print(f'当前代理网站：{obj.NAME}')
                obj.getAllProxys()
                instance.checkAllProxy()
        else:
            raise Exception('又慢又严格影响性能')
        return cls.availableProxy

    @classmethod
    def export(cls, fmt='txt', filepath=None):
        if fmt not in cls.SUPPORTFORMAT:
            raise ValueError(f'不支持的导出格式: {fmt}，可选: {cls.SUPPORTFORMAT}')

        proxies = cls.availableProxy
        seen = set()
        if fmt == 'txt':
            lines = []
            for region, protocols in proxies.items():
                for protocol, proxyList in protocols.items():
                    for proxy in proxyList:
                        if proxy not in seen:
                            seen.add(proxy)
                            lines.append(proxy)
            content = '\n'.join(lines)

        elif fmt == 'json':
            deduped = {}
            for region, protocols in proxies.items():
                deduped[region] = {}
                for protocol, proxyList in protocols.items():
                    deduped[region][protocol] = list(dict.fromkeys(proxyList))
            content = json.dumps(deduped, ensure_ascii=False, indent=2)

        elif fmt == 'jsonl':
            lines = []
            for region, protocols in proxies.items():
                for protocol, proxyList in protocols.items():
                    for proxy in proxyList:
                        if proxy not in seen:
                            seen.add(proxy)
                            lines.append(json.dumps(
                                {'region': region, 'protocol': protocol, 'proxy': proxy},
                                ensure_ascii=False
                            ))
            content = '\n'.join(lines)

        unique_count = len(seen) if seen else sum(len(v) for v in deduped.values() for v in v.values())
        if unique_count == 0:
            print('⚠️没有可用代理，请先调用 main() 获取')
            return

        if filepath is None:
            filepath = os.path.join(os.getcwd(), f'proxies.{fmt}')

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'✅已导出 {unique_count} 条不重复代理到 {filepath}')

        return content

    # 站大爷代理
    class ZdyProxyPool:
        NAME = '站大爷代理'
        API = "http://www.zdopen.com/FreeProxy/Get/"

        def __init__(self, app_id=None, akey=None, count=100, dalu=1,
                     protocol_type=4,
                     return_type=3):
            self.app_id = '202606120521419669'
            self.akey = 'bf0c7ca08a8f2fd9'
            self.count = count
            self.dalu = dalu
            self.protocol_type = protocol_type
            self.return_type = return_type

        def getAllProxys(self):
            def _getChinaProxys():
                def _getHttpProxys():
                    baseUrl = ProxyPool.ZdyProxyPool.API
                    self.protocol_type = 1
                    params = {
                        "app_id": self.app_id,
                        "akey": self.akey,
                        "count": self.count,
                        "dalu": self.dalu,
                        "protocol_type": self.protocol_type,
                        "return_type": self.return_type
                    }
                    headers = {'User-Agent': random.choice(ProxyPool._UALIST)}
                    try:
                        response = requests.get(baseUrl, params=params, timeout=6,
                                                headers=headers)
                        if response.ok:
                            proxyInfoList = response.json().get('data').get('proxy_list')
                            for itemProxyInfo in proxyInfoList:
                                itemProxy = itemProxyInfo.get('protocol').lower() + '://' + itemProxyInfo.get(
                                    'ip') + ':' + str(itemProxyInfo.get('port'))
                                ProxyPool.allProxy.get('China').get('http').append(itemProxy)
                        else:
                            raise Exception('❌️请求失败\n')
                    except requests.exceptions.ConnectTimeout:
                        print(f'❌连接超时：{baseUrl}\n')
                    except requests.exceptions.ReadTimeout:
                        print(f'❌读取超时：{baseUrl}\n')
                    except Exception as e:
                        print(f'❌️API未知错误：{baseUrl}\n')
                        print(e)

                def _getHttpsProxys():
                    baseUrl = ProxyPool.ZdyProxyPool.API
                    self.protocol_type = 4
                    params = {
                        "app_id": self.app_id,
                        "akey": self.akey,
                        "count": self.count,
                        "dalu": self.dalu,
                        "protocol_type": self.protocol_type,
                        "return_type": self.return_type
                    }
                    headers = {'User-Agent': random.choice(ProxyPool._UALIST)}
                    try:
                        response = requests.get(baseUrl, params=params, timeout=6,
                                                headers=headers)
                        if response.ok:
                            proxyInfoList = response.json().get('data').get('proxy_list')
                            for itemProxyInfo in proxyInfoList:
                                itemProxy = itemProxyInfo.get('protocol').lower() + '://' + itemProxyInfo.get(
                                    'ip') + ':' + str(itemProxyInfo.get('port'))
                                ProxyPool.allProxy.get('China').get('https').append(itemProxy)
                        else:
                            raise Exception('❌️请求失败\n')
                    except requests.exceptions.ConnectTimeout:
                        print(f'❌连接超时：{baseUrl}\n')
                    except requests.exceptions.ReadTimeout:
                        print(f'❌读取超时：{baseUrl}\n')
                    except Exception as e:
                        print(f'❌️API未知错误：{baseUrl}\n')
                        print(e)

                _getHttpsProxys()
                time.sleep(1.5)
                _getHttpProxys()

            def _getAbroadProxys():
                def _getHttpProxys():
                    baseUrl = ProxyPool.ZdyProxyPool.API
                    self.dalu = 0
                    self.protocol_type = 1
                    params = {
                        "app_id": self.app_id,
                        "akey": self.akey,
                        "count": self.count,
                        "dalu": self.dalu,
                        "protocol_type": self.protocol_type,
                        "return_type": self.return_type
                    }
                    headers = {'User-Agent': random.choice(ProxyPool._UALIST)}
                    try:
                        response = requests.get(baseUrl, params=params, timeout=6,
                                                headers=headers)
                        if response.ok:
                            proxyInfoList = response.json().get('data').get('proxy_list')
                            for itemProxyInfo in proxyInfoList:
                                itemProxy = itemProxyInfo.get('protocol').lower() + '://' + itemProxyInfo.get(
                                    'ip') + ':' + str(itemProxyInfo.get('port'))
                                ProxyPool.allProxy.get('abroad').get('http').append(itemProxy)
                        else:
                            raise Exception('❌️请求失败\n')
                    except requests.exceptions.ConnectTimeout:
                        print(f'❌连接超时：{baseUrl}\n')
                    except requests.exceptions.ReadTimeout:
                        print(f'❌读取超时：{baseUrl}\n')
                    except Exception as e:
                        print(f'❌️API未知错误：{baseUrl}\n')
                        print(e)

                def _getHttpsProxys():
                    baseUrl = ProxyPool.ZdyProxyPool.API
                    self.protocol_type = 4
                    params = {
                        "app_id": self.app_id,
                        "akey": self.akey,
                        "count": self.count,
                        "dalu": self.dalu,
                        "protocol_type": self.protocol_type,
                        "return_type": self.return_type
                    }
                    headers = {'User-Agent': random.choice(ProxyPool._UALIST)}
                    try:
                        response = requests.get(baseUrl, params=params, timeout=6,
                                                headers=headers)
                        if response.ok:
                            proxyInfoList = response.json().get('data').get('proxy_list')
                            for itemProxyInfo in proxyInfoList:
                                itemProxy = itemProxyInfo.get('protocol').lower() + '://' + itemProxyInfo.get(
                                    'ip') + ':' + str(itemProxyInfo.get('port'))
                                ProxyPool.allProxy.get('abroad').get('https').append(itemProxy)
                        else:
                            raise Exception('❌️请求失败\n')
                    except requests.exceptions.ConnectTimeout:
                        print(f'❌连接超时：{baseUrl}\n')
                    except requests.exceptions.ReadTimeout:
                        print(f'❌读取超时：{baseUrl}\n')
                    except Exception as e:
                        print(f'❌️API未知错误：{baseUrl}\n')
                        print(e)

                _getHttpsProxys()
                time.sleep(1.5)
                _getHttpProxys()

            _getChinaProxys()
            time.sleep(1.5)
            _getAbroadProxys()

    # 六六代理
    class SixSixProxyPool:
        NAME = '六六代理'
        API = 'http://api.66daili.com/'

        def __init__(self, num=60, protocol='https', format='json'):
            self.num = str(num)
            self.protocol = protocol
            self.format = format

        def getAllProxys(self):
            def _getHttpProxys():
                self.protocol = 'http'
                baseUrl = ProxyPool.SixSixProxyPool.API
                params = {
                    'num': self.num,
                    'protocol': self.protocol,
                    'format': self.format
                }
                headers = {'User-Agent': random.choice(ProxyPool._UALIST)}
                try:
                    response = requests.get(baseUrl, params=params, timeout=6,
                                            headers=headers)
                    if response.ok:
                        proxyInfoList = response.json().get('data')
                        for itemProxyInfo in proxyInfoList:
                            itemProxy = itemProxyInfo.get('protocol').lower() + '://' + itemProxyInfo.get(
                                'ip') + ':' + itemProxyInfo.get('port')
                            ProxyPool.allProxy.get('China').get('http').append(itemProxy)
                    elif response.status_code == 429:
                        raise Exception('⚠️请求次数过多请稍后重试\n')
                    else:
                        raise Exception('❌️请求失败\n')
                except requests.exceptions.ConnectTimeout:
                    print(f'❌连接超时：{baseUrl}\n')
                except requests.exceptions.ReadTimeout:
                    print(f'❌读取超时：{baseUrl}\n')
                except Exception as e:
                    print(f'❌️API未知错误：{baseUrl}\n')
                    print(e)

            def _getHttpsProxys():
                baseUrl = ProxyPool.SixSixProxyPool.API
                params = {
                    'num': self.num,
                    'protocol': self.protocol,
                    'format': self.format
                }
                headers = {'User-Agent': random.choice(ProxyPool._UALIST)}
                try:
                    response = requests.get(baseUrl, params=params, timeout=6,
                                            headers=headers)
                    if response.ok:
                        proxyList = response.json().get('data')
                        for itemProxyInfo in proxyList:
                            itemProxy = itemProxyInfo.get('protocol').lower() + '://' + itemProxyInfo.get(
                                'ip') + ':' + itemProxyInfo.get('port')
                            ProxyPool.allProxy.get('China').get('https').append(itemProxy)
                    elif response.status_code == 429:
                        raise Exception('⚠️请求次数过多请稍后重试\n')
                    else:
                        raise Exception('❌️请求失败\n')
                except requests.exceptions.ConnectTimeout:
                    print(f'❌连接超时：{baseUrl}\n')
                except requests.exceptions.ReadTimeout:
                    print(f'❌读取超时：{baseUrl}\n')
                except Exception as e:
                    print(f'❌️API未知错误：{baseUrl}\n')
                    print(e)

            _getHttpsProxys()
            _getHttpProxys()

    # 云代理
    class YunProxyPool:
        NAME = '云代理'
        INDEXURL = 'http://www.ip3366.net/free/'
        _PARAMS = '?stype=1&page='
        try:
            _indexCode = requests.get(INDEXURL).content
            _indexSoup = BeautifulSoup(_indexCode, 'html.parser')
        except:
            raise Exception(NAME + '：获取网页首页源代码失败')
        try:
            LASTPAGE = int(_indexSoup.select_one('#listnav a:nth-last-of-type(3)').get_text())
        except:
            raise Exception(NAME + '：获取最后页数失败')

        # 获取单页代理
        def _getOnePageProxys(self, soup, allProxys):
            for _ in soup.select('table tbody tr'):
                itemProxyListInfo = _.find_all('td')
                retainField = [1, 2, 4]
                filterItemProxyListInfo = [item.get_text() for index, item in enumerate(itemProxyListInfo, 1) if
                                           index in retainField]
                filterItemProxyListInfo.insert(0, filterItemProxyListInfo.pop().lower())
                itemProxy = ':'.join(filterItemProxyListInfo)
                proxyType = filterItemProxyListInfo[0]
                if proxyType == 'http':
                    allProxys.get('China').get('http').append(itemProxy[:5] + '//' + itemProxy[5:])
                elif proxyType == 'https':
                    allProxys.get('China').get('https').append(itemProxy[:6] + '//' + itemProxy[6:])

        # 获取所有代理
        def getAllProxys(self):
            for page in range(1, ProxyPool.YunProxyPool.LASTPAGE + 1):
                if page == 1:
                    self._getOnePageProxys(ProxyPool.YunProxyPool._indexSoup, ProxyPool.allProxy)
                else:
                    try:
                        itemPageCode = requests.get(
                            ProxyPool.YunProxyPool.INDEXURL + ProxyPool.YunProxyPool._PARAMS + str(page)).content
                        itemPageSoup = BeautifulSoup(itemPageCode, 'html.parser')
                        self._getOnePageProxys(itemPageSoup, ProxyPool.allProxy)
                    except:
                        raise Exception(ProxyPool.YunProxyPool.NAME + f'：获取网页第{page}页源代码失败')


if __name__ == '__main__':
    print(ProxyPool.main(perType=2,total=5))
    ProxyPool.export(fmt='json')
    # a = ProxyPool.SixSixProxyPool()
    # a.getAllProxys()
    # b = ProxyPool.ZdyProxyPool()
    # b.getAllProxys()
    # c = ProxyPool()
    # print(c.availableObject)
    # c.checkAllProxy(2)
    # print('所有代理：' + str(c.allProxy))
    # print('可用代理：' + str(c.availableProxy))
