#!/usr/bin/env python3
"""
东方财富稳定取数模块。
背景：本机挂了 Clash 代理(127.0.0.1:7890)。
  - 代理对东财 push2/push2his API 域名是 REJECT(ProxyError)；
  - 直连时东财各 API 域名被 DNS 污染：解析到的多数 IP(如 117.184.38.143/14.103.x)
    会直接 reset 连接；只有 IP 101.226.30.136 这一节点稳定可用，且它同时服务
    行情(push2)与历史K线(push2his)。
解决：清空代理 + trust_env=False + 把东财 API 域名强制解析到该可用 IP(DNS pinning)。
  注意：保持 SNI=原域名、verify=True，证书是 *.eastmoney.com 通配，TLS 仍正常校验，
  不削弱安全（不用 verify=False、不伪装 Host）。

用法:
  from em_fetch import quotes, secid, kline
  data = quotes({'蔚蓝锂芯':'0.002245', '亿纬锂能':'0.300014'})
  ks = kline('1.600160', 120)   # 日K前复权
"""
import os, time, json, socket
import requests

for _k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY','all_proxy','ALL_PROXY']:
    os.environ.pop(_k, None)

# ---- DNS pinning：绕过东财 API 域名的 DNS 污染 ----
# 实测稳定可用的东财 CDN 节点(同时供 push2 行情 + push2his 历史K线)。
# 若将来失效，按 README 思路重新探测一个可用 IP 替换即可。
_GOOD_IP = '101.226.30.136'
_PINNED = {'push2his.eastmoney.com', 'push2.eastmoney.com',
           'push2delay.eastmoney.com', 'push2hisdelay.eastmoney.com'}
_orig_getaddrinfo = socket.getaddrinfo
def _pinned_getaddrinfo(host, *args, **kwargs):
    return _orig_getaddrinfo(_GOOD_IP if host in _PINNED else host, *args, **kwargs)
socket.getaddrinfo = _pinned_getaddrinfo

_S = requests.Session()
_S.trust_env = False
_H = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/125.0 Safari/537.36',
      'Referer': 'https://quote.eastmoney.com/', 'Accept': '*/*'}

# 域名已 DNS-pin 到可用 IP，行情与 K线均稳定可取
QUOTE_HOSTS = ['push2delay.eastmoney.com', 'push2.eastmoney.com']
KLINE_HOSTS = ['push2his.eastmoney.com']

_FIELDS = 'f43,f44,f45,f46,f60,f48,f50,f168,f162,f167,f116,f170,f171,f137'


def secid(code):
    """'600160'->'1.600160'(沪/科创/北), '000636'->'0.000636'(深/创业)"""
    code = str(code)
    if code.startswith(('5', '6', '9', '11', '15')) or code.startswith('688'):
        return '1.' + code
    if code.startswith(('8', '4', '92')):  # 北交所
        return '0.' + code
    return '0.' + code


def _get(hosts, path, params, tries=4):
    for host in hosts:
        for _ in range(tries):
            try:
                t = _S.get(f'https://{host}{path}', params=params, headers=_H, timeout=10).text.strip()
                if t.startswith('{'):
                    return json.loads(t)
            except Exception:
                time.sleep(1.5)
    return None


def quotes(name2secid):
    """批量取实时行情。返回 {name: {...}} ; 取数失败的 name 值为 None。"""
    out = {}
    for name, sid in name2secid.items():
        j = _get(QUOTE_HOSTS, '/api/qt/stock/get', {'secid': sid, 'fltt': '2', 'fields': _FIELDS})
        r = (j or {}).get('data') or {}
        if r.get('f43'):
            mv = r.get('f116') or 0
            out[name] = {
                'price': r.get('f43'), 'chg': r.get('f170'), 'open': r.get('f46'),
                'prev': r.get('f60'), 'high': r.get('f44'), 'low': r.get('f45'),
                'amp': r.get('f171'), 'vr': r.get('f50'), 'turnover': r.get('f168'),
                'amount': r.get('f48'), 'pe': r.get('f162'), 'pb': r.get('f167'),
                'mktcap_yi': round(mv / 1e8, 1) if isinstance(mv, (int, float)) else None,
                'main_net': r.get('f137'),
            }
        else:
            out[name] = None
        time.sleep(0.4)
    return out


def kline(sid, lmt=70):
    """日K(前复权)。返回 klines 列表或 None。需 Clash 放行东财 his 节点才可用。"""
    j = _get(KLINE_HOSTS, '/api/qt/stock/kline/get',
             {'secid': sid, 'klt': '101', 'fqt': '1', 'end': '20500101', 'lmt': lmt,
              'fields1': 'f1,f2,f3', 'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'})
    ks = ((j or {}).get('data') or {}).get('klines')
    return ks or None


if __name__ == '__main__':
    import sys
    watch = {'蔚蓝锂芯': '0.002245', '亿纬锂能': '0.300014', '滨化股份': '1.601678',
             '多氟多': '0.002407', '天赐材料': '0.002709', '嘉元科技': '1.688388',
             '太辰光': '0.300570', '风华高科': '0.000636'}
    d = quotes(watch)
    print(f"{'名称':<8}{'现价':>9}{'涨%':>8}{'换手%':>8}{'PE':>9}{'市值亿':>9}")
    for n in watch:
        r = d.get(n)
        if r:
            print(f"{n:<8}{str(r['price']):>9}{str(r['chg']):>8}{str(r['turnover']):>8}{str(r['pe']):>9}{str(r['mktcap_yi']):>9}")
        else:
            print(f"{n:<8}{'取数失败':>9}")
