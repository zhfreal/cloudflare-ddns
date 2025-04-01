#!/usr/bin/env python3

"""
CloudFlare dns tool
"""
try:
    from gevent import monkey

    monkey.patch_all(ssl=True)
except Exception as _:
    pass
from copy import deepcopy
import sys
import argparse
import json
import time
import urllib.parse
import requests
import re

valid_record_type = ("A", "AAAA", "CNAME")
RE_SPLITTER_WITH_WHITESPACE = re.compile(r"[;,|\s]+")


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

    api_url = "https://api.cloudflare.com/client/v4/zones/"
    email = ""
    api_key = ""
    proxied = False
    headers = None
    domain = None
    zone = None
    dns_records = {}
    # zone's value like
    # {
    #         "a.com": {
    #             "id": "12345678",
    #             "records": {
    #                 "b.a.com": {
    #                     "A": {
    #                         "1.1.1.1": "123456" // <content > : < ID >
    #                     }
    #                 }
    #             }
    #         }
    #     }
    zones = {}
    zones_list = []
    http_proxies_default = {"http_proxy": "", "https_proxy": ""}
    public_ip_finder = (
        "https://api64.ipify.org/",
        "https://ip.seeip.org",
        "http://api.ip.sb/ip",
    )
    per_page = 200

    def __init__(
            self, email: str, api_key: str, **kwargs
    ):
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
        self.headers = {"X-Auth-Key": api_key, "X-Auth-Email": email}
        # minimum ttl is 60 seconds
        # set ttl for basic record creatation or record update
        self.ttl = 300
        if kwargs.get("ttl") and isinstance(kwargs["ttl"], int) and kwargs["ttl"] >= 60:
            self.ttl = kwargs["ttl"]
        # set proxies for connection between local to cloudflare
        self.http_proxies = CloudFlare.__get_http_proxies__(
            copy_proxy=True, **kwargs)
        # self.__setup_zone__()
        self.__init_zones__()

    @classmethod
    def __get_http_proxies__(cls, copy_proxy: bool = True, **kwargs):
        """
        create http proxies for request, it's a class method
        :param copy_proxy: if it's True: http_proxy will be same
        with https_proxy when just https_proxy is provoied;
        https_proxy will be same with http_proxy when just
        http_proxy is provoied. If it's False, no copy between
        http_proxy and https_proxy, if either http_proxy or https_proxy is provoided.
        :param kwargs: http_proxy and https_proxy will stored in it.
        """
        t_proxies = deepcopy(cls.http_proxies_default)
        if (
                kwargs.get("http_proxy")
                and isinstance(kwargs["http_proxy"], str)
                and len(kwargs["http_proxy"]) > 0
        ):
            t_proxies["http_proxy"] = kwargs["http_proxy"]
        if (
                kwargs.get("https_proxy")
                and isinstance(kwargs["https_proxy"], str)
                and len(kwargs["https_proxy"]) > 0
        ):
            t_proxies["https_proxy"] = kwargs["https_proxy"]
        if copy_proxy:
            if len(t_proxies["http_proxy"]) == 0:
                t_proxies["http_proxy"] = t_proxies["https_proxy"]
            if len(t_proxies["https_proxy"]) == 0:
                t_proxies["https_proxy"] = t_proxies["http_proxy"]
        return t_proxies

    def __set_http_proxies__(self, **kwargs):
        t_http_proxies = CloudFlare.__get_http_proxies__(
            copy_proxy=False, **kwargs)
        if len(t_http_proxies["http_proxy"]) > 0:
            self.http_proxies["http_proxy"] = t_http_proxies["http_proxy"]
        if len(t_http_proxies["https_proxy"]) > 0:
            self.http_proxies["https_proxy"] = t_http_proxies["https_proxy"]

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
        method_method = getattr(requests, method)
        t_try = 0
        payload = {}
        if kwargs.get("params"):
            payload = kwargs["params"]
        while t_try < 3:
            try:
                t_rsp = method_method(
                    url,
                    headers=self.headers,
                    json=data,
                    params=payload,
                    proxies=t_http_proxies,
                    timeout=10,
                )
                if t_rsp.status_code != 200:
                    print(
                        f"Request {url} using method - {method} with header {self.headers} and data {data}, got {t_rsp}"
                    )
                    return False, requests.HTTPError(t_rsp.reason)
                t_result = json.loads(t_rsp.text)
                if "success" not in t_result or not t_result["success"]:
                    return False, t_result
                return True, t_result
            except (
                    requests.ConnectTimeout,
                    requests.ConnectionError,
                    requests.Timeout,
                    requests.ReadTimeout,
            ) as e:
                print(
                    f"Request {url} using method - {method} "
                    f"with header {self.headers} and data {data}, got {str(e)}"
                )
                print("retry!")
                t_try += 1
            except Exception as e:
                return False, e
        return False, None

    @classmethod
    def get_zone_name(cls, domain: str, domain_class=-1):
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
    def get_full_name(cls, domain: str, zone_name: str):
        domain = domain.strip().strip(".").strip().lower()
        zone_name = zone_name.strip().strip(".").strip().lower()
        if len(domain) == 0 or len(zone_name) == 0:
            return None
        if domain == zone_name:
            return domain
        if domain.endswith("." + zone_name):
            return domain
        return domain + "." + zone_name

    def __init_zones__(self, **kwargs):
        """
        Setup all zones and their records.
        self.zones like {
            "a.com": {
                "id": "12345678",
                "records": {
                    "b.a.com": {
                        "A": {
                            "1.1.1.1": "123456" // <content>: <ID>
                        }
                    }
                }
            }
        }
        :return:
        """
        page = 1
        fetched = 0
        while True:
            payload = {"page": page, "per_page": self.per_page}
            # Initialize current zone
            t_succ, t_result_dict = self.__request__(
                self.api_url, "get", None, params=payload, **kwargs
            )
            if not t_succ or "result" not in t_result_dict:
                raise CloudFlareError(f"Failed to get zone: '{t_result_dict}'")
            if "result" not in t_result_dict or len(t_result_dict["result"]) == 0:
                raise CloudFlareError(
                    "Can't list zones for you. Please check with Cloudflare!"
                )
            for zone in t_result_dict["result"]:
                self.zones[zone["name"]] = {"id": zone["id"]}
                self.zones_list.append(zone["name"])
            if "result_info" not in t_result_dict:
                raise CloudFlareError(
                    f"Failed to get zone, 'Got: \n{t_result_dict}'")
            fetched += t_result_dict["result_info"]["count"]
            total_count = t_result_dict["result_info"]["total_count"]
            if fetched >= total_count:
                break
            else:
                page += 1
        self.zones_list = sort_zones(self.zones_list)

    def __init_records_for_zone__(self, zone_name, **kwargs):
        if zone_name not in self.zones:
            raise CloudFlareError(
                f"Can't find zone {zone_name} for you. Please check with Cloudflare!"
            )
        zone_id = self.zones[zone_name]["id"]
        domain = ''
        if 'domain' in kwargs:
            domain = kwargs['domain']
        # escape when init was done
        # if (
        #         "records" in self.zones[zone_name]
        #         and len(self.zones[zone_name]["records"]) > 0
        # ):
        #     return
        if "records" not in self.zones[zone_name]:
            self.zones[zone_name]["records"] = {}
        dns_records = {}
        page = 1
        fetched = 0
        while True:
            payload = {"page": page, "per_page": self.per_page}
            t_succ, t_result_dict = self.__request__(
                self.api_url + zone_id + "/dns_records",
                "get",
                None,
                params=payload,
                **kwargs,
            )
            if not t_succ or "result" not in t_result_dict:
                raise CloudFlareError(
                    f"Failed to get dns records for zone: "
                    "\"{zone_name}\", 'Got: \n{t_result_dict}'"
                )
            for t_record in t_result_dict["result"]:
                # escape other than A AAAA CNAME
                # if not is_valid_dns_type(t_record["type"]):
                #     continue
                # escape other than domain when domain is set
                if len(domain) > 0 and not t_record["name"] == domain:
                    continue
                if t_record["name"] not in dns_records:
                    dns_records[t_record["name"]] = {}
                if t_record["type"] not in dns_records[t_record["name"]]:
                    dns_records[t_record["name"]][t_record["type"]] = {}
                if t_record["content"] not in dns_records[t_record["name"]][t_record["type"]]:
                    dns_records[t_record["name"]][t_record["type"]
                                                  ][t_record["content"]] = {}
                dns_records[t_record["name"]][t_record["type"]][t_record["content"]] = \
                    t_record["id"]
                self.dns_records[t_record["id"]] = t_record
                # dns_records[t_record["name"]
                #             ][t_record["type"]][t_record["content"]]['record'] = t_record
                # if "values" not in dns_records[t_record["name"]][t_record["type"]]:
                #     dns_records[t_record["name"]
                #                 ][t_record["type"]]["values"] = []
                # dns_records[t_record["name"]][t_record["type"]
                #                               ]["values"].append(t_record)
            if "result_info" not in t_result_dict:
                raise CloudFlareError(
                    f"Failed to get dns records for zone: "
                    "\"{zone_name}\", 'Got: \n{t_result_dict}'"
                )
            fetched += t_result_dict["result_info"]["count"]
            total_count = t_result_dict["result_info"]["total_count"]
            if fetched >= total_count:
                break
            else:
                page += 1
        self.zones[zone_name]["records"].update(dns_records)

    def __get_records_for_zone__(self, zone_name):
        if zone_name not in self.zones:
            raise CloudFlareError(
                f"Can't find zone {zone_name} for you. Please check with Cloudflare!"
            )
        return self.zones[zone_name]["records"]

    def __init_records_for_sub_domain__(self, full_sub_domain, **kwargs):
        prefix, zone_name = self.split_domain(full_sub_domain)
        if len(prefix) == 0 or len(zone_name) == 0 or zone_name not in self.zones:
            raise CloudFlareError(
                f"Can't find zone {zone_name} for you. Please check with Cloudflare!"
            )
        self.__init_records_for_zone__(
            zone_name, domain=full_sub_domain, **kwargs)

    def __get_records_for_domain__(self, full_sub_domain: str):
        zone_name = self.__get_zone_name__(full_sub_domain)
        t_records = self.__get_records_for_zone__(zone_name)
        if full_sub_domain in t_records:
            return t_records[full_sub_domain]
        return {}

    def __get_records_for_domain_and_type__(self, zone: str, prefix: str, dns_type: str):
        full_sub_domain = f"{prefix}.{zone}"
        t_records = self.__get_records_for_domain__(full_sub_domain)
        records = {}
        dns_type = dns_type.strip().upper()
        if dns_type in t_records:
            records.update(t_records[dns_type])
        return records

    def __get_record_id_for_domain_type_and_content__(
            self, zone: str, prefix: str, dns_type: str, content: str
    ):
        dns_type = dns_type.strip().upper()
        full_sub_domain = f"{prefix}.{zone}"
        t_records = self.__get_records_for_domain_and_type__(
            zone, prefix, dns_type)
        if content in t_records:
            return t_records[content]

    def __get_zone_id__(self, full_sub_domain: str):
        full_sub_domain = full_sub_domain.strip().strip(".").strip()
        zone_name = self.__get_zone_name__(full_sub_domain)
        if len(zone_name) > 0:
            return self.zones[zone_name]["id"]
        raise CloudFlareError(f"Can't find zone for domain {full_sub_domain}")

    def __get_zone_name__(self, full_sub_domain: str):
        full_sub_domain = full_sub_domain.strip().strip(".").strip()
        if full_sub_domain in self.zones:
            return full_sub_domain
        _, zone_name = self.split_domain(full_sub_domain)
        if len(zone_name) > 0:
            return zone_name
        raise CloudFlareError(f"Can't find zone for domain {full_sub_domain}")

    def __create_one_record__(self, name, dns_type, content, **kwargs):
        """
        Create a dns record
        :param dns_type:
        :param name:
        :param content:
        :param kwargs:
        :return:
        """
        zone_id = self.__get_zone_id__(name)
        zone_name = self.__get_zone_name__(name)
        data = {"type": dns_type, "name": name, "content": content}
        if kwargs.get("ttl") and kwargs["ttl"] != 1:
            data["ttl"] = kwargs["ttl"]
        else:
            data["ttl"] = self.ttl
        if kwargs.get("proxied") and isinstance(kwargs["proxied"], bool):
            data["proxied"] = kwargs["proxied"]
            # if record is proxied, then ttl is automatically and the value is 1
            if data["proxied"]:
                data["ttl"] = 1
        else:
            data["proxied"] = self.proxied
        t_succ, t_result_dict = self.__request__(
            self.api_url + zone_id + "/dns_records", "post", data=data, **kwargs
        )
        if not t_succ or "result" not in t_result_dict:
            raise CloudFlareError(
                f'Failed to create "{name}" records for zone: "{zone_name}", \'{t_result_dict}\''
            )
        t_record = t_result_dict["result"]
        self.dns_records[t_record["id"]] = t_record
        # update self.zones
        if "records" not in self.zones[zone_name]:
            self.zones[zone_name]["records"] = {}
        if t_record["name"] not in self.zones[zone_name]["records"]:
            self.zones[zone_name]["records"][t_record["name"]] = {}
        if dns_type not in self.zones[zone_name]["records"][t_record["name"]]:
            self.zones[zone_name]["records"][t_record["name"]][dns_type] = {}
        self.zones[zone_name]["records"][t_record["name"]][t_record["type"]][t_record["content"]] = \
            t_record["id"]
        return t_record

    def __update_record_by_id__(
            self, record_id, name, dns_type, content, **kwargs
    ) -> dict:
        """
        Update dns record by record id
        :prarm record_id:
        :param name:
        :param dns_type:
        :param content:
        :param kwargs:
        :return:
        """
        name = name.lower()
        dns_type = dns_type.upper()
        zone_id = self.__get_zone_id__(name)
        zone_name = self.__get_zone_name__(name)
        # do double check
        if record_id not in self.dns_records:
            raise CloudFlareError(f"Can't find record id "
                                  f"{record_id} in local cache")
        old_record = self.dns_records[record_id]
        old_content = old_record["content"]
        if "records" not in self.zones[zone_name] or \
                name not in self.zones[zone_name]["records"] or \
                dns_type not in self.zones[zone_name]["records"][name] or \
                old_content not in self.zones[zone_name]["records"][name][dns_type]:
            raise CloudFlareError(
                f"Can't find record {name}: {dns_type}, {old_content} in local cache"
            )
        if self.zones[zone_name]["records"][name][dns_type][old_content] != record_id:
            raise CloudFlareError(
                f"Inconsistent record {record_id} and {name}: {dns_type}, {old_content} in local cache"
            )
        data = {"type": dns_type, "name": name, "content": content}
        if kwargs.get("ttl") and kwargs["ttl"] != 1:
            data["ttl"] = kwargs["ttl"]
        if kwargs.get("proxied") and isinstance(kwargs["proxied"], bool):
            data["proxied"] = kwargs["proxied"]
            # if record is proxied, then ttl is automatically and the value is 1
            if data["proxied"]:
                data["ttl"] = 1
        else:
            data["proxied"] = self.proxied
        t_succ, t_result_dict = self.__request__(
            urllib.parse.urljoin(self.api_url, zone_id +
                                 "/dns_records/" + record_id),
            "put",
            data=data,
            **kwargs,
        )
        if not t_succ or "result" not in t_result_dict:
            raise CloudFlareError(
                f'Failed to update "{name}: {dns_type}, {content}" '
                f'records for zone: "{zone_name}", \'{t_result_dict}\''
            )
        t_record = t_result_dict["result"]
        # update self.dns_records
        self.dns_records[record_id] = t_record
        # update self.zones
        if old_content != content:
            del self.zones[zone_name]["records"][name][dns_type][old_content]
            self.zones[zone_name]["records"][name][dns_type][content] = record_id
        return t_result_dict["result"]

    def __delete_record_by_id__(self, zone_id, record_id, **kwargs):
        """
        Delete a dns record
        :param zone_id:
        :param record_id:
        :return:
        """
        # do double check
        if record_id not in self.dns_records:
            raise CloudFlareError(f"Can't find record id "
                                  f"{record_id} in local cache")
        record = self.dns_records[record_id]
        content = record["content"]
        name = record["name"]
        zone_name = record["zone_name"]
        dns_type = record["type"]
        if "records" not in self.zones[zone_name] or \
            name not in self.zones[zone_name]["records"] or \
            dns_type not in self.zones[zone_name]["records"][name] or \
            content not in self.zones[zone_name]["records"][name][
                dns_type]:
            raise CloudFlareError(
                f"Can't find record {name}: "
                f"{dns_type}, {content} in local cache"
            )
        if self.zones[zone_name]["records"][name][dns_type][content] != record_id:
            raise CloudFlareError(
                f"Inconsistent record {record_id} and {name}: "
                f"{dns_type}, {content} in local cache"
            )
        t_succ, t_result_dict = self.__request__(
            urllib.parse.urljoin(self.api_url, zone_id +
                                 "/dns_records/" + record_id),
            "delete",
            None,
            **kwargs,
        )
        # failed to perford delete-action, rase an error
        if not t_succ:
            raise CloudFlareError(
                f'Can\'t delete record id - "{record_id}" for reason: {t_result_dict}'
            )
        # delete from local cache
        del self.dns_records[record_id]
        del self.zones[zone_name]["records"][name][dns_type][content]
        return True, t_result_dict, dns_type, content

    # def refresh(self, **kwargs):
    #     """
    #     Shortcut for setup zone
    #     :return:
    #     """
    #     self.__set_http_proxies__(**kwargs)
    #     self.__init_zones__(**kwargs)
    #     # self.__setup_zone__(**kwargs)

    def list_zones(self, **kwargs):
        """
        List all zones
        :return:
        """
        for key, _ in self.zones.items():
            print(key)

    def is_zone(self, domain: str, **kwargs):
        """
        check if a domain is a zone
        :param domain: domain
        :return:
        """
        for zone in self.zones_list:
            if zone == domain:
                return True
        return False

    def has_root_zone(self, domain: str, **kwargs):
        """
        check if a domain has a zone registered or not
        :param domain: domain
        :return:
        """
        domain = str(domain).strip().strip(".").strip().lower()
        for zone in self.zones_list:
            if domain.endswith("." + zone):
                return True
        return False

    def split_domain(self, domain: str, **kwargs) -> tuple:
        """
        Split domain into (prefix, zone).

        For example, if the domain is "example.com", and the zone is "example.com",
        then the prefix is "".

        If the domain is "sub.example.com", and the zone is "example.com",
        then the prefix is "sub".

        :param domain: domain
        :return: tuple of (prefix, zone)
        """
        domain = str(domain).strip().strip(".").strip().lower()
        for zone in self.zones_list:
            if domain.endswith("." + zone):
                prefix = domain.removesuffix("." + zone)
                prefix = prefix.strip(".")
                return (prefix, zone)
        return ()

    def list_record_for_zone(self, zone: str, **kwargs):
        """
        List all records for a zone
        :param zone:
        :return:
        """
        zone_name = self.__get_zone_name__(zone)
        self.__init_records_for_zone__(zone_name, **kwargs)
        for key, value in self.zones[zone_name]["records"].items():
            if zone == zone_name or key == zone:
                print(f"{key}: ")
                for v in value.values():
                    for t_v in v["values"]:
                        print(t_v)

    def list_records(self, records: dict, **kwargs):
        """
        List all records for a zone
        :param zone:
        :return:
        """
        for t_zone in records:
            self.__init_records_for_zone__(t_zone, **kwargs)
            for t_prefix in records[t_zone]:
                t_sub_domain = f"{t_prefix}.{t_zone}"
                if t_sub_domain in self.zones[t_zone]["records"]:
                    t_record_id_list = []
                    for key, value in self.zones[t_zone]["records"][t_sub_domain].items():
                        if len(records[t_zone][t_prefix]) > 0:
                            if key in records[t_zone][t_prefix]:
                                for t_t_v in value.values():
                                    t_record_id_list.append(t_t_v)
                        else:
                            for t_t_v in value.values():
                                t_record_id_list.append(t_t_v)
                    if len(t_record_id_list) > 0:
                        print(f"{t_sub_domain}: ")
                        for t_id in t_record_id_list:
                            if t_id in self.dns_records:
                                print(self.dns_records[t_id])

    # def create_records(self, name, dns_type, content_list, **kwargs):
    #     """
    #     Create a dns record
    #     :param dns_type:
    #     :param name:
    #     :param content_list:
    #     :param kwargs:
    #     :return:
    #     """
    #     name = name.lower()
    #     dns_type = dns_type.upper()
    #     self.__init_records_for_sub_domain__(name, **kwargs)
    #     content_list = list(set(content_list))
    #     if dns_type == "CNAME" and len(content_list) > 1:
    #         print(
    #             f"WARNING! Can't create more than one records for ({name}, {dns_type}), {
    #                 dns_type} just one record permitted!"
    #         )
    #         return
    #     t_records_dict = self.__get_records_for_domain_and_type__(
    #         name, dns_type)
    #     # just check for CNAME, CNAME need just one record
    #     # if dns_type == "CNAME" and len(t_records_list) > 1:
    #     #     print(f"WARNING! Escape exists record ({name}, {dns_type}, {t_content}), {dns_type} just one record permitted!")
    #     #     return
    #     # check records exist or not,
    #     #    keep the content and its record id.
    #     # t_exists_dict = {}
    #     t_non_exist_content = []
    #     for t_content in content_list:
    #         if t_content in t_records_dict:
    #             print(
    #                 f"Escape existing record ({name}, {dns_type}, {t_content})")
    #         else:
    #             t_non_exist_content.append(t_content)
    #     # do create for non-exist records
    #     # t_created_dict = {}
    #     for t_content in t_non_exist_content:
    #         self.__create_one_record__(name, dns_type, t_content, **kwargs)
    #         # t_created_dict[(name, dns_type, t_content)] = t_result
    #         print(
    #             f"Succeed to created a record ({name}, {dns_type}, {t_content})")
    #         time.sleep(0.1)

    def create_records_new(self, records_dict: dict, **kwargs):
        """
        Create a dns record
        :param records_dict: {<zone>: {"prefix": {<type>: {<content>: (ttl, proxied)}}}}
        :param kwargs:
        :return:
        """
        for t_zone in records_dict:
            t_zone = t_zone.lower()
            self.__init_records_for_zone__(t_zone, **kwargs)
            self.__get_records_for_zone__(t_zone)
            for t_prefix in records_dict[t_zone]:
                t_sub_domain = f"{t_prefix}.{t_zone}"
                for dns_type in records_dict[t_zone][t_prefix]:
                    dns_type = dns_type.upper()
                    t_records_dict = self.__get_records_for_domain_and_type__(
                        t_zone, t_prefix, dns_type
                    )
                    t_non_exist_content = []
                    for t_content in records_dict[t_zone][t_prefix][dns_type]:
                        if t_content in t_records_dict:
                            print(
                                f"Escape existing record ({t_sub_domain}, "
                                f"{dns_type}, {t_content})"
                            )
                        else:
                            t_ttl, t_proxied = records_dict[t_zone][t_prefix][dns_type][t_content]
                            t_non_exist_content.append(
                                (t_content, t_ttl, t_proxied))
                    # do create for non-exist records
                    # t_created_dict = {}
                    for t_content, t_ttl, t_proxied in t_non_exist_content:
                        self.__create_one_record__(
                            t_sub_domain,
                            dns_type,
                            t_content,
                            ttl=t_ttl,
                            proxied=t_proxied,
                            **kwargs,
                        )
                        # t_created_dict[(name, dns_type, t_content)] = t_result
                        print(
                            f"Succeed to created a record ({t_sub_domain}, {dns_type},"
                            f" {t_content})"
                        )
                        time.sleep(0.1)

    # def delete_records(self, name, dns_type, content_list: list, **kwargs):
    #     """
    #     Delete a dns record
    #     :param name:
    #     :param dns_type:
    #     :param content_list: can be empty, delete all records which dns type is <dns_type>
    #     :return:
    #     """
    #     name = name.lower()
    #     dns_type = dns_type.upper()
    #     self.__init_records_for_sub_domain__(name, **kwargs)
    #     # reset proxies
    #     # self.__set_http_proxies__(**kwargs)
    #     zone_id = self.__get_zone_id__(name)
    #     t_record_dict = self.__get_records_for_domain_and_type__(
    #         name, dns_type)
    #     for content in t_record_dict:
    #         record_id = t_record_dict[content]
    #         # delete from remote server
    #         if content not in content_list:
    #             continue
    #         t_succ, _ = self.__delete_record_by_id__(
    #             zone_id, record_id, **kwargs)
    #         if t_succ:
    #             print(f"Succeed to delete [{name}, {dns_type}, {content}]")
    #         else:
    #             print(
    #                 f"Warnig! Failed to delete [{name}, {dns_type}, {content}]")
    #         time.sleep(0.1)

    def delete_records_new(self, records_dict: dict, **kwargs):
        """
        Delete a dns record
        :param records_dict: {<zone>: {"prefix": {<type>: {<content>: (ttl, proxied)}}}}
        :param kwargs:
        :return:
        """
        for t_zone in records_dict:
            t_zone = t_zone.lower()
            self.__init_records_for_zone__(t_zone, **kwargs)
            zone_id = self.__get_zone_id__(t_zone)
            record_id_list_for_del = []
            for t_prefix in records_dict[t_zone]:
                if len(records_dict[t_zone][t_prefix]) == 0:
                    t_current_record_dict = self.__get_records_for_domain__(
                        f"{t_prefix}.{t_zone}")
                    for t_v in t_current_record_dict.values():
                        for t_t_v in t_v.values():
                            record_id_list_for_del.append(t_t_v)
                else:
                    for dns_type in records_dict[t_zone][t_prefix]:
                        dns_type = dns_type.upper()
                        t_current_record_dict = self.__get_records_for_domain_and_type__(
                            t_zone, t_prefix, dns_type
                        )
                        for content in t_current_record_dict:
                            record_id = t_current_record_dict[content]
                            record_id_list_for_del.append(record_id)
                for record_id in record_id_list_for_del:
                    t_succ, _, dns_type, content = self.__delete_record_by_id__(
                        zone_id, record_id, **kwargs
                    )
                    if t_succ:
                        print(
                            f"Succeed to delete [{t_prefix}.{t_zone}, {dns_type}, {content}]")
                    else:
                        print(
                            f"Warnig! Failed to delete "
                            f"[{t_prefix}.{t_zone}, {dns_type}, {content}]"
                        )
                    time.sleep(0.1)

    # def update_records(self, name, dns_type, content_list: list, **kwargs):
    #     """
    #     Update dns record
    #     :param dns_type:
    #     :param name:
    #     :param content:
    #     :param kwargs:
    #     :return:
    #     """
    #     name = name.lower()
    #     dns_type = dns_type.upper()
    #     zone_id = self.__get_zone_id__(name)
    #     self.__init_records_for_sub_domain__(name, **kwargs)
    #     # strip and remove duplicated item
    #     content_list = [str(content).strip() for content in content_list]
    #     content_list = list(set(content_list))
    #     if dns_type == "CNAME" and len(content_list) > 1:
    #         print(
    #             f"WARNING! Can't update more than one records for ({name}, {dns_type}), {
    #                 dns_type} just one record permitted!"
    #         )
    #         return
    #     # clean
    #     t_records_dict = self.__get_records_for_domain_and_type__(
    #         name, dns_type)
    #     # scan content list, find all exist records and non-exist records
    #     t_non_exist_contents = []
    #     t_exist_contents = []
    #     for t_content in content_list:
    #         if t_content in t_records_dict:
    #             t_exist_contents.append(t_content)
    #         else:
    #             t_non_exist_contents.append(t_content)
    #     # find all extra records
    #     t_extra_records = []
    #     for t_content in t_records_dict:
    #         if t_content not in content_list:
    #             t_extra_records.append(t_content)
    #     # update for existing records
    #     for t_content in t_exist_contents:
    #         self.__update_record_by_id__(
    #             t_content["id"], name, dns_type, t_content, **kwargs
    #         )
    #         print(f"Update for ({name}, {dns_type}), {t_content})")
    #     # create non-exist records:
    #     for t_content in t_non_exist_contents:
    #         self.__create_one_record__(name, dns_type, t_content, **kwargs)
    #         print(f"Create ({name}, {dns_type}), {t_content})")
    #     # delete extra records
    #     for t_content in t_extra_records:
    #         self.__delete_record_by_id__(
    #             zone_id, t_records_dict[t_content], **kwargs)
    #         print(f"Delete ({name}, {dns_type}), {t_content})")

    def update_records_new(self, records_dict: dict, **kwargs):
        """
        Update dns record
        :param records_dict: {<zone>: {"prefix": {<type>: {<content>: (ttl, proxied)}}}}
        :param kwargs:
        :return:
        """
        for t_zone in records_dict:
            t_zone = t_zone.lower()
            zone_id = self.__get_zone_id__(t_zone)
            self.__init_records_for_zone__(t_zone, **kwargs)
            for t_prefix in records_dict[t_zone]:
                t_prefix_obj = records_dict[t_zone][t_prefix]
                t_full_domain = f"{t_prefix}.{t_zone}"
                for dns_type in t_prefix_obj:
                    dns_type = dns_type.upper()
                    # clean
                    t_current_records_dict = self.__get_records_for_domain_and_type__(
                        t_zone, t_prefix, dns_type
                    )
                    # scan content list, find all exist records and non-exist records
                    t_non_exist_contents = []
                    t_exist_contents = []
                    t_dns_obj = t_prefix_obj[dns_type]
                    for t_content in t_dns_obj:
                        t_ttl, t_proxied = t_dns_obj[t_content]
                        if t_content in t_current_records_dict:
                            t_exist_contents.append(
                                (t_content, t_ttl, t_proxied))
                        else:
                            t_non_exist_contents.append(
                                (t_content, t_ttl, t_proxied))
                    # find all extra records
                    t_extra_records = []
                    if len(t_current_records_dict) > 0:
                        for t_content, t_record_id in t_current_records_dict.items():
                            t_record = self.dns_records[t_record_id]
                            t_name = t_record['name']
                            # t_zone = t_record['zone_name']
                            t_type = t_record['type']
                            t_cont = t_content
                            t_ttl = t_record['ttl']
                            t_proxied = t_record['proxied']
                            t_prefix = str(t_name).removesuffix(f".{t_zone}")
                            if t_prefix not in records_dict[t_zone] or \
                                    t_type not in t_prefix_obj or \
                                    t_cont not in t_dns_obj:
                                t_extra_records.append(t_content)
                    # update for existing records
                    for t_content, t_ttl, t_proxied in t_exist_contents:
                        if t_content in t_current_records_dict:
                            t_record_id = t_current_records_dict[t_content]
                            self.__update_record_by_id__(
                                t_record_id,
                                t_full_domain,
                                dns_type,
                                t_content,
                                ttl=t_ttl,
                                proxied=t_proxied,
                                **kwargs,
                            )
                            print(f"Update for [{t_full_domain}, "
                                  f"{dns_type}, {t_content}]")
                    # delete extra records
                    for t_content in t_extra_records:
                        t_record_id = t_current_records_dict[t_content]
                        self.__delete_record_by_id__(
                            zone_id, t_record_id, **kwargs)
                        print(f"Delete [{t_full_domain}, "
                              f"{dns_type}, {t_content}]")
                    # add for non-exist records:
                    while len(t_non_exist_contents) > 0:
                        t_content, t_ttl, t_proxied = t_non_exist_contents[0]
                        self.__create_one_record__(
                            t_full_domain,
                            dns_type,
                            t_content,
                            ttl=t_ttl,
                            proxied=t_proxied,
                            **kwargs,
                        )
                        print(
                            f"Create [{t_full_domain}, {dns_type}, {t_content}]")


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ("yes", "true", "t", "y", "1"):
        return True
    elif v.lower() in ("no", "false", "f", "n", "0"):
        return False
    else:
        raise argparse.ArgumentTypeError(
            "Bool value expected.")


def print_logs(t_u: list, t_c: list, t_d: list, t_k: list):
    if len(t_u) > 0:
        print("Update for:")
        for t_i in t_u:
            print(f'"{t_i[0]}" - "{t_i[1]}" - "{t_i[2]}"')
            print(t_u[t_i])
    if len(t_c) > 0:
        print("Create for:")
        for t_i in t_c:
            print(f'"{t_i[0]}" - "{t_i[1]}" - "{t_i[2]}"')
            print(t_c[t_i])
    if len(t_d) > 0:
        print("Delete for:")
        for t_i in t_d:
            print(f'"{t_i[0]}" - "{t_i[1]}" - "{t_i[2]}"')
            print(t_d[t_i])
    if len(t_k) > 0:
        print("Keep for:")
        for t_i in t_k:
            print(f'"{t_i[0]}" - "{t_i[1]}" - "{t_i[2]}"')
            print(t_k[t_i])


def gen_content_dict(dns_type: str, content_list: list, ttl: int, proxied: bool, **kwargs):
    t_content_dict = {dns_type: {}}
    t_content_list = split_content_list(content_list)
    for c in t_content_list:
        t_content_dict[dns_type][c] = (ttl, proxied)
    return t_content_dict


def is_valid_dns_type(dns_type: str):
    return dns_type.upper() in valid_record_type


def split_content_list(content_list: list):
    t_content_list = []
    for t in content_list:
        t_list = split_content(str(t))
        t_content_list.extend(t_list)
    return list(set(t_content_list))


def split_content(content: str):
    t_re_rules = RE_SPLITTER_WITH_WHITESPACE
    t_list = t_re_rules.split(str(content))
    return list(set(t_list))


def sort_zones(zones: list):
    if len(zones) == 0:
        return []
    t_dict = {}
    t_sorted = []
    zones = list(set([str(zone).strip().strip('.') for zone in zones]))
    for zone in zones:
        t_zone_list = str(zone).split('.')
        t_len = len(t_zone_list)
        if t_len not in t_dict:
            t_dict[t_len] = []
        t_dict[t_len].append(zone)
    t_key = list(t_dict.keys())
    t_key.sort(reverse=True)
    for k in t_key:
        t_dict[k].sort()
        t_sorted.extend(t_dict[k])
    return t_sorted


def custom_help():
    msg = '''usage: 
  1. python3 cloudflare-ddns.py [-e EMAIL] [-k API_KEY] --list_zone <-z ZONE> [-z ZONE]...
  2. python3 cloudflare-ddns.py [-e EMAIL] [-k API_KEY] --list_record \\
        <-d DOMAIN [-d domain]... | -z ZONE [-z ZONE] [-a ALIAS [-a ALIAS]...]> [--dns-type DNS_TYPE] \\
  UPDATE:
  3. python3 cloudflare-ddns.py [-e EMAIL] [-k API_KEY] --update-record \\
        <-d DOMAIN [-d domain]... | -z ZONE [-z ZONE]... -a ALIAS [-a ALIAS]...>  \\
        [[-4 IPV4_ADDR]... [-6 IPV6_ADDR]... | [-c CNAME | --cname-alias ALIAS] | \\
        [-t TTL] [--proxied [PROXIED]
  4. python3 cloudflare-ddns.py [-e EMAIL] [-k API_KEY] --update-record \\
        <-z ZONE [-z ZONE]...> <-r RAW | --raw-file RAW_FILE] | [--raw-alias ALIAS | --raw-alias-file ALIAS_FILE]> \\
        [-t TTL] [--proxied [PROXIED]
  CREATE:
  5. python3 cloudflare-ddns.py [-e EMAIL] [-k API_KEY] --add-record \\
        <-d DOMAIN [-d domain]... | -z ZONE [-z ZONE]... -a ALIAS [-a ALIAS]...>  \\
        [[-4 IPV4_ADDR]... [-6 IPV6_ADDR]... | [-c CNAME | --cname-alias ALIAS] | \\
        [-t TTL] [--proxied [PROXIED]
  6. python3 cloudflare-ddns.py [-e EMAIL] [-k API_KEY] --add-record \\
        <-z ZONE [-z ZONE]...> <-r RAW | --raw-file RAW_FILE] | [--raw-alias ALIAS | --raw-alias-file ALIAS_FILE]> \\
        [-t TTL] [--proxied [PROXIED]
  DELETE:
  7. python3 cloudflare-ddns.py [-e EMAIL] [-k API_KEY] --delete-record \\
        <-d DOMAIN [-d domain]... | -z ZONE [-z ZONE] -a ALIAS [-a ALIAS]...>  \\
        [[-4 IPV4_ADDR]... [-6 IPV6_ADDR]... [-c CNAME | --cname-alias ALIAS] | \\
        [-r RAW | --raw-file RAW_FILE] | [--raw-alias ALIAS | --raw-alias-file ALIAS_FILE] | [--dns-type DNS_TYPE]]

command arguments:
  --list_zone            list all zones
  --list_record          list records for specific zone
  --update-record         domain for update
  --add-record            domain for add
  --delete-record         domain for delete

options:
  -h, --help            show this help message and exit
  -e EMAIL, --email EMAIL
                        Email for your cloudflare account
  -k API_KEY, --api-key API_KEY
                        API Key of your cloudflare account
  -z ZONE, --zone-id ZONE
                        zone id in cloudflare
  -a ALIAS, --alias ALIAS
                        alias of domain
  -d DOMAIN, --domain DOMAIN
                        sub domain, "--alias a --zone example.com" equivalent to "--domain a.example.com"
  -4 IPV4_ADDR, --ipv4 IPV4_ADDR
                        IPv4 address for action
  -6 IPV6_ADDR, --ipv6 IPV6_ADDR
                        IPv6 address for action
  -c CNAME, --cname CNAME
                        cname for action
  --cname-alias CNAME_ALIAS
                        alias of cname content while do add or update. For example, '-a example.com,example.com --alias ww1 --cname-alias w1'
  --dns-type DNS_TYPE   dns type for delete
  -t TTL, --ttl TTL     ttl for record
  --proxied [PROXIED]   It should be proxied
  -r RAW, --raw RAW     raw record for operation. For example, "add_record -d example.com --raw ww1,A,1.1.1.1,60,false" and "--raw
                        ww2,CNAME,w1.example.com,60,false". The "content" must be full target while DNS type is "CNAME", comparing with "--raw-
                        alias".
  --raw-file RAW_FILE   file stored raw for operation, each line contains "name,dns_type,content,ttl,proxied", which is the same as "--raw".
  --raw-alias RAW_ALIAS
                        alias of raw content while do add or operation. For example, "add_record -d example.com "--raw-alias
                        ww1,A,1.1.1.1,60,false" and"--raw-alias ww2,CNAME,w1,60,false". The "content" must be alias while DNS type is "CNAME",
                        comparing with "--raw"."--raw-alias ww2,CNAME,w1,60,false" equivalent to "--raw ww2,CNAME,w1.example.com,60,false".
  --raw-alias-file RAW_ALIAS_FILE
                        file stored raw for operation, each line contains "name, dns_type, content, ttl, proxied", which is the same as "--raw-
                        alias".
  -v, --version         show version
'''
    print(msg)
    sys.exit(0)


def main():
    from src import __version__
    print(f"cloudflare-ddns {__version__}")
    print("  - a DDNS helper for Cloudflare.")
    print('  - create, delete or update dns record for dns type "A|AAAA|CNAME".')
    print("")
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "-e",
        "--email",
        action="store",
        dest="email",
        type=str,
        help="Email for your cloudflare account"
    )
    parser.add_argument(
        "-k",
        "--api-key",
        action="store",
        dest="api_key",
        type=str,
        help="API Key of your cloudflare account"
    )
    cmd_group = parser.add_mutually_exclusive_group(required=False)
    cmd_group.add_argument(
        "--list-zone",
        action="store",
        dest="list_zone",
        default=False,
        const=True,
        nargs='?',
        type=str2bool,
        help="list all zones",
    )
    cmd_group.add_argument(
        "--list-record",
        action="store",
        dest="list_record", nargs='?',
        type=str2bool, const=True, default=False,
        help="list records for specific zone"
    )
    cmd_group.add_argument(
        "--update-record",
        action="store",
        dest="update_record", nargs='?',
        type=str2bool, const=True, default=False,
        help="domain for update"
    )
    cmd_group.add_argument(
        "--add-record",
        action="store",
        dest="add_record", nargs='?',
        type=str2bool, const=True, default=False,
        help="domain for add"
    )
    cmd_group.add_argument(
        "--delete-record",
        action="store",
        dest="delete_record", nargs='?',
        type=str2bool, const=True, default=False,
        help="domain for delete"
    )
    parser.add_argument(
        "-z", "--zone",
        action="append",
        dest="zone",
        type=str,
        help="root domain, zone in cloudflare"
    )
    parser.add_argument(
        "-d", "--domain",
        action="append",
        dest="domain",
        type=str,
        help="subdomain in cloudflare. \"--alias a --zone example.com\" equivalent to \"--domain a.example.com\""
    )
    parser.add_argument(
        "-a",
        "--alias",
        action="append",
        dest="alias",
        type=str,
        help="alias of domain"
    )
    parser.add_argument(
        "-4",
        "--ipv4",
        action="append",
        dest="ipv4_addr",
        type=str,
        help="IPv4 address for action"
    )
    parser.add_argument(
        "-6",
        "--ipv6",
        action="append",
        dest="ipv6_addr",
        type=str,
        help="IPv6 address for action"
    )
    parser.add_argument(
        "-c", "--cname", action="store", dest="cname", type=str, help="cname for action"
    )
    parser.add_argument(
        "--cname-alias",
        action="store",
        dest="cname_alias",
        type=str,
        help="alias of cname content while do add or update. "
             "For example, '-a example.com,example.com --alias ww1 --cname-alias w1'"
    )
    parser.add_argument(
        "--dns-type",
        action="append",
        dest="dns_type",
        type=str,
        help="dns type for delete"
    )
    parser.add_argument(
        "-t",
        "--ttl",
        action="store",
        default=60,
        dest="ttl",
        type=int,
        help="ttl for record"
    )
    parser.add_argument(
        "--proxied",
        action="store",
        default=False,
        const=True,
        nargs='?',
        dest="proxied",
        type=str2bool,
        help="It should be proxied"
    )
    parser.add_argument(
        "-r",
        "--raw",
        action="append",
        dest="raw",
        type=str,
        help='raw record for operation. For example, "add_record -d example.com --raw ww1,A,1.1.1.1,60,false" and '
             '"--raw ww2,CNAME,w1.example.com,60,false". '
             'The "content" must be full target while DNS type is "CNAME", comparing with "--raw-alias".'
    )
    parser.add_argument(
        "--raw-file",
        action="store",
        dest="raw_file",
        type=str,
        help='file stored raw for operation, each line contains "name,dns_type,content,ttl,proxied", which is the same as "--raw".'
    )
    parser.add_argument(
        "--raw-alias",
        action="append",
        dest="raw_alias",
        type=str,
        help="alias of raw content while do add or operation. For example, \"add_record -d example.com "
             "\"--raw-alias ww1,A,1.1.1.1,60,false\" and"
             "\"--raw-alias ww2,CNAME,w1,60,false\". "
             "The \"content\" must be alias while DNS type is \"CNAME\", comparing with \"--raw\"."
             "\"--raw-alias ww2,CNAME,w1,60,false\" equivalent to \"--raw ww2,CNAME,w1.example.com,60,false\"."
    )
    parser.add_argument(
        "--raw-alias-file",
        action="store",
        dest="raw_alias_file",
        type=str,
        help="file stored raw for operation, each line contains \"name, dns_type, content, ttl, proxied\", which is the same as \"--raw-alias\"."
    )
    parser.add_argument(
        "-v",
        "--version",
        action="store_true",
        dest="version",
        default=False,
        help="show version",
    )
    parser.print_help = lambda: custom_help()
    args = parser.parse_args()
    if args.version:
        sys.exit(0)
    if not args.email or len(args.email) == 0:
        print("No email!")
        sys.exit(1)
    if not args.api_key or len(args.api_key) == 0:
        print("No API Key!")
        sys.exit(1)
    # add, update and delete
    t_domains_list = []
    action_list_zones = False
    action_list_records = False
    action_add_records = False
    action_update_records = False
    action_delete_records = False
    # {"a.com": {"prefix": {"A": {"1.1.1.1": {"ttl": 60, "proxied": False, "DEL"}, "DEL": False}}}}
    t_records_dict = {}
    # for update records only
    t_raw_list = []
    if args.list_zone:
        action_list_zones = True
    elif args.list_record > 0:
        action_list_records = True
    elif args.update_record:
        action_update_records = True
    elif args.add_record:
        action_add_records = True
    elif args.delete_record:
        action_delete_records = True
    else:
        print("No valid cmd provided!")
        sys.exit(1)
    if (args.ipv4_addr and len(args.ipv4_addr) > 0) or (args.ipv6_addr and len(args.ipv6_addr) > 0):
        if (args.cname and len(args.cname) > 0) or (args.cname_alias and len(args.cname_alias) > 0):
            print(
                "Please do not use \"--cname\" or \"--cname-alias\" with \"--ipv4-addr\" or \"--ipv6-addr\"")
            sys.exit(1)
        if (args.raw and len(args.raw) > 0) or (args.raw_file and len(args.raw_file) > 0) or \
                (args.raw_alias and len(args.raw_alias) > 0) or (args.raw_alias_file and len(args.raw_alias_file) > 0):
            print(
                "Please do not use \"--raw\", \"--raw-alias\", \"--raw-file\" "
                "or \"--raw-alias-file\" with \"--ipv4-addr\" or \"--ipv6-addr\"")
            sys.exit(1)
        if args.zone and len(args.zone) > 0:
            if not args.alias or len(args.alias) == 0:
                print(
                    "Please use \"--alias\" with \"--zone\"")
                sys.exit(1)
            if args.domain and len(args.domain) > 0:
                print(
                    "Please do not use \"--domain\" with \"--zone\"")
                sys.exit(1)
        elif not args.domain or len(args.domain) == 0:
            print(
                "Please use \"--zone\" with \"--alias\" or just use \"--domain\"")
            sys.exit(1)
    elif (args.cname and len(args.cname) > 0) or (args.cname_alias and len(args.cname_alias) > 0):
        if (args.raw and len(args.raw) > 0) or (args.raw_file and len(args.raw_file) > 0) or \
                (args.raw_alias and len(args.raw_alias) > 0) or (args.raw_alias_file and len(args.raw_alias_file) > 0):
            print(
                "Please do not use \"--raw\", \"--raw-alias\", \"--raw-file\" "
                "or \"--raw-alias-file\" with \"--cname\" or \"--cname-alias\"")
            sys.exit(1)
        if args.cname_alias and len(args.cname_alias) > 0:
            if not args.zone or len(args.zone) == 0 or not args.alias or len(args.alias) == 0:
                print(
                    "Please use \"--zone\", \"--alias\" with \"--cname-alias\"")
                sys.exit(1)
            if args.domain and len(args.domain) > 0:
                print(
                    "Please do not use \"--domain\" with \"--cname-alias\"")
                sys.exit(1)
        else:
            if args.zone and len(args.zone) > 0:
                if not args.alias or len(args.alias) == 0:
                    print(
                        "Please use \"--alias\" with \"--zone\"")
                    sys.exit(1)
                if args.domain and len(args.domain) > 0:
                    print(
                        "Please do not use \"--domain\" with \"--zone\"")
                    sys.exit(1)
            elif not args.domain or len(args.domain) == 0:
                print(
                    "Please use \"--zone\" with \"--alias\" or just use \"--domain\"")
                sys.exit(1)
    elif (args.raw and len(args.raw) > 0) or (args.raw_file and len(args.raw_file) > 0) or \
            (args.raw_alias and len(args.raw_alias) > 0) or (args.raw_alias_file and len(args.raw_alias_file) > 0):
        if (args.alias and len(args.alias) > 0) or (args.domain and len(args.domain) > 0):
            print(
                "Please do not use \"--alias\" or \"--domain\" with \"--raw\", \"--raw-alias\", \"--raw-file\" or \"--raw-alias-file\"")
            sys.exit(1)
        if not args.zone or len(args.zone) == 0:
            print(
                "Please use \"--zone\" with \"--raw\", \"--raw-alias\", \"--raw-file\" or \"--raw-alias-file\"")
            sys.exit(1)
        if ((args.raw and len(args.raw) > 0) or (args.raw_file and len(args.raw_file) > 0)) and \
                (args.raw_alias or len(args.raw_alias) > 0 or args.raw_alias_file or len(args.raw_alias_file) > 0):
            print(
                "Please do not use \"--raw\" or \"--raw-file\" with \"--raw-alias\" or \"--raw-alias-file\"")
            sys.exit(1)
    cf = CloudFlare(email=args.email, api_key=args.api_key)
    if action_list_zones:
        cf.list_zones()
        sys.exit(0)
    # not list zones
    # check domain
    if args.domain and len(args.domain) > 0:
        t_domains_list.extend(split_content_list(args.domain))
        for t_domain in t_domains_list:
            if cf.is_zone(t_domain):
                print("{t_domain} is zone! Please do not use \"-d\" with a zone.")
                sys.exit(1)
            if not cf.has_root_zone(t_domain):
                print(
                    "{t_domain} does not have root zone! Please add root zone in CloudFlare.")
                sys.exit(1)
            t_prefix, t_zone = cf.split_domain(t_domain)
            if t_zone not in t_records_dict:
                t_records_dict[t_zone] = {}
            if t_prefix not in t_records_dict[t_zone]:
                t_records_dict[t_zone][t_prefix] = {}
    # check zone
    if args.zone and len(args.zone) > 0:
        # if not args.alias or len(args.alias) == 0:
        #     print("No alias provided!")
        #     sys.exit(1)
        # zone list
        t_zone_list = split_content_list(args.zone)
        for t_zone in t_zone_list:
            if not cf.is_zone(t_zone):
                print(
                    "{t_zone} is not zone! Please provide valid zone which registered in CloudFlare.")
                sys.exit(1)
            if t_zone not in t_records_dict:
                t_records_dict[t_zone] = {}
            for t_alias in split_content_list(args.alias):
                t_domains_list.append(f"{t_alias}.{t_zone}")
                if t_alias not in t_records_dict[t_zone]:
                    t_records_dict[t_zone][t_alias] = {}
    # # init t_records_dict
    # for t_domain in t_domains_list:
    #     pass
    if len(t_records_dict) == 0:
        print("No valid domain provided!")
        sys.exit(1)
    # resolve ipv4
    if args.ipv4_addr and len(args.ipv4_addr) > 0:
        t_ipv4_list = split_content_list(args.ipv4_addr)
        for t_zone in t_records_dict:
            for t_prefix in t_records_dict[t_zone]:
                t_records_dict[t_zone][t_prefix].update(gen_content_dict(
                    "A", t_ipv4_list, args.ttl, args.proxied))

    # resolve ipv6
    if args.ipv6_addr and len(args.ipv6_addr) > 0:
        t_ipv6_list = split_content_list(args.ipv6_addr)
        for t_zone in t_records_dict:
            for t_prefix in t_records_dict[t_zone]:
                t_records_dict[t_zone][t_prefix].update(gen_content_dict(
                    "AAAA", t_ipv6_list, args.ttl, args.proxied))

    # resolve cname
    if (args.cname and len(args.cname) > 0) or (args.cname_alias and len(args.cname_alias) > 0):
        for t_zone in t_records_dict:
            for t_prefix in t_records_dict[t_zone]:
                if args.cname and len(args.cname) > 0:
                    t_content = args.cname
                else:
                    t_content = args.cname_alias + f".{t_zone}"
                t_records_dict[t_zone][t_prefix].update(gen_content_dict(
                    "CNAME", [t_content], args.ttl, args.proxied))
    if (args.raw and len(args.raw) > 0) or (args.raw_file and len(args.raw_file) > 0):
        t_raw_list = []
        if args.raw and len(args.raw) > 0:
            t_raw_list = split_content_list(args.raw)
        if args.raw_file and len(args.raw_file) > 0:
            try:
                with open(args.raw_file, "r") as fp:
                    t_content_list = fp.readlines()
                    t_raw_list.extend(
                        [item.strip()
                         for item in t_content_list if len(item.strip()) > 0]
                    )
            except Exception as E:
                print(f"failed to read --raw-file {args.raw_file}")
                raise E
        for t_raw in t_raw_list:
            t_line_list = split_content_list(t_raw)
            if len(t_line_list) != 5:
                print(f"invalid raw content {t_raw}")
                sys.exit(1)
            t_prefix, t_dns_type, t_content, t_ttl, t_proxied = t_line_list
            for t_zone in t_records_dict:
                if t_prefix not in t_records_dict[t_zone]:
                    t_records_dict[t_zone][t_prefix] = {}
                t_records_dict[t_zone][t_prefix].update(gen_content_dict(
                    t_dns_type, [t_content], t_ttl, t_proxied))
    if (args.raw_alias and len(args.raw_alias) > 0) or (args.raw_alias_file and len(args.raw_alias_file) > 0):
        t_raw_list = []
        if args.raw_alias and len(args.raw_alias) > 0:
            t_raw_list = split_content_list(args.raw_alias)
        if args.raw_alias_file and len(args.raw_alias_file) > 0:
            try:
                with open(args.raw_alias_file, "r") as fp:
                    t_content_list = fp.readlines()
                    t_raw_list.extend(
                        [item.strip()
                         for item in t_content_list if len(item.strip()) > 0]
                    )
            except Exception as E:
                print(f"failed to read --raw-alias-file {args.raw_alias_file}")
                raise E
        for t_raw in t_raw_list:
            t_line_list = split_content_list(t_raw)
            if len(t_line_list) != 5:
                print(f"invalid raw content {t_raw}")
                sys.exit(1)
            # t_content is just prefix in --raw-alias or --raw-alias-file
            t_prefix, t_dns_type, t_content, t_ttl, t_proxied = t_line_list
            for t_zone in t_records_dict:
                if t_prefix not in t_records_dict[t_zone]:
                    t_records_dict[t_zone][t_prefix] = {}
                t_records_dict[t_zone][t_prefix].update(gen_content_dict(
                    t_dns_type, [f"{t_content}.{t_zone}"], t_ttl, t_proxied))
    # only works when action_list_records or action_delete_records
    if args.dns_type and len(args.dns_type) > 0:
        if action_list_records or action_delete_records:
            t_dns_type_list = split_content_list(args.dns_type)
            for t_dns_type in t_dns_type_list:
                if not is_valid_dns_type(t_dns_type):
                    print(f"invalid dns type {t_dns_type}")
                    sys.exit(1)
            for t_zone in t_records_dict:
                for t_prefix in t_records_dict[t_zone]:
                    for t_dns_type in t_dns_type_list:
                        t_records_dict[t_zone][t_prefix][t_dns_type] = {}
    # list records
    if action_list_records:
        cf.list_records(t_records_dict)
    elif action_update_records:
        cf.update_records_new(t_records_dict)
    elif action_add_records:
        cf.create_records_new(t_records_dict)
    elif action_delete_records:
        cf.delete_records_new(t_records_dict)
    else:
        print("Invalid operation!")
