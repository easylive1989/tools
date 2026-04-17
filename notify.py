#!/usr/bin/env python3
# Compatibility shim — forwards to common/notify.py
import sys, os, runpy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
runpy.run_module("common.notify", run_name="__main__", alter_sys=True)
