#!/usr/bin/env python
# coding: utf8

"""
一个干净的DNS
"""

from pickle import dumps, loads
from random import choice
import socket
from SocketServer import UDPServer, DatagramRequestHandler
# from threading import Thread
from time import time

from dnslib import DNSRecord, DNSQuestion

from redis import StrictRedis


# DNS 记录缓存时间为 六小时
RECORD_CACHE_TIME = 6 * 60 * 60
# 客户端请求频率限制为 一分钟一百次
FREQUENCY_TIMES = 100
FREQUENCY_SECONDS = 60
# 各仓库号预定义
FREQUENCY_DB_NO = 0
CACHE_DB_NO = 1
SETUP_DOMAIN_DB_NO = 2
GRAY_DOMAIN_DB_NO = 3


class CleanDNSHandler(DatagramRequestHandler):

    def __init__(self, request, client_address, server):
        self.request = request
        self.client_address = client_address
        self.server = server
        self.setup()
        try:
            self.handle()
        except StandardError, error_message:
            log.exception(error_message)
        else:
            self.finish()
        finally:
            log.info("client_ip: {}, query_id: {}, qname: {}, qtype: {}".format(
                self.client_address[0],
                self.query_id, self.qname, self.qtype))

    def IP_frequency(self):
        # IP_int = reduce(lambda i, j: i*2**8 + int(j),
        #                 self.client_address[0].split("."))
        frequency_key = "IP:{}".format(self.client_address[0])
        IP_frequency = frequency_db.hgetall(frequency_key)
        time_now = int(time())
        if not IP_frequency:
            frequency_db.hmset(
                frequency_key, "token", 99, "timestamp", time_now)
            return

        token_should_be = int(
            (time_now - IP_frequency["timestamp"]
             ) / FREQUENCY_SECONDS * FREQUENCY_TIMES
        ) + IP_frequency["token"]
        if token_should_be > FREQUENCY_TIMES:
            token_should_be = FREQUENCY_TIMES
        assert token_should_be >= 1

        frequency_db.hmset(
            frequency_key, "token", token_should_be-1, "timestamp", time_now)

    def parse(self):
        query_parse_ret = DNSRecord.parse(self.packet)

        query_opcode = query_parse_ret.header.get_opcode()
        if query_opcode == 0:
            pass
        elif query_opcode == 1:
            # reverse query
            pass
        elif query_opcode == 2:
            # server status query
            pass
        else:
            raise NotImplementedError

        self.query_id = query_parse_ret.header.id
        self.qname = str(query_parse_ret.q.qname)
        self.qtype = query_parse_ret.q.qtype

    def cache_hit(self):
        cache_key = "cache:{}:{}".format(self.qtype, self.qname)
        cache_ret = cache_db.get(cache_key)
        if cache_ret:
            log.info("cache_hit: {}".format(self.query_id))
            response_packet = DNSRecord()
            response_packet.header.id = self.query_id
            response_packet.add_question(DNSQuestion(self.qname))
            for answer in loads(cache_ret):
                response_packet.add_answer(answer)
            log.info(response_packet.__str__())
            log.info("DNS response id {}".format(self.query_id))
            response_packet_str = response_packet.pack().__str__()
            self.wfile.write(response_packet_str)
            return True

    def white_list_check(self):
        if self.qname.endswith(".cn") or self.qname.endswith(".cn."):
            return True
        white_qname_key = "white_list:{}".format(self.qname)
        return setup_domain_db.exists(white_qname_key)

    def black_list_check(self):
        black_qname_key = "black_list:{}".format(self.qname)
        return setup_domain_db.exists(black_qname_key)

    def request_upstream_DNS(self):
        log.info("request the upstream DNS")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect((self.selected_DNS, 53))
        sock.send(self.packet)
        response_packet = sock.recv(1024)
        self.wfile.write(response_packet)

        cache_key = "cache:{}:{}".format(self.qtype, self.qname)
        response_parse_ret = DNSRecord.parse(response_packet)
        cache_db.setex(
            cache_key, RECORD_CACHE_TIME, dumps(response_parse_ret.rr))

    def handle(self):
        """
        处理DNS请求的主体流程
        """
        # 请求IP频率检查 防止被反射放大攻击者利用
        # self.IP_frequency()
        # 请求包解析
        self.parse()
        # cache 检查
        if self.cache_hit():
            return

        # 缓存里面没有 选定上游DNS
        if self.white_list_check():
            # white DNS 114.114.114.114 223.5.5.5
            self.selected_DNS = choice(["114.114.114.114", "223.5.5.5"])
        elif self.black_list_check():
            # black DNS 8.8.8.8 8.8.4.4 208.67.222.222 208.67.220.220
            # self.selected_DNS = choice([
            #     "8.8.8.8", "8.8.4.4", "208.67.222.222", "208.67.220.220"])
            self.selected_DNS = "8.8.8.8"
        else:
            # use white DNS and push into check list
            self.selected_DNS = "8.8.8.8"
            gray_domain_db.sadd("gray_list", self.qname)

        # 请求上游DNS
        self.request_upstream_DNS()

if __name__ == "__main__":
    from logging import StreamHandler
    stream_handler = StreamHandler()
    from logging import Formatter
    formatter = Formatter(
        fmt='%(asctime)s %(lineno)d %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')
    stream_handler.setFormatter(formatter)
    from logging import getLogger
    log = getLogger(__name__)
    log.addHandler(stream_handler)
    from logging import INFO
    log.setLevel(INFO)

    frequency_db = StrictRedis(db=FREQUENCY_DB_NO)
    cache_db = StrictRedis(db=CACHE_DB_NO)
    setup_domain_db = StrictRedis(db=SETUP_DOMAIN_DB_NO)
    gray_domain_db = StrictRedis(db=GRAY_DOMAIN_DB_NO)

    server = UDPServer(("0.0.0.0", 53), CleanDNSHandler)
    log.info("DNS server start at 0.0.0.0:5353")
    server.serve_forever()
    # server_thread = Thread(target=server.serve_forever)
    # server_thread.daemon = False
    # server_thread.start()
