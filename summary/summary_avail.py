# This is the persist object structure:
#
# {
#   "p": {              # peerstate
#      "PEER_ID" : {    # the peers id
#         "c": True,    # connected or not
#         "a": 1.0      # the availability value
#      }
#   },
#   "r": 123,           # the number of runs
#   "v": 1              # version
# }


# ensure an rpc peer is added
def addpeer(p, rpcpeer):
    pid = rpcpeer['id']
    if pid not in p.persist['p']:
        p.persist['p'][pid] = {
            'c': rpcpeer['connected'],
            'a': 1.0 if rpcpeer['connected'] else 0.0
        }


# exponetially smooth online/offline states of peers
def trace_availability(p, rpcpeers):
    p.persist['r'] += 1
    leadwin = max(min(p.avail_window, p.persist['r'] * p.avail_interval), p.avail_interval)
    samples = leadwin / p.avail_interval
    alpha = 1.0 / samples
    beta = 1.0 - alpha

    for rpcpeer in rpcpeers['peers']:
        pid = rpcpeer['id']
        addpeer(p, rpcpeer)

        if rpcpeer['connected']:
            p.persist['p'][pid]['c'] = True
            p.persist['p'][pid]['a'] = 1.0 * alpha + p.persist['p'][pid]['a'] * beta
        else:
            p.persist['p'][pid]['c'] = False
            p.persist['p'][pid]['a'] = 0.0 * alpha + p.persist['p'][pid]['a'] * beta
