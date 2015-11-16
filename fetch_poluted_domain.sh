#!/bin/bash
# utf8

#################################################################
# find which domain is polute by the GFW from the alexas top 1M #
#
# download top-1m.csv from 
# https://support.alexa.com/hc/en-us/articles/
# 200449834-Does-Alexa-have-a-list-of-its-top-ranked-websites-
#
# Note that this list is based on the 1 month average Traffic Rank
# , not the 3-month average traffic rank.  The list is updated daily.
#################################################################

function dig_test {
    BEINGLESS_SERVER='101.200.190.85'
	result=$(dig +time=1 +tries=1 +short @$BEINGLESS_SERVER $1)

	if [[ $result != *"servers could be reached"* ]]
	then
		echo $1 >> ./poluted_domain_optimized_by_xargs.txt
	fi
}

export -f dig_test

cat top-1m.csv \
	| cut -d , -f 2 \
	| xargs -P100 -n1 -I% bash -c 'dig_test %'
