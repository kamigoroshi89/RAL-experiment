import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import numpy as np
from cuff_vs_art import load, pair
out, excl, total = pair(load(), w=30.0, span_max=40.0)
x = np.concatenate(list(out.values()))
y = x[np.abs(x) <= 50]
print("main all: n=%d mean=%.2f sd=%.2f" % (len(x), x.mean(), x.std(ddof=1)))
print("post-hoc |d|<=50: n=%d mean=%.2f sd=%.2f dropped=%s" % (len(y), y.mean(), y.std(ddof=1), x[np.abs(x) > 50]))
