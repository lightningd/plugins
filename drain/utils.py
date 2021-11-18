import time

TIMEOUT = 60


# we need to have this pyln.testing.utils code duplication
# as this also needs to be run without testing libs
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
    return [c for c in node.rpc.listfunds()['channels'] if c.get('short_channel_id') == scid][0]['our_amount_msat']


# returns their_amount_msat for a given node and scid
def get_theirs(node, scid):
    ours = get_ours(node, scid)
    total = [c for c in node.rpc.listfunds()['channels'] if c.get('short_channel_id') == scid][0]['amount_msat']
    return total - ours


# these wait for the HTLC commit settlement to change our/their amounts
def wait_ours(node, scid, ours_before):
    wait_for(lambda: ours_before != get_ours(node, scid))
    return get_ours(node, scid)
