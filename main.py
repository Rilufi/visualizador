import json
import logging
import concurrent.futures
import random
import requests
import pandas as pd
import itertools
from sources import SOURCES

logging.basicConfig(
    format='%(asctime)s %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

HEADERS = {
    'User-Agent': f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.{random.randint(0, 9999)} Safari/537.{random.randint(0, 99)}'  # noqa
}
MAX_WORKERS = 300
AVAILABLE_PROXIES = []
USABLE_PROXIES = []


class ProxyItem:
    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.proxy = {
            'http': f'http://{self.ip}:{self.port}',
            'https': f'http://{self.ip}:{self.port}'
        }
        self.is_valid = self.check()
        logging.info(f'Checking Proxy: {self.__dict__}')

    def check(self) -> bool:
        global USABLE_PROXIES
        try:
            requests.get(
                url='https://ipecho.net/plain',
                proxies=self.proxy,
                timeout=5
            )
            USABLE_PROXIES.append({'ip': self.ip, 'port': self.port})
            return True
        except:
            return False


class Scraper:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.url: str = self.config.get('url')
        self.method: str = self.config.get('method')
        self.parser: dict = self.config.get('parser', {})
        self.parser_type: str = list(self.parser.keys())[0]
        self.parser_config: dict = list(self.parser.values())[0]
        self.request_timeout = 10
        self.is_succeed = False
        logging.info(f'Source: {self.config.get("id")} has started.')

    def crawl(self) -> requests.Response:
        return requests.request(
            method=self.method,
            url=self.url,
            headers=HEADERS,
            timeout=self.request_timeout
        )

    def parse(self) -> list:
        proxies = []

        try:
            response = self.crawl()
            if self.parser_type == "pandas":
                df = pd.read_html(response.content)[self.parser_config.get('table_index', 0)]
                for x in range(0, len(df)):
                    if not self.parser_config.get('combined', None):
                        ip = str(df.loc[df.index[x], self.parser_config.get('ip')]).strip()
                        port = int(df.loc[df.index[x], self.parser_config.get('port')])
                        proxies.append({'ip': ip, 'port': port})
                    else:
                        combined: str = df.loc[df.index[x], self.parser_config.get('combined')]
                        if len(combined.split(':')) == 2:
                            ip = combined.split(':')[0].strip()
                            port = int(combined.split(':')[1])
                            proxies.append({'ip': ip, 'port': port})

            if self.parser_type == "json":
                data = response.json()[self.parser_config.get('data')]
                for x in data:
                    proxies.append({
                        'ip': str(x[self.parser_config.get('ip', '')]).strip(),
                        'port': int(x[self.parser_config.get('port', '')])
                    })

            if self.parser_type == "txt":
                data = str(response.content, encoding='utf-8')
                for x in data.split('\n'):
                    if len(x.split(':')) == 2:
                        proxies.append({
                            'ip': x.split(':')[0].strip(),
                            'port': int(x.split(':')[1].strip())
                        })
            self.is_succeed = True
        except:
            self.is_succeed = False
            logging.error(f'Source: {self.config.get("id")}', exc_info=True)

        return proxies

    def run(self) -> bool:
        global AVAILABLE_PROXIES
        proxies = self.parse()

        if len(proxies) > 0:
            AVAILABLE_PROXIES = itertools.chain(AVAILABLE_PROXIES, proxies)

        return self.is_succeed, len(proxies)


def geolocation_info(batch_ips) -> list:
    try:
        def batch_request(data):
            response = requests.post("http://ip-api.com/batch", json=data, timeout=120)
            if response.status_code == 200:
                return response.json()
            return None

        batch_limit = 100
        ip_api_results = []
        list_of_ip = [x["ip"] for x in batch_ips]
        for start in range(0, len(list_of_ip), batch_limit):
            batch = list_of_ip[start: start + batch_limit]
            geo = batch_request(batch)
            if geo:
                ip_api_results = itertools.chain(ip_api_results, geo)

        proxy_dict = dict([(x["ip"], x["port"]) for x in batch_ips])
        model = []
        for x in list(ip_api_results):
            ip = x['query']
            port = proxy_dict[ip]
            model.append({"ip": ip, "port": port, "geolocation": x})

        return model
    except:
        return []


def what_is_my_ip():
    logging.info(f"Current IP Address: {requests.get(url='http://ipecho.net/plain').text}")


def main():
    global MAX_WORKERS
    source_states = []

    for config in SOURCES:
        scraper = Scraper(config)
        succeed, count = scraper.run()
        source_states.append({
            "id": config['id'],
            "url": config['url'],
            "succeed": succeed,
            "count": count
        })

    list_of_proxies = list(AVAILABLE_PROXIES)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        worker_to_queue = {
            executor.submit(ProxyItem, x['ip'], x['port']): x for x in list_of_proxies
        }
        for worker in concurrent.futures.as_completed(worker_to_queue):
            worker_to_queue[worker]

    with open("data.json", "w") as f:
        json.dump(USABLE_PROXIES, f, indent=4)

    with open("data.txt", "w") as f:
        for x in USABLE_PROXIES:
            f.write(f'{x.get("ip")}:{x.get("port")}\n')

    geolocations = geolocation_info(USABLE_PROXIES)
    if len(geolocations) > 0:
        with open("data-with-geolocation.json", "w") as f:
            json.dump(geolocations, f, indent=4)

    logging.info(f'{len(list_of_proxies)} proxies are crawled.')
    logging.info(f'{len(USABLE_PROXIES)} proxies are usable.')



if __name__ == '__main__':
    main()
    what_is_my_ip()

"""
MIT License

Copyright (c) 2021-2023 MShawon

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, wait
from glob import glob
from time import sleep

import requests
from fake_headers import Headers

os.system("")


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


print(bcolors.OKGREEN + """
  ____                                    
 |  _ \ _ __ _____  ___   _               
 | |_) | '__/ _ \ \/ / | | |              
 |  __/| | | (_) >  <| |_| |              
 |_|   |_|_ \___/_/\_\\__, |_             
      / ___| |__   ___|___/| | _____ _ __ 
     | |   | '_ \ / _ \/ __| |/ / _ \ '__|
     | |___| | | |  __/ (__|   <  __/ |   
      \____|_| |_|\___|\___|_|\_\___|_|   
                                          
""" + bcolors.ENDC)

print(bcolors.OKCYAN + """
[ GitHub : https://github.com/MShawon/YouTube-Viewer ]
""" + bcolors.ENDC)


checked = {}
cancel_all = False


def backup():
    try:
        shutil.copy('GoodProxy.txt', 'ProxyBackup.txt')
        print(bcolors.WARNING +
              'GoodProxy.txt backed up in ProxyBackup.txt' + bcolors.ENDC)
    except Exception:
        pass

    print('', file=open('GoodProxy.txt', 'w'))


def clean_exe_temp(folder):
    try:
        temp_name = sys._MEIPASS.split('\\')[-1]
    except Exception:
        temp_name = None

    for f in glob(os.path.join('temp', folder, '*')):
        if temp_name not in f:
            shutil.rmtree(f, ignore_errors=True)


def load_proxy():
    proxies = []

#    filename = input(bcolors.OKBLUE +
#                     'Enter your proxy file name: ' + bcolors.ENDC)

#    if not os.path.isfile(filename) and filename[-4:] != '.txt':
 #       filename = f'{filename}.txt'
    filename = 'data.txt'
    
    try:
        with open(filename, encoding="utf-8") as fh:
            loaded = [x.strip() for x in fh if x.strip() != '']
    except Exception as e:
        print(bcolors.FAIL + str(e) + bcolors.ENDC)
        input('')
        sys.exit()

    for lines in loaded:
        if lines.count(':') == 3:
            split = lines.split(':')
            lines = f'{split[2]}:{split[-1]}@{split[0]}:{split[1]}'
        proxies.append(lines)

    return proxies


def main_checker(proxy_type, proxy, position):
    if cancel_all:
        raise KeyboardInterrupt

    checked[position] = None

    try:
        proxy_dict = {
            "http": f"{proxy_type}://{proxy}",
            "https": f"{proxy_type}://{proxy}",
        }

        header = Headers(
            headers=False
        ).generate()
        agent = header['User-Agent']

        headers = {
            'User-Agent': f'{agent}',
        }

        response = requests.get(
            'https://www.youtube.com/', headers=headers, proxies=proxy_dict, timeout=30)
        status = response.status_code

        if status != 200:
            raise Exception(status)

        print(bcolors.OKBLUE + f"Worker {position+1} | " + bcolors.OKGREEN +
              f'{proxy} | GOOD | Type : {proxy_type} | Response : {status}' + bcolors.ENDC)

        print(f'{proxy}|{proxy_type}', file=open('GoodProxy.txt', 'a'))

    except Exception as e:
        try:
            e = int(e.args[0])
        except Exception:
            e = ''
        print(bcolors.OKBLUE + f"Worker {position+1} | " + bcolors.FAIL +
              f'{proxy} | {proxy_type} | BAD | {e}' + bcolors.ENDC)
        checked[position] = proxy_type


def proxy_check(position):
    sleep(2)
    proxy = proxy_list[position]

    if '|' in proxy:
        splitted = proxy.split('|')
        main_checker(splitted[-1], splitted[0], position)
    else:
        main_checker('http', proxy, position)
        if checked[position] == 'http':
            main_checker('socks4', proxy, position)
        if checked[position] == 'socks4':
            main_checker('socks5', proxy, position)


def main():
    global cancel_all

    cancel_all = False
    pool_number = [i for i in range(total_proxies)]

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(proxy_check, position)
                   for position in pool_number]
        done, not_done = wait(futures, timeout=0)
        try:
            while not_done:
                freshly_done, not_done = wait(not_done, timeout=5)
                done |= freshly_done
        except KeyboardInterrupt:
            print(bcolors.WARNING +
                  'Hold on!!! Allow me a moment to finish the running threads' + bcolors.ENDC)
            cancel_all = True
            for future in not_done:
                _ = future.cancel()
            _ = wait(not_done, timeout=None)
            raise KeyboardInterrupt
        except IndexError:
            print(bcolors.WARNING + 'Number of proxies are less than threads. Provide more proxies or less threads. ' + bcolors.ENDC)


if __name__ == '__main__':

    clean_exe_temp(folder='proxy_check')
    backup()

    try:
        threads = int(
            input(bcolors.OKBLUE+'Threads (recommended = 100): ' + bcolors.ENDC))
    except Exception:
        threads = 100

    proxy_list = load_proxy()
    # removing empty & duplicate proxies
    proxy_list = list(set(filter(None, proxy_list)))

    total_proxies = len(proxy_list)
    print(bcolors.OKCYAN +
          f'Total unique proxies : {total_proxies}' + bcolors.ENDC)

    try:
        main()
    except KeyboardInterrupt:
        sys.exit()
