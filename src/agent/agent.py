"""`ruai agent`: agge, the multi-agent CLI, written in rupy (run by CPython too).

    python3 agent.py <op> ...           (PYTHONPATH=python for rupy.json / rupy.http)
    rupy run src/agent/agent.py <op> ...
"""
import sys

from cli import main

main(sys.argv[1:])
