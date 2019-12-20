import time

TIMEOUT=60


def wait_for(success, timeout=TIMEOUT):
    start_time = time.time()
    interval = 0.25
    while not success() and time.time() < start_time + timeout:
        time.sleep(interval)
        interval *= 2
        if interval > 5:
            interval = 5
    if time.time() > start_time + timeout:
        raise ValueError("Timeout waiting for {}", success)


# waits for a bunch of nodes HTLCs to settle
def wait_for_all_htlcs(nodes):
    for n in nodes:
        n.wait_for_htlcs()


# returns our_amount_msat for a given node and scid
def get_ours(node, scid):
    return [c for c in node.rpc.listfunds()['channels'] if c['short_channel_id'] == scid][0]['our_amount_msat']


# these wait for the HTLC commit settlement
def wait_ours(node, scid, ours_before):
    wait_for(lambda: ours_before != get_ours(node, scid))
    return get_ours(node, scid)


def wait_ours_above(node, scid, value):
    wait_for(lambda: get_ours(node, scid) > value)
    return get_ours(node, scid)


def wait_ours_below(node, scid, value):
    wait_for(lambda: get_ours(node, scid) < value)
    return get_ours(node, scid)


