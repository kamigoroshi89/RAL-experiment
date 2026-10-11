import pickle, json, collections, sys
sys.path.insert(0,'/tmp/research/likelihood/scripts')
import common
r1 = pickle.load(open(f"{common.ROOT}/out/pairs_p40_sw1.pkl","rb"))
r0 = pickle.load(open(f"{common.ROOT}/out/pairs_p40_sw0.pkl","rb"))
old = [json.loads(l) for l in open('/tmp/research/pairs/probe_p40.jsonl')]
key = lambda r: (r['group'], r['variant'], r['ordinal'])
oldd = {key(r): r for r in old}
# 1. reproduction of the old probe: same (template, key, kappa, t) alerts under profile 'off' (probe profile)
mism = 0; tot = 0; kappa_c = collections.Counter()
for r in r1:
    o = oldd[key(r)]
    for m in "AB":
        mine = sorted((a['template'], a['key'], a['old_off'], a['decided']) for a in r[m]['alerts'])
        # the probe stored (tau, key, kappa, verdict, t_ms); t_ms is the alert t; compare on (tau,key,kappa)
        theirs = sorted((x[0], x[1], x[2]) for x in o[m]['alerts'] if x[3] == 'violated')
        mm = sorted((a, b, c) for a, b, c, d in mine)
        tot += 1
        if mm != theirs: mism += 1
        for a in r[m]['alerts']: kappa_c[a['old_off']] += 1
print("members compared", tot, "mismatching alert lists", mism, kappa_c)
# 2. switch 0 == profile off at switch 1 (diagnostics capability without reports = None)
import dataclasses
diff = 0; n = 0
for a, b in zip(r1, r0):
    for m in "AB":
        for x, y in zip(a[m]['alerts'], b[m]['alerts']):
            n += 1
            if x['ev_off'] != y['ev_on'] or x['ev_off'] != y['ev_off']: diff += 1
print("alerts", n, "ev_off(sw1) != ev(sw0):", diff)
