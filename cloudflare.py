"""
CloudFlare dns tools.
"""
from copy import deepcopy
import sys
import argparse
import json
import time
import urllib.parse
import requests

class CloudFlareError(Exception):
    """
    Base exception for CloudFlare module
    """
    pass


class ZoneNotFound(CloudFlareError):
    """
    Raised when a specified zone is not found from CloudFlare
    """
    pass


class RecordNotFound(CloudFlareError):
    """
    Raised when a specified record is not found for a zone from CloudFlare
    """
    pass

class CloudFlare:
    """
    CloudFlare dns tools class
    """
    api_url = 'https://api.cloudflare.com/client/v4/zones/'

    email = ''

    api_key = ''

    proxied = False

    headers = None

    domain = None

    zone = None

    dns_records = None

    http_proxies_default = {
        "http_proxy": "",
        "https_proxy": ""
    }

    public_ip_finder = (
        'https://api64.ipify.org/',
        'https://ip.seeip.org',
        'http://api.ip.sb/ip'
    )

    def __init__(self, email: str, api_key: str, domain: str, proxied: bool = False, **kwargs):
        """
        Initialization. It will set the zone information of the domain for operation.
        It will also get dns records of the current zone.
        :param email:
        :param api_key:
        :param domain:
        :param proxied:
        """
        self.email = email
        self.api_key = api_key
        self.domain = domain
        self.proxied = proxied
        self.headers = {
            'X-Auth-Key': api_key,
            'X-Auth-Email': email
        }
        # minimum ttl is 60 seconds
        # set ttl for basic record creatation or record update
        self.ttl = 300
        if kwargs.get('ttl') and isinstance(kwargs['ttl'], int) and kwargs['ttl'] >= 60:
            self.ttl = kwargs['ttl']
        # set proxies for connection between local to cloudflare
        self.http_proxies = CloudFlare.__get_http_proxies__(
            copy_proxy=True, **kwargs)
        self.__setup_zone__()

    @classmethod
    def __get_http_proxies__(cls, copy_proxy: bool = True, **kwargs):
        """
        create http proxies for request, it's a class method
        :param copy_proxy: if it's True: http_proxy will be same with https_proxy when just https_proxy is provoied; https_proxy will be same with http_proxy when just http_proxy is provoied. If it's False, no copy between http_proxy and https_proxy, if either http_proxy or https_proxy is provoided.
        :param kwargs: http_proxy and https_proxy will stored in it.
        """
        t_proxies = deepcopy(cls.http_proxies_default)
        if kwargs.get('http_proxy') and isinstance(kwargs['http_proxy'], str) and len(kwargs['http_proxy']) > 0:
            t_proxies["http_proxy"] = kwargs['http_proxy']
        if kwargs.get('https_proxy') and isinstance(kwargs['https_proxy'], str) and len(kwargs['https_proxy']) > 0:
            t_proxies["https_proxy"] = kwargs['https_proxy']
        if copy_proxy:
            if len(t_proxies["http_proxy"]) == 0:
                t_proxies["http_proxy"] = t_proxies["https_proxy"]
            if len(t_proxies["https_proxy"]) == 0:
                t_proxies["https_proxy"] = t_proxies["http_proxy"]
        return t_proxies

    def __set_http_proxies__(self, **kwargs):
        t_http_proxies = CloudFlare.__get_http_proxies__(
            copy_proxy=False, **kwargs)
        if len(t_http_proxies['http_proxy']) > 0:
            self.http_proxies['http_proxy'] = t_http_proxies['http_proxy']
        if len(t_http_proxies['https_proxy']) > 0:
            self.http_proxies['https_proxy'] = t_http_proxies['https_proxy']

    def __request__(self, url, method, data=None, **kwargs):
        """
        The requester shortcut to submit a http request to CloutFlare
        :param url:
        :param method:
        :param data:
        :return:
        """
        t_http_proxies = CloudFlare.__get_http_proxies__(
            copy_proxy=True, **kwargs)
        method = getattr(requests, method)
        t_rsp = method(
            url,
            headers=self.headers,
            json=data,
            proxies=t_http_proxies,
            timeout=10
        )
        if t_rsp.status_code != 200:
            print(t_rsp)
            raise requests.HTTPError(t_rsp.reason)
        t_result = json.loads(t_rsp.text)
        if "success" not in t_result or not t_result["success"]:
            return False, t_result
        return True, t_result

    @classmethod
    def get_zone_name(domain: str, domain_class=-1):
        # split and strip
        domain_segments = domain.split(".")
        domain_segments = [domain.lower().strip()
                           for domain in domain_segments]
        domain_segments = [
            domain for domain in domain_segments if len(domain) > 0]
        # Join the last two segments of the domain name.
        t_len = len(domain_segments)
        if t_len < 2:
            return 0, None
        if domain_class <= 0:
            domain_class = t_len
        elif domain_class <= 2:
            domain_class = 2
        if t_len < domain_class:
            domain_class = t_len
        return domain_class, ".".join(domain_segments[(t_len - domain_class):])

    @classmethod
    def get_full_name(domain: str, zone_name: str):
        domain = domain.strip().strip(".").strip().lower()
        zone_name = zone_name.strip().strip(".").strip().lower()
        if len(domain) == 0 or len(zone_name) == 0:
            return None
        if domain == zone_name:
            return domain
        if domain.endswith("." + zone_name):
            return domain
        return domain + "." + zone_name

    def __get_full_name__(self, domain: str):
        return CloudFlare.get_full_name(domain, self.zone["name"])

    def __setup_zone__(self, **kwargs):
        """
        Setup zone for current domain.
        It will also setup the dns records of the zone
        :return:
        """
        # Initialize current zone
        t_succ, t_result_dict = self.__request__(
            self.api_url, 'get', None, **kwargs)
        if not t_succ or 'result' not in t_result_dict:
            raise CloudFlareError(
                "Failed to get zone: \"{self.domain}\", \'{t_result_dict}\'".format())
        for zone in t_result_dict['result']:
            zone_name = zone['name']
            if self.domain == zone_name or self.domain.endswith("." + zone_name):
                self.zone = zone
                break
        if not self.zone:
            raise ZoneNotFound('Cannot find zone information for the domain {domain}.'
                               .format(domain=self.domain))
        # Initialize dns_records of current zone
        t_succ, t_result_dict = self.__request__(
            self.api_url + zone['id'] + '/dns_records', 'get', None, **kwargs)
        if not t_succ or 'result' not in t_result_dict:
            raise CloudFlareError(
                f"Failed to get dns records for zone: \"{self.domain}\", \'{t_result_dict}\'")
        self.dns_records = t_result_dict['result']

    def __create_one_record__(self, dns_type, name, t_result_dict, **kwargs):
        """
        Create a dns record
        :param dns_type:
        :param name:
        :param content:
        :param kwargs:
        :return:
        """
        data = {
            'type': dns_type,
            'name': name,
            'content': t_result_dict
        }
        if kwargs.get('ttl') and kwargs['ttl'] != 1:
            data['ttl'] = kwargs['ttl']
        else:
            data['ttl'] = self.ttl
        if kwargs.get('proxied') and isinstance(kwargs['proxied'], bool):
            data['proxied'] = kwargs['proxied']
        else:
            data['proxied'] = self.proxied
        t_succ, t_result_dict = self.__request__(
            self.api_url + self.zone['id'] + '/dns_records',
            'post',
            data=data,
            **kwargs
        )
        if not t_succ or 'result' not in t_result_dict:
            raise CloudFlareError(
                f"Failed to create \"{name}\" records for zone: \"{self.domain}\", \'{t_result_dict}\'")
        self.dns_records.append(t_result_dict['result'])
        return t_result_dict['result']

    def __update_record_by_id__(self, record_id, dns_type, name, content, **kwargs):
        """
        Update dns record by record id
        :param dns_type:
        :param name:
        :param content:
        :param kwargs:
        :return:
        """
        name = name.lower()
        dns_type = dns_type.upper()
        # strip and remove duplicated item
        content_list = [str(content).strip().lower()
                        for content in content_list]
        content_list = list(set(content_list))
        data = {
            'type': dns_type,
            'name': name,
            'content': content
        }
        if kwargs.get('ttl') and kwargs['ttl'] != 1:
            data['ttl'] = kwargs['ttl']
        if kwargs.get('proxied') and isinstance(kwargs['proxied'], bool):
            data['proxied'] = kwargs['proxied']
        else:
            data['proxied'] = self.proxied
        t_succ, t_result_dict = self.__request__(
            urllib.parse.urljoin(
                self.api_url, self.zone['id'] + '/dns_records/' + record_id),
            'put',
            data=data,
            **kwargs
        )
        if not t_succ or 'result' not in t_result_dict:
            raise CloudFlareError(
                f"Failed to update \"{name}: {dns_type}, {content}\" records for zone: \"{self.domain}\", \'{t_result_dict}\'")
        return t_result_dict['result']

    def __delete_record_by_id__(self, record_id, **kwargs):
        """
            Delete a dns record
            :param record_id:
            :return:
            """
        for t_index in range(len(self.dns_records)):
            if self.dns_records[t_index]['id'] == record_id:
                t_succ, t_result_dict = self.__request__(
                    urllib.parse.urljoin(
                        self.api_url, self.zone['id'] + '/dns_records/' + record_id),
                    'delete',
                    None,
                    **kwargs
                )
                # failed to perford delete-action, rase an error
                if not t_succ:
                    raise CloudFlareError(
                        f"Failed to delete dns record id - \"{record_id}\" records for zone: \"{self.domain}\", \'{t_result_dict}\'")
                del self.dns_records[t_index]
                return True, t_result_dict
        raise CloudFlareError(f"Can't find record id - \"{record_id}\"")

    def refresh(self, **kwargs):
        """
        Shortcut for setup zone
        :return:
        """
        self.__set_http_proxies__(**kwargs)
        self.__setup_zone__(**kwargs)

    def get_records(self, name, dns_type, refresh=False, **kwargs):
        """
        Get a dns record
        :param dns_type:
        :param name:
        :return:
        """
        # set proxies if refresh will be performed
        name = name.lower()
        dns_type = dns_type.upper()
        if refresh:
            self.__set_http_proxies__(**kwargs)
        try:
            records = [record for record in self.dns_records
                       if record['type'] == dns_type and record['name'] == name]
        except IndexError:
            raise RecordNotFound(
                'Cannot find the specified dns record in domain {domain}'
                .format(domain=name))
        return records

    def create_records(self, name, dns_type, content_list, **kwargs):
        """
        Create a dns record
        :param dns_type:
        :param name:
        :param content_list:
        :param kwargs:
        :return:
        """
        # reset proxies
        self.__set_http_proxies__(**kwargs)
        name = name.lower()
        dns_type = dns_type.upper()
        # strip and remove duplicated item
        content_list = [str(content).strip().lower()
                        for content in content_list]
        content_list = list(set(content_list))
        t_records = self.get_records(name, dns_type)
        # check records exist or not,
        #    keep the content and its record id.
        t_ext_dict = {}
        t_non_ext_content = []
        for t_content in content_list:
            t_found = False
            for t_record in t_records:
                t_ext_dict[(name, dns_type, t_content)] = t_record
                t_found = True
                break
            if not t_found:
                t_non_ext_content.append(t_content)
        # do create for non-exist records
        t_created_dict = {}
        for t_content in t_non_ext_content:
            t_result = self.__create_one_record__(
                dns_type, name, t_content, **kwargs)
            t_created_dict[(name, dns_type, t_content)] = t_result
            time.sleep(0.5)
        return t_created_dict, t_ext_dict

    def delete_records(self, name, dns_type, content_list: list = [], **kwargs):
        """
        Delete a dns record
        :param dns_type:
        :param name:
        :return:
        """
        name = name.lower()
        dns_type = dns_type.upper()
        # strip and remove duplicated item
        content_list = [str(content).strip().lower()
                        for content in content_list]
        content_list = list(set(content_list))
        t_index = 0
        t_d_dict = {}
        while t_index < len(self.dns_records):
            t_record = self.dns_records[t_index]
            # it's not the target, t_index should be increased
            if not(t_record['type'] == dns_type and t_record['name'] == name):
                if len(content_list) == 0 or not t_record['content'] in content_list:
                    t_index += 1
                    continue
            # delete from remote server
            _, t_result = self.__delete_record_by_id__(
                t_record['id'], **kwargs)
            t_d_dict[(name, dns_type, t_record["content"])] = t_result
            time.sleep(0.5)
        return t_d_dict

    def update_records(self, name, dns_type, content_list: list, **kwargs):
        """
        Update dns record
        :param dns_type:
        :param name:
        :param content:
        :param kwargs:
        :return:
        """
        name = name.lower()
        dns_type = dns_type.upper()
        # strip and remove duplicated item
        content_list = [str(content).strip().lower()
                        for content in content_list]
        content_list = list(set(content_list))
        t_content_for_loop = [item for item in content_list]
        t_i_old_r = 0
        t_updated_C = []
        t_created_C = []
        t_deleted_C = []
        t_updated_list = {}
        t_created_list = {}
        t_deleted_list = {}
        # loop form self.dns_records
        while t_i_old_r < len(self.dns_records) and len(t_content_for_loop) > 0:
            t_o_record = self.dns_records[t_i_old_r]
            # check it's type and name, if its not target, skip and t_i_old_r rolling
            if not(t_o_record['type'] == dns_type and t_o_record['name'] == name):
                t_i_old_r += 1
                continue
            # loop for t_content_for_loop
            t_i_new_c = 0
            t_found = False
            # if found, it should be update
            # if doesn't, pop the first one from t_content_for_loop to update
            while t_i_new_c < len(t_content_for_loop):
                t_content = t_content_for_loop[t_i_new_c]
                if t_content == t_o_record["content"]:
                    t_found = True
                    t_updated_C.append(t_content)
                    del t_content_for_loop[t_i_new_c]
                    break
                t_i_new_c += 1
            if t_found:
                t_content = t_updated_C[-1]
            else:
                t_content = t_content_for_loop[0]
                t_updated_C.append(t_content)
                del t_content_for_loop[0]
            # update the record
            t_result = self.__update_record_by_id__(
                t_o_record['id'], dns_type, name, t_content, **kwargs)
            self.dns_records[t_i_old_r] = t_result
            t_updated_list[(
                name, dns_type, t_content)] = t_result
            # keep rolling
            t_i_old_r += 1
            time.sleep(0.5)
        # no more new recors for update, delete from original records list and remote if it have more the same type and name records
        if t_i_old_r < len(self.dns_records):
            while t_i_old_r < len(self.dns_records):
                t_o_record = self.dns_records[t_i_old_r]
                if t_o_record['type'] == dns_type and t_o_record['name'] == name:
                    _, t_result = self.__delete_record_by_id__(
                        t_o_record['id'], **kwargs)
                    t_deleted_list[(
                        name, dns_type, t_o_record['content'])] = t_result
                    t_deleted_C.append(t_o_record["content"])
                    time.sleep(0.5)
                    continue
                t_i_old_r += 1
                continue
        # we have more records to update, them are need to add.
        if len(t_content_for_loop) > 0:
            t_results_created, t_results_exists = self.create_records(
                name, dns_type, t_content_for_loop, **kwargs)
            if len(t_results_exists) > 0:
                print(t_results_created)
                print(t_results_exists)
                raise CloudFlareError(
                    "There should not be records which already exists!")
            t_created_C.extend(t_content_for_loop)
            t_created_list = t_results_created
        return t_updated_list, t_created_list, t_deleted_list


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError(
            'BooleTEMPOUTBOUNDVNEXTan value expected.')


def print_logs(t_u: list, t_c: list, t_d: list, t_k: list):
    if len(t_u) > 0:
        print("Update for:")
        for t_i in t_u.values():
            print(t_i)
    if len(t_c) > 0:
        print("Create for:")
        for t_i in t_c.values():
            print(t_i)
    if len(t_d) > 0:
        print("Delete for:")
        for t_i in t_d.keys():
            print(f"\"{t_i[0]}\" - \"{t_i[1]}\" - \"{t_i[2]}\"")
            print(t_d[t_i])
    if len(t_k) > 0:
        print("Keep for:")
        for t_i in t_k.keys():
            print(f"\"{t_i[0]}\" - \"{t_i[1]}\" - \"{t_i[2]}\"")
            print(t_d[t_i])


def main():
    print("cloudflare-ddns a DDNS helper for Cloudflare.")
    print("Create, delete or update dns record for dns type \"A|AAAA|CNAME\".")
    print("")
    parser = argparse.ArgumentParser()
    parser.add_argument("-e", '--email', action="store",
                        dest="email", type=str, help="Email for your cloudflare account")
    parser.add_argument("-k", '--api-key', action="store",
                        dest="api_key", type=str, help="API Key of your cloudflare account")
    cmd_group = parser.add_mutually_exclusive_group()
    cmd_group.add_argument('-u', '--update-record', action="store",
                           dest="u_domain", type=str, help="domain for update")
    cmd_group.add_argument('-a', '--add-record', action="store",
                           dest="a_domain", type=str, help="domain for add")
    cmd_group.add_argument('-d', '--delete-record', action="store",
                           dest="d_domain", type=str, help="domain for delete")
    parser.add_argument("-4", '--ipv4', action="append",
                        dest="ipv4_addr", type=str, help="IPv4 address for action")
    parser.add_argument("-6", '--ipv6', action="append",
                        dest="ipv6_addr", type=str, help="IPv6 address for action")
    parser.add_argument("-c", '--cname', action="store",
                        dest="cname", type=str, help="cname for action")
    parser.add_argument('--dns-type', action="append",
                        dest="dns_type", type=str, help="dns type for delete")
    parser.add_argument("-t", '--ttl', action="store", default=60,
                        dest="ttl", type=int, help="ttl for record")
    parser.add_argument('--proxied', action="store", default=False,
                        dest="proxied", type=str2bool, help="It should be proxied")
    args = parser.parse_args()
    if not args.email or len(args.email) == 0:
        print("No email!")
        sys.exit(1)
    if not args.api_key or len(args.api_key) == 0:
        print("No API Key!")
        sys.exit(1)
    t_domain = ""
    if args.u_domain and len(args.u_domain) > 0:
        t_domain = args.u_domain
    if args.a_domain and len(args.a_domain) > 0:
        t_domain = args.a_domain
    if args.d_domain and len(args.d_domain) > 0:
        t_domain = args.d_domain
    if not t_domain or len(t_domain) == 0:
        print("No domain!")
        sys.exit(1)
    if (not args.ipv4_addr or len(args.ipv4_addr) == 0) and \
            (not args.ipv6_addr or len(args.ipv6_addr) == 0) and \
            (not args.cname or len(args.cname) == 0):
        # for add or update
        if args.u_domain or args.a_domain:
            print("No record for update!")
            sys.exit(1)
        # for delete
        elif not args.dns_type or len(args.dns_type) == 0:
            print(
                "Neither record (-4|-6|-c) nor dns type (--dns-type) is provided for deletion!")
            sys.exit(1)
    if args.d_domain and len(args.d_domain) > 0 and args.dns_type and len(args.dns_type) > 0:
        for t_type in args.dns_type:
            if t_type not in ("A", "AAAA", "CNAME"):
                print(
                    "DNS type (--dns-type) should be \"A\", \"AAAA\" or \"CNAME\"!")
                sys.exit(1)
    cf = CloudFlare(email=args.email, api_key=args.api_key, domain=t_domain)
    if args.u_domain:
        if args.ipv4_addr and len(args.ipv4_addr) > 0:
            t_u, t_c, t_d = cf.update_records("A", t_domain, args.ipv4_addr,
                                              ttl=args.ttl, proxied=args.proxied)
            print_logs(t_u, t_c, t_d, [])
        if args.ipv6_addr and len(args.ipv6_addr) > 0:
            t_u, t_c, t_d = cf.update_records("AAAA", t_domain, args.ipv6_addr,
                                              ttl=args.ttl, proxied=args.proxied)
            print_logs(t_u, t_c, t_d, [])
        if args.cname and len(args.cname) > 0:
            t_u, t_c, t_d = cf.update_records("CNAME", t_domain, [args.cname],
                                              ttl=args.ttl, proxied=args.proxied)
            print_logs(t_u, t_c, t_d, [])
    if args.a_domain:
        if args.ipv4_addr and len(args.ipv4_addr) > 0:
            t_c, t_k = cf.create_records(t_domain, "A", args.ipv4_addr,
                                         ttl=args.ttl, proxied=args.proxied)
            print_logs([], t_c, [], t_k)
        if args.ipv6_addr and len(args.ipv6_addr) > 0:
            t_c, t_k = cf.create_records(t_domain, "AAAA", args.ipv6_addr,
                                         ttl=args.ttl, proxied=args.proxied)
            print_logs([], t_c, [], t_k)
        if args.cname and len(args.cname) > 0:
            t_c, t_k = cf.create_records(t_domain, "CNAME", [args.cname],
                                         ttl=args.ttl, proxied=args.proxied)
            print_logs([], t_c, [], t_k)
    if args.d_domain:
        if args.ipv4_addr and len(args.ipv4_addr) > 0:
            t_d = cf.delete_records(t_domain, "A", args.ipv4_addr,
                                    ttl=args.ttl, proxied=args.proxied)
            print_logs([], [], t_d, [])
        if args.ipv6_addr and len(args.ipv6_addr) > 0:
            t_d = cf.delete_records(t_domain, "AAAA", args.ipv6_addr,
                                    ttl=args.ttl, proxied=args.proxied)
            print_logs([], [], t_d, [])
        if args.cname and len(args.cname) > 0:
            t_d = cf.delete_records(t_domain, "CNAME", [args.cname],
                                    ttl=args.ttl, proxied=args.proxied)
            print_logs([], [], t_d, [])
        if args.dns_type:
            for t_type in args.dns_type:
                t_d = cf.delete_records(t_domain, t_type, [],
                                        ttl=args.ttl, proxied=args.proxied)
                print_logs([], [], t_d, [])


if __name__ == "__main__":
    main()
