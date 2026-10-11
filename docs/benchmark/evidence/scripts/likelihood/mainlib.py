"""Main population: match alerts to ground-truth events (scoring side only) and expose (alert, true cause, event)."""
import pickle, collections, sys
sys.path.insert(0, "/tmp/research/likelihood"); sys.path.insert(0, "/tmp/research/likelihood/scripts")
import common
H = 3600 * 1000
C3_TEMPLATES = {"replay": ["range", "sched", "hold", "resp", "sys"], "injection_naive": ["range", "hold", "resp", "sched", "sys"],
                "injection_informed": ["range", "resp", "hold", "sys"], "dispense_forgery": ["count", "hold", "resp", "int"],
                "presence_spoof": ["int"], "dispenser_physical_tamper": ["count", "hold", "resp", "int"],
                "timestamp_manipulation": ["sched", "hold", "range", "resp"]}
SILENT = {"stuck_at", "cuff_silent_bias", "dispenser_bounce"}


def load(tag):
    return pickle.load(open(f"{common.ROOT}/out/main_{tag}.pkl", "rb"))


def event_templates(g, log):
    cls, sub, tmpl, onset, end, inj = g
    if tmpl is not None:
        return [tmpl]
    if cls == "C3":
        return C3_TEMPLATES.get(sub, [])
    for l in log:
        if l["cls"] == cls and l["subtype"] == sub and l["onset_ms"] == onset and l["templates"]:
            return list(l["templates"])
    for l in log:
        if l["cls"] == cls and l["subtype"] == sub and l["templates"]:
            return list(l["templates"])
    return []


def first_decidable(g):
    cls, sub, tmpl, onset, end, inj = g
    return end if (cls == "C1" and end is not None) else onset


def match_day(day, window_ms=24 * H, priority="injected"):
    """Greedy one-to-one matching as ralmon.eval.metrics.match_events (events by reference time, earliest free compatible
    alert), with a template-compatibility condition and an alert window [ref, ref + window]. priority='injected':
    injected events take their alerts first. Returns list of (alert, event, n_compatible_causes)."""
    evs = [(g, event_templates(g, day["log"])) for g in day["gt"]]
    order = sorted(range(len(evs)), key=lambda i: (0 if (priority == "injected" and evs[i][0][5]) else 1, first_decidable(evs[i][0]), i))
    alerts = sorted(day["alerts"], key=lambda a: a["decided"])
    taken = set(); out = []
    for i in order:
        g, tm = evs[i]
        ref = first_decidable(g)
        end = g[4] if g[4] is not None else g[3]
        for a in alerts:
            if id(a) in taken or a["template"] not in tm:
                continue
            if ref <= a["decided"] <= max(ref, end) + window_ms:
                taken.add(id(a)); out.append((a, g)); break
    return out, [a for a in alerts if id(a) not in taken]


def label_alerts(day, window_ms=24 * H):
    """Many-to-one labelling: for each alert the set of ground-truth events (scoring side) whose template and time are
    compatible. Returns list of (alert, [events])."""
    evs = [(g, event_templates(g, day["log"])) for g in day["gt"]]
    out = []
    for a in day["alerts"]:
        comp = []
        for g, tm in evs:
            if a["template"] not in tm:
                continue
            ref = first_decidable(g)
            end = g[4] if g[4] is not None else g[3]
            if ref <= a["decided"] <= max(ref, end) + window_ms:
                comp.append(g)
        out.append((a, comp))
    return out


def truth_of(comp, mode="strict"):
    """cause of the alert from its compatible events; None = false alarm (no event), 'AMB' = ambiguous."""
    if not comp:
        return None, None
    causes = {g[0] for g in comp}
    if len(causes) == 1:
        return next(iter(causes)), sorted(comp, key=lambda g: g[5], reverse=True)[0]
    if mode == "injected":
        inj = {g[0] for g in comp if g[5]}
        if len(inj) == 1:
            c = next(iter(inj)); return c, [g for g in comp if g[0] == c and g[5]][0]
    return "AMB", comp[0]
