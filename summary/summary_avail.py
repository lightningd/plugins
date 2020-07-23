from datetime import datetime

# ensure an rpc peer is added
def addpeer(p, rpcpeer):
    pid = rpcpeer['id']
    if not pid in p.avail_peerstate:
        p.avail_peerstate[pid] = {
            'connected' : rpcpeer['connected'],
            'last_seen' : datetime.now() if rpcpeer['connected'] else None,
            'avail' : 1.0 if rpcpeer['connected'] else 0.0
        }


# exponetially smooth online/offline states of peers
def trace_availability(p, rpcpeers):
    p.avail_count += 1
    leadwin = max(min(p.avail_window, p.avail_count * p.avail_interval), p.avail_interval)
    samples = leadwin / p.avail_interval
    alpha   = 1.0 / samples
    beta    = 1.0 - alpha

    for rpcpeer in rpcpeers['peers']:
        pid = rpcpeer['id']
        addpeer(p, rpcpeer)

        if rpcpeer['connected']:
            p.avail_peerstate[pid]['last_seen'] = datetime.now()
            p.avail_peerstate[pid]['connected'] = True
            p.avail_peerstate[pid]['avail']     = 1.0 * alpha + p.avail_peerstate[pid]['avail'] * beta
        else:
            p.avail_peerstate[pid]['connected'] = False
            p.avail_peerstate[pid]['avail']     = 0.0 * alpha + p.avail_peerstate[pid]['avail'] * beta
