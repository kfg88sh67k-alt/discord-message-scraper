"""Runs the default analysis: words + messages pie & timeline charts plus a
text dump of the numbers behind them into output/report/.

    python3 analysis.py

Full CLI (stats, activity, search, ...) lives in the package:

    python3 -m analysis stats
    python3 -m analysis activity --by month
    python3 -m analysis search "hello"
"""

from analysis import report

if __name__ == "__main__":
    report()
