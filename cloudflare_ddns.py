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

VERSION = "v2.4 - 20240403"

valid_record_type = ("A", "AAAA", "CNAME")


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
    zones = {}
    http_proxies_default = {"http_proxy": "", "https_proxy": ""}
    public_ip_finder = (
        "https://api64.ipify.org/",
        "https://ip.seeip.org",
        "http://api.ip.sb/ip",
    )
    per_page = 200

    def __init__(
            self, email: str, api_key: str, domain: str, proxied: bool = False, **kwargs
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
        self.domain = domain
        self.proxied = proxied
        self.headers = {"X-Auth-Key": api_key, "X-Auth-Email": email}
        # minimum ttl is 60 seconds
        # set ttl for basic record creatation or record update
        self.ttl = 300
        if kwargs.get("ttl") and isinstance(kwargs["ttl"], int) and kwargs["ttl"] >= 60:
            self.ttl = kwargs["ttl"]
        # set proxies for connection between local to cloudflare
        self.http_proxies = CloudFlare.__get_http_proxies__(copy_proxy=True, **kwargs)
        # self.__setup_zone__()
        self.__init_zones__()

    @classmethod
    def __get_http_proxies__(cls, copy_proxy: bool = True, **kwargs):
        """
        create http proxies for request, it's a class method
        :param copy_proxy: if it's True: http_proxy will be same with https_proxy when just https_proxy is provoied; https_proxy will be same with http_proxy when just http_proxy is provoied. If it's False, no copy between http_proxy and https_proxy, if either http_proxy or https_proxy is provoided.
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
        t_http_proxies = CloudFlare.__get_http_proxies__(copy_proxy=False, **kwargs)
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
        t_http_proxies = CloudFlare.__get_http_proxies__(copy_proxy=True, **kwargs)
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
                    f"Request {url} using method - {method} with header {self.headers} and data {data}, got {str(e)}"
                )
                print("retry!")
                t_try += 1
            except Exception as e:
                return False, e
        return False, e

    @classmethod
    def get_zone_name(cls, domain: str, domain_class=-1):
        # split and strip
        domain_segments = domain.split(".")
        domain_segments = [domain.lower().strip() for domain in domain_segments]
        domain_segments = [domain for domain in domain_segments if len(domain) > 0]
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
            if "result_info" not in t_result_dict:
                raise CloudFlareError(f"Failed to get zone, 'Got: \n{t_result_dict}'")
            fetched += t_result_dict["result_info"]["count"]
            total_count = t_result_dict["result_info"]["total_count"]
            if fetched >= total_count:
                break
            else:
                page += 1

    def __init_records_for_zone__(self, zone_name, **kwargs):
        if zone_name not in self.zones:
            raise CloudFlareError(
                f"Can't find zone {zone_name} for you. Please check with Cloudflare!"
            )
        zone_id = self.zones[zone_name]["id"]
        # escape when init was done
        if (
                "records" in self.zones[zone_name]
                and len(self.zones[zone_name]["records"]) > 0
        ):
            return
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
                    f"Failed to get dns records for zone: \"{zone_name}\", 'Got: \n{t_result_dict}'"
                )
            for t_record in t_result_dict["result"]:
                # escape other than A AAAA CNAME
                if not is_valid_dns_type(t_record["type"]):
                    continue
                if t_record["name"] not in dns_records:
                    dns_records[t_record["name"]] = {}
                if t_record["type"] not in dns_records[t_record["name"]]:
                    dns_records[t_record["name"]][t_record["type"]] = {}
                dns_records[t_record["name"]][t_record["type"]][t_record["content"]] = (
                    t_record["id"]
                )
            if "result_info" not in t_result_dict:
                raise CloudFlareError(
                    f"Failed to get dns records for zone: \"{zone_name}\", 'Got: \n{t_result_dict}'"
                )
            fetched += t_result_dict["result_info"]["count"]
            total_count = t_result_dict["result_info"]["total_count"]
            if fetched >= total_count:
                break
            else:
                page += 1
        self.zones[zone_name]["records"] = dns_records

    def __get_records_for_zone__(self, zone_name):
        if zone_name not in self.zones:
            raise CloudFlareError(
                f"Can't find zone {zone_name} for you. Please check with Cloudflare!"
            )
        return self.zones[zone_name]["records"]

    def __init_records_for_sub_domain__(self, full_sub_domain, **kwargs):
        zone_name = self.__get_zone_name__(full_sub_domain)
        if zone_name not in self.zones:
            raise CloudFlareError(
                f"Can't find zone {zone_name} for you. Please check with Cloudflare!"
            )
        self.__init_records_for_zone__(zone_name, **kwargs)

    def __get_records_for_domain__(self, full_sub_domain: str):
        zone_name = self.__get_zone_name__(full_sub_domain)
        return self.__get_records_for_zone__(zone_name)

    def __get_records_for_domain_and_type__(self, full_sub_domain: str, dns_type: str):
        zone_name = self.__get_zone_name__(full_sub_domain)
        t_records = self.__get_records_for_zone__(zone_name)
        records = {}
        dns_type = dns_type.strip().upper()
        if full_sub_domain in t_records:
            t_t_records = t_records[full_sub_domain]
            if dns_type in t_t_records:
                records.update(t_t_records[dns_type])
        return records

    def __get_record_id_for_domain_type_and_content__(
            self, full_sub_domain: str, dns_type: str, content: str
    ):
        dns_type = dns_type.strip().upper()
        t_records = self.__get_records_for_domain_and_type__(full_sub_domain, dns_type)
        if content in t_records:
            return t_records[content]

    def __get_zone_id__(self, full_sub_domain: str):
        full_sub_domain = full_sub_domain.strip().strip(".").strip()
        zone_name = self.__get_zone_name__(full_sub_domain)
        return self.zones[zone_name]["id"]

    def __get_zone_name__(self, full_sub_domain: str):
        full_sub_domain = full_sub_domain.strip().strip(".").strip()
        for zone_name in self.zones:
            if full_sub_domain == zone_name:
                return zone_name
            if full_sub_domain.endswith("." + zone_name):
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
                f'Failed to create "{name}" records for zone: "{self.domain}", \'{t_result_dict}\''
            )
        t_record = t_result_dict["result"]
        # self.dns_records[t_record["id"]] = t_record
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
            urllib.parse.urljoin(self.api_url, zone_id + "/dns_records/" + record_id),
            "put",
            data=data,
            **kwargs,
        )
        if not t_succ or "result" not in t_result_dict:
            raise CloudFlareError(
                f'Failed to update "{name}: {dns_type}, {content}" records for zone: "{self.domain}", \'{t_result_dict}\''
            )
        self.dns_records[record_id] = t_result_dict
        return t_result_dict["result"]

    def __delete_record_by_id__(self, zone_id, record_id, **kwargs):
        """
        Delete a dns record
        :param zone_id:
        :param record_id:
        :return:
        """
        t_succ, t_result_dict = self.__request__(
            urllib.parse.urljoin(self.api_url, zone_id + "/dns_records/" + record_id),
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
        # del self.dns_records[record_id]
        return True, t_result_dict

    def refresh(self, **kwargs):
        """
        Shortcut for setup zone
        :return:
        """
        self.__set_http_proxies__(**kwargs)
        self.__init_zones__(**kwargs)
        # self.__setup_zone__(**kwargs)

    def create_records(self, name, dns_type, content_list, **kwargs):
        """
        Create a dns record
        :param dns_type:
        :param name:
        :param content_list:
        :param kwargs:
        :return:
        """
        name = name.lower()
        dns_type = dns_type.upper()
        self.__init_records_for_sub_domain__(name, **kwargs)
        content_list = list(set(content_list))
        if dns_type == "CNAME" and len(content_list) > 1:
            print(
                f"WARNING! Can't create more than one records for ({name}, {dns_type}), {dns_type} just one record permitted!"
            )
            return
        t_records_dict = self.__get_records_for_domain_and_type__(name, dns_type)
        ## just check for CNAME, CNAME need just one record
        # if dns_type == "CNAME" and len(t_records_list) > 1:
        #     print(f"WARNING! Escape exists record ({name}, {dns_type}, {t_content}), {dns_type} just one record permitted!")
        #     return
        # check records exist or not,
        #    keep the content and its record id.
        # t_exists_dict = {}
        t_non_exist_content = []
        for t_content in content_list:
            if t_content in t_records_dict:
                print(f"Escape existing record ({name}, {dns_type}, {t_content})")
            else:
                t_non_exist_content.append(t_content)
        # do create for non-exist records
        # t_created_dict = {}
        for t_content in t_non_exist_content:
            self.__create_one_record__(name, dns_type, t_content, **kwargs)
            # t_created_dict[(name, dns_type, t_content)] = t_result
            print(f"Succeed to created a record ({name}, {dns_type}, {t_content})")
            time.sleep(0.1)

    def create_records_new(self, records_dict: dict, **kwargs):
        """
        Create a dns record
        :param records_dict: {<name>: {<type>: {<content>: (ttl, proxied)}}}
        :param kwargs:
        :return:
        """
        for name in records_dict:
            name = name.lower()
            self.__init_records_for_sub_domain__(name, **kwargs)
            for dns_type in records_dict[name]:
                dns_type = dns_type.upper()
                t_records_dict = self.__get_records_for_domain_and_type__(
                    name, dns_type
                )
                t_non_exist_content = []
                for t_content in records_dict[name][dns_type]:
                    if t_content in t_records_dict:
                        print(
                            f"Escape existing record ({name}, {dns_type}, {t_content})"
                        )
                    else:
                        t_ttl, t_proxied = records_dict[name][dns_type][t_content]
                        t_non_exist_content.append((t_content, t_ttl, t_proxied))
                # do create for non-exist records
                # t_created_dict = {}
                for t_content, t_ttl, t_proxied in t_non_exist_content:
                    self.__create_one_record__(
                        name,
                        dns_type,
                        t_content,
                        ttl=t_ttl,
                        proxied=t_proxied,
                        **kwargs,
                    )
                    # t_created_dict[(name, dns_type, t_content)] = t_result
                    print(
                        f"Succeed to created a record ({name}, {dns_type}, {t_content})"
                    )
                    time.sleep(0.1)

    def delete_records(self, name, dns_type, content_list: list, **kwargs):
        """
        Delete a dns record
        :param name:
        :param dns_type:
        :param content_list: can be empty, delete all records which dns type is <dns_type>
        :return:
        """
        name = name.lower()
        dns_type = dns_type.upper()
        self.__init_records_for_sub_domain__(name, **kwargs)
        # reset proxies
        # self.__set_http_proxies__(**kwargs)
        zone_id = self.__get_zone_id__(name)
        t_record_dict = self.__get_records_for_domain_and_type__(name, dns_type)
        for content in t_record_dict:
            record_id = t_record_dict[content]
            # delete from remote server
            if content not in content_list:
                continue
            t_succ, _ = self.__delete_record_by_id__(zone_id, record_id, **kwargs)
            if t_succ:
                print(f"Succeed to delete [{name}, {dns_type}, {content}]")
            else:
                print(f"Warnig! Failed to delete [{name}, {dns_type}, {content}]")
            time.sleep(0.1)

    def delete_records_new(self, records_dict: dict, **kwargs):
        """
        Delete a dns record
        :param records_dict: {<name>: {<type>: {<content>: (ttl, proxied)}}}
        :param kwargs:
        :return:
        """
        for name in records_dict:
            name = name.lower()
            self.__init_records_for_sub_domain__(name, **kwargs)
            zone_id = self.__get_zone_id__(name)
            for dns_type in records_dict[name]:
                dns_type = dns_type.upper()
                t_current_record_dict = self.__get_records_for_domain_and_type__(
                    name, dns_type
                )
                for content in t_current_record_dict:
                    record_id = t_current_record_dict[content]
                    # if we give specific content to delete, then target must be the this content list;
                    # so, if a exist record not in our target list and the target list must have specific content provided, then it can be skipped
                    if (
                            len(records_dict[name][dns_type]) > 0
                            and content not in records_dict[name][dns_type]
                    ):
                        continue
                    t_succ, _ = self.__delete_record_by_id__(
                        zone_id, record_id, **kwargs
                    )
                    if t_succ:
                        print(f"Succeed to delete [{name}, {dns_type}, {content}]")
                    else:
                        print(
                            f"Warnig! Failed to delete [{name}, {dns_type}, {content}]"
                        )
                    time.sleep(0.1)

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
        zone_id = self.__get_zone_id__(name)
        self.__init_records_for_sub_domain__(name, **kwargs)
        # strip and remove duplicated item
        content_list = [str(content).strip() for content in content_list]
        content_list = list(set(content_list))
        if dns_type == "CNAME" and len(content_list) > 1:
            print(
                f"WARNING! Can't update more than one records for ({name}, {dns_type}), {dns_type} just one record permitted!"
            )
            return
        # clean
        t_records_dict = self.__get_records_for_domain_and_type__(name, dns_type)
        # scan content list, find all exist records and non-exist records
        t_non_exist_contents = []
        t_exist_contents = []
        for t_content in content_list:
            if t_content in t_records_dict:
                t_exist_contents.append(t_content)
            else:
                t_non_exist_contents.append(t_content)
        # find all extra records
        t_extra_records = []
        for t_content in t_records_dict:
            if t_content not in content_list:
                t_extra_records.append(t_content)
        # update for existing records
        for t_content in t_exist_contents:
            self.__update_record_by_id__(
                t_content["id"], name, dns_type, t_content, **kwargs
            )
            print(f"Update for ({name}, {dns_type}), {t_content})")
        # create non-exist records:
        for t_content in t_non_exist_contents:
            self.__create_one_record__(name, dns_type, t_content, **kwargs)
            print(f"Create ({name}, {dns_type}), {t_content})")
        # delete extra records
        for t_content in t_extra_records:
            self.__delete_record_by_id__(zone_id, t_records_dict[t_content], **kwargs)
            print(f"Delete ({name}, {dns_type}), {t_content})")

    def update_records_new(self, records_dict: dict, **kwargs):
        """
        Update dns record
        :param records_dict: {<name>: {<type>: {<content>: (ttl, proxied)}}}
        :param kwargs:
        :return:
        """
        for name in records_dict:
            name = name.lower()
            zone_id = self.__get_zone_id__(name)
            self.__init_records_for_sub_domain__(name, **kwargs)
            for dns_type in records_dict[name]:
                dns_type = dns_type.upper()
                # clean
                t_current_records_dict = self.__get_records_for_domain_and_type__(
                    name, dns_type
                )
                # scan content list, find all exist records and non-exist records
                t_non_exist_contents = []
                t_exist_contents = []
                for t_content in records_dict[name][dns_type]:
                    t_ttl, t_proxied = records_dict[name][dns_type][t_content]
                    if t_content in t_current_records_dict:
                        t_exist_contents.append((t_content, t_ttl, t_proxied))
                    else:
                        t_non_exist_contents.append((t_content, t_ttl, t_proxied))
                # find all extra records
                t_extra_records = []
                for t_content in t_current_records_dict:
                    if t_content not in records_dict[name][dns_type]:
                        t_extra_records.append(t_content)
                # update for existing records
                for t_content, t_ttl, t_proxied in t_exist_contents:
                    t_record_id = t_current_records_dict[t_content]
                    self.__update_record_by_id__(
                        t_record_id,
                        name,
                        dns_type,
                        t_content,
                        ttl=t_ttl,
                        proxied=t_proxied,
                        **kwargs,
                    )
                    print(f"Update for [{name}, {dns_type}, {t_content}]")
                # update t_extra_records with records in t_non_exist_contents:
                while len(t_non_exist_contents) > 0:
                    t_content, t_ttl, t_proxied = t_non_exist_contents[0]
                    if len(t_extra_records) > 0:
                        t_record_id = t_current_records_dict[t_extra_records[0]]
                        self.__update_record_by_id__(
                            t_record_id,
                            name,
                            dns_type,
                            t_content,
                            ttl=t_ttl,
                            proxied=t_proxied,
                            **kwargs,
                        )
                        print(
                            f"Update to {t_content} [{name}, {dns_type}, {t_extra_records[0]}]"
                        )
                        del t_extra_records[0]
                    else:
                        # no more records for update, just create
                        self.__create_one_record__(
                            name,
                            dns_type,
                            t_content,
                            ttl=t_ttl,
                            proxied=t_proxied,
                            **kwargs,
                        )
                        print(f"Create [{name}, {dns_type}, {t_content}]")
                    del t_non_exist_contents[0]
                # delete extra records
                for t_content in t_extra_records:
                    t_record_id = t_current_records_dict[t_content]
                    self.__delete_record_by_id__(zone_id, t_record_id, **kwargs)
                    print(f"Delete [{name}, {dns_type}, {t_content}]")


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ("yes", "true", "t", "y", "1"):
        return True
    elif v.lower() in ("no", "false", "f", "n", "0"):
        return False
    else:
        raise argparse.ArgumentTypeError("BooleTEMPOUTBOUNDVNEXTan value expected.")


def print_logs(t_u: list, t_c: list, t_d: list, t_k: list):
    if len(t_u) > 0:
        print("Update for:")
        for t_i in t_u.keys():
            print(f'"{t_i[0]}" - "{t_i[1]}" - "{t_i[2]}"')
            print(t_u[t_i])
    if len(t_c) > 0:
        print("Create for:")
        for t_i in t_c.keys():
            print(f'"{t_i[0]}" - "{t_i[1]}" - "{t_i[2]}"')
            print(t_c[t_i])
    if len(t_d) > 0:
        print("Delete for:")
        for t_i in t_d.keys():
            print(f'"{t_i[0]}" - "{t_i[1]}" - "{t_i[2]}"')
            print(t_d[t_i])
    if len(t_k) > 0:
        print("Keep for:")
        for t_i in t_k.keys():
            print(f'"{t_i[0]}" - "{t_i[1]}" - "{t_i[2]}"')
            print(t_k[t_i])


def gen_content_dict(dns_type: str, content: list, ttl: int, proxied: bool):
    t_content_dict = {dns_type: {}}
    t_content_list = []
    t_re_rules = re.compile("[;,|]+")
    for t in content:
        t_list = t_re_rules.split(str(t))
        t_content_list.extend(t_list)
    t_content_list = list(set(t_content_list))
    for t in t_content_list:
        t_content_dict[dns_type][t] = (ttl, proxied)
    return t_content_dict


def is_valid_dns_type(dns_type: str):
    return dns_type.upper() in valid_record_type


def main():
    print(f"cloudflare-ddns {VERSION}")
    print("  - a DDNS helper for Cloudflare.")
    print('  - create, delete or update dns record for dns type "A|AAAA|CNAME".')
    print("")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-e",
        "--email",
        action="store",
        dest="email",
        type=str,
        help="Email for your cloudflare account",
    )
    parser.add_argument(
        "-k",
        "--api-key",
        action="store",
        dest="api_key",
        type=str,
        help="API Key of your cloudflare account",
    )
    cmd_group = parser.add_mutually_exclusive_group(required=False)
    cmd_group.add_argument(
        "-u",
        "--update-record",
        action="append",
        dest="u_domain",
        type=str,
        help="domain for update",
    )
    cmd_group.add_argument(
        "-a",
        "--add-record",
        action="append",
        dest="a_domain",
        type=str,
        help="domain for add",
    )
    cmd_group.add_argument(
        "-d",
        "--delete-record",
        action="append",
        dest="d_domain",
        type=str,
        help="domain for delete",
    )
    cmd_group.add_argument(
        "-r",
        "--raw",
        action="append",
        dest="raw",
        type=str,
        help='raw record for update, each line: "name,dns_type,content,ttl,proxied"',
    )
    cmd_group.add_argument(
        "--raw-file",
        action="store",
        dest="raw_file",
        type=str,
        help='file store raw for update, each line: "name,dns_type,content,ttl,proxied"',
    )
    parser.add_argument(
        "--alias",
        action="append",
        dest="alias",
        type=str,
        help="alias of domain while do add or update. For example, '-a zhfreal.top,zhfreal.nl --alias ww1,ww2 --cname-alias w1'",
    )
    parser.add_argument(
        "-4",
        "--ipv4",
        action="append",
        dest="ipv4_addr",
        type=str,
        help="IPv4 address for action",
    )
    parser.add_argument(
        "-6",
        "--ipv6",
        action="append",
        dest="ipv6_addr",
        type=str,
        help="IPv6 address for action",
    )
    parser.add_argument(
        "-c", "--cname", action="store", dest="cname", type=str, help="cname for action"
    )
    parser.add_argument(
        "--cname-alias",
        action="store",
        dest="cname_alias",
        type=str,
        help="alias of cname content while do add or update. For example, '-a zhfreal.top,zhfreal.nl --alias ww1 --cname-alias w1'",
    )
    parser.add_argument(
        "--dns-type",
        action="append",
        dest="dns_type",
        type=str,
        help="dns type for delete",
    )
    parser.add_argument(
        "-t",
        "--ttl",
        action="store",
        default=60,
        dest="ttl",
        type=int,
        help="ttl for record",
    )
    parser.add_argument(
        "--proxied",
        action="store",
        default=False,
        dest="proxied",
        type=str2bool,
        help="It should be proxied",
    )
    parser.add_argument(
        "--raw-alias",
        action="append",
        dest="raw_alias",
        type=str,
        help="alias of raw content while do add or update. For example, "
             "'-a|u zhfreal.top,zhfreal.nl --raw-alias ww1,A,1.1.1.1,60,false'; "
             "'-a|u zhfreal.top,zhfreal.nl --raw-alias ww1,CNAME,w1.zhfreal.top,60,false'"
             "'-a|u zhfreal.top,zhfreal.nl --raw-alias ww1,CNAME,w1,60,false'",
    )
    parser.add_argument(
        "--raw-alias-file",
        action="store",
        dest="raw_alias_file",
        type=str,
        help="alias of raw content while do add or update. For example, "
             "'-a|u zhfreal.top,zhfreal.nl --raw-alias ww1,A,1.1.1.1,60,false'; "
             "'-a|u zhfreal.top,zhfreal.nl --raw-alias ww1,CNAME,w1.zhfreal.top,60,false'"
             "'-a|u zhfreal.top,zhfreal.nl --raw-alias ww1,CNAME,w1,60,false'",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="store_true",
        dest="version",
        default=False,
        help="show version",
    )
    args = parser.parse_args()
    if args.version:
        sys.exit(0)
    if not args.email or len(args.email) == 0:
        print("No email!")
        sys.exit(1)
    if not args.api_key or len(args.api_key) == 0:
        print("No API Key!")
        sys.exit(1)
    t_domains_list = []
    t_add_records = 0
    t_update_records = 0
    t_delete_records = 0
    t_records_dict = {}
    t_raw_list = []
    if args.u_domain and len(args.u_domain) > 0:
        t_domains_list = args.u_domain
        t_update_records = 1
    elif args.a_domain and args.a_domain and len(args.a_domain) > 0:
        t_domains_list = args.a_domain
        t_add_records = 1
    elif args.d_domain and len(args.d_domain) > 0:
        t_domains_list = args.d_domain
        t_delete_records = 1
    elif args.raw and len(args.raw) > 0:
        ### raw data like： name,dns_type,content,ttl,proxied
        t_update_records = 1
        t_raw_list.extend(args.raw)
    elif args.raw_file and len(args.raw_file) > 0:
        t_update_records = 1
        try:
            with open(args.raw_file, "r") as fp:
                t_content_list = fp.readlines()
                t_raw_list.extend(
                    [item.strip() for item in t_content_list if len(item.strip())]
                )
        except Exception as E:
            print(f"failed to read --raw-file {args.raw_file}")
            raise E
    else:
        print("No valid cmd provided!")
        sys.exit(1)
    # resolve raw
    t_raw_list = list(set(t_raw_list))
    if len(t_raw_list) > 0:
        t_re_rules = re.compile("[;,|]+")
        for t_raw in t_raw_list:
            t_item_list = t_re_rules.split(str(t_raw))
            if len(t_item_list) != 5:
                print(f"invalid raw record for udpate {t_raw}")
                sys.exit(1)
            name, t_dns_type, content, ttl, proxied = t_item_list
            if name not in t_records_dict:
                t_records_dict[name] = {}
            if t_dns_type not in t_records_dict[name]:
                t_records_dict[name][t_dns_type] = {}
            try:
                t_ttl = int(ttl)
                t_proxied = str2bool(proxied)
                t_records_dict[name][t_dns_type][content] = (t_ttl, t_proxied)
            except Exception as E:
                print(
                    f'Either ttl - {ttl} or proxied - {proxied} isn\'t valid in  <--raw> - "{t_raw}"'
                )
                sys.exit(1)
    # read raw-alias
    t_raw_alias_list = []
    if args.raw_alias and len(args.raw_alias) > 0:
        t_raw_alias_list.extend(args.raw_alias)
    if args.raw_alias_file and len(args.raw_alias_file) > 0:
        try:
            with open(args.raw_alias_file, "r") as fp:
                t_content_list = fp.readlines()
                t_raw_alias_list.extend(
                    [item.strip() for item in t_content_list if len(item.strip()) > 0]
                )
        except Exception as e:
            print(f"failed to read --raw-alias-file {args.raw_alias_file}")
            raise e
    t_raw_alias_list = list(set(t_raw_alias_list))
    t_re_rules = re.compile("[;,|]+")
    t_raw_alias_resolved_list = []
    for t_raw in t_raw_alias_list:
        t_raw = str(t_raw)
        # skip empty line
        if len(t_raw) == 0:
            continue
        t_item_list = t_re_rules.split(str(t_raw))
        if len(t_item_list) != 5:
            print(f"invalid raw record for udpate {t_raw}")
            sys.exit(1)
        name, t_dns_type, content, ttl, proxied = t_item_list
        if not is_valid_dns_type(t_dns_type):
            continue
        try:
            t_ttl = int(ttl)
            t_proxied = str2bool(proxied)
            t_raw_alias_resolved_list.append(
                (name, t_dns_type, content, t_ttl, t_proxied)
            )
        except Exception as E:
            print(
                f'Either ttl - {ttl} or proxied - {proxied} isn\'t valid in  <--raw> - "{t_raw}"'
            )
            sys.exit(1)
    # args.alias
    t_alias_list = []
    if args.alias and len(args.alias) > 0:
        t_re_rules = re.compile("[;,|]+")
        for t_alias in args.alias:
            t_t_alias_list = t_re_rules.split(str(t_alias))
            t_t_alias_list = [
                item.strip() for item in t_t_alias_list if len(item.strip()) > 0
            ]
            t_alias_list.extend(t_t_alias_list)
    # splite domains in t_domains_list, while do "-a|-u|-d"
    if len(t_domains_list) > 0:
        t_n_domains_list = []
        t_re_rules = re.compile("[;,|]+")
        for t_domain_t in t_domains_list:
            t_domains = t_re_rules.split(str(t_domain_t))
            t_n_domains_list.extend(t_domains)
        t_n_domains_list = [
            item.strip() for item in t_n_domains_list if len(item.strip()) > 0
        ]
        t_domains_list = list(set(t_n_domains_list))
        for r_domain in t_domains_list:
            t_domain = r_domain
            if t_add_records == 1 or t_update_records == 1:
                for (
                        t_alias,
                        t_dns_type,
                        t_c,
                        t_ttl,
                        t_proxied,
                ) in t_raw_alias_resolved_list:
                    t_domain = t_alias + "." + r_domain
                    t_dns_type = str(t_dns_type).upper()
                    # t_c is a prefix
                    if t_dns_type == "CNAME" and "." not in t_c:
                        t_c = t_c + "." + r_domain
                    if t_domain not in t_records_dict:
                        t_records_dict[t_domain] = {}
                    t_records_dict[t_domain].update(
                        gen_content_dict(t_dns_type, [t_c], t_ttl, t_proxied)
                    )
            t_t_domains_list = []
            if len(t_alias_list) > 0:
                t_t_domains_list.extend(
                    [t_alias + "." + r_domain for t_alias in t_alias_list]
                )
            else:
                t_t_domains_list.append(r_domain)
            for t_domain in t_t_domains_list:
                if t_domain not in t_records_dict:
                    t_records_dict[t_domain] = {}
                if args.ipv4_addr and len(args.ipv4_addr) > 0:
                    t_dns_type = "A"
                    t_records_dict[t_domain].update(
                        gen_content_dict(
                            t_dns_type, args.ipv4_addr, args.ttl, args.proxied
                        )
                    )
                if args.ipv6_addr and len(args.ipv6_addr) > 0:
                    t_dns_type = "AAAA"
                    t_records_dict[t_domain].update(
                        gen_content_dict(
                            t_dns_type, args.ipv6_addr, args.ttl, args.proxied
                        )
                    )
                if args.cname and len(args.cname) > 0:
                    t_dns_type = "CNAME"
                    t_records_dict[t_domain].update(
                        gen_content_dict(
                            t_dns_type, [args.cname], args.ttl, args.proxied
                        )
                    )
                if args.cname_alias and len(args.cname_alias) > 0:
                    t_dns_type = "CNAME"
                    t_cname = args.cname_alias + "." + r_domain
                    t_records_dict[t_domain].update(
                        gen_content_dict(
                            t_dns_type, [t_cname], args.ttl, args.proxied
                        )
                    )
                if (
                        t_delete_records == 1
                        and args.dns_type
                        and len(args.dns_type) > 0
                ):
                    for t_dns_type in args.dns_type:
                        t_dns_type = str(t_dns_type).upper()
                        if not is_valid_dns_type(t_dns_type):
                            print(
                                f"Invalid record type, {t_dns_type}, should be one of {valid_record_type}"
                            )
                            sys.exit(1)
                        t_records_dict[t_domain].update(
                            gen_content_dict(t_dns_type, [], args.ttl, args.proxied)
                        )
    # do data check
    for t_records in t_records_dict.values():
        # CNAME can't work with A or AAAA
        if ("A" in t_records or "AAAA" in t_records) and "CNAME" in t_records:
            print("CNAME record can't work with A or AAAA records")
            sys.exit(1)
        # CNAME can't have more than one
        if "CNAME" in t_records and len(t_records["CNAME"]) > 1:
            print("CNAME can't have more than one records")
            sys.exit(1)
        if t_add_records == 1 or t_update_records == 1:
            if (
                    ("A" not in t_records or len(t_records["A"]) == 0)
                    and ("AAAA" not in t_records or len(t_records["AAAA"]) == 0)
                    and ("CNAME" not in t_records or len(t_records["CNAME"]) == 0)
            ):
                print(
                    "No A, AAAA or CNAME provoided while do records adding or updating"
                )
                sys.exit(1)
        else:
            if (
                    "A" not in t_records
                    and "AAAA" not in t_records
                    and "CNAME" not in t_records
            ):
                print("No A, AAAA or CNAME provoided while do records deletion")
                sys.exit(1)
    # do cloudflare api init
    cf = CloudFlare(email=args.email, api_key=args.api_key, domain="")
    if t_update_records == 1:
        cf.update_records_new(t_records_dict)
    elif t_add_records == 1:
        cf.create_records_new(t_records_dict)
    elif t_delete_records == 1:
        cf.delete_records_new(t_records_dict)
    else:
        print("Invalid operation!")


if __name__ == "__main__":
    main()
