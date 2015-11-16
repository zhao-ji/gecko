#!/bin/bash
#coding: utf8

#######################################
# setup black and white list in redis #
#######################################


function set_up {
    redis-cli -h localhost -p 6379 -n 2 set "$1:$2" ''
}

export -f set_up
redis-cli -h localhost -p 6379 -n 2 flushdb
cat china_domain.txt|xargs -P100 -n 1 -I % bash -c "set_up white_list %"
cat block_domain.txt|xargs -P100 -n 1 -I % bash -c "set_up black_list %"
