# ensure an rpc peer is added
def addpeer(p, rpcpeer):
    pid = rpcpeer['id']
    if pid not in p.persist['peerstate']:
        p.persist['peerstate'][pid] = {
            'connected': rpcpeer['connected'],
            'avail': 1.0 if rpcpeer['connected'] else 0.0
        }


# exponetially smooth online/offline states of peers
def trace_availability(p, rpcpeers):
    p.persist['availcount'] += 1
    leadwin = max(min(p.avail_window, p.persist['availcount'] * p.avail_interval), p.avail_interval)
    samples = leadwin / p.avail_interval
    alpha = 1.0 / samples
    beta = 1.0 - alpha

    for rpcpeer in rpcpeers['peers']:
        pid = rpcpeer['id']
        addpeer(p, rpcpeer)

        if rpcpeer['connected']:
            p.persist['peerstate'][pid]['connected'] = True
            p.persist['peerstate'][pid]['avail'] = 1.0 * alpha + p.persist['peerstate'][pid]['avail'] * beta
        else:
            p.persist['peerstate'][pid]['connected'] = False
            p.persist['peerstate'][pid]['avail'] = 0.0 * alpha + p.persist['peerstate'][pid]['avail'] * beta
