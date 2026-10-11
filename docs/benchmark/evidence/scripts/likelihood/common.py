"""Shared set-up of the likelihood prototype (research copy; nothing here is in the repository)."""
import os, sys
ROOT = "/tmp/research/likelihood"
sys.path.insert(0, f"{ROOT}/repo/src"); sys.path.insert(0, f"{ROOT}/repo")
sys.path.insert(0, f"{ROOT}/scripts")
REG = f"{ROOT}/research_registry.yaml"
from ralmon.attribution.extract import DeviceCapabilities, DeviceProfile

def profile(auth: bool, diagnostics: bool, witness_robot: bool = True) -> DeviceProfile:
    """Run profile as in /tmp/research/pairs/scripts/probe_pairs.py; `diagnostics` switches the driver capability."""
    cuff = DeviceCapabilities(status_reports=True, supervised=True, diagnostics=diagnostics, seq=True, two_clocks=True,
                              authenticates=False, error_codes=True, deadline_ms=12 * 3600 * 1000)
    disp = DeviceCapabilities(status_reports=True, supervised=True, diagnostics=diagnostics, seq=True, two_clocks=True,
                              authenticates=auth)
    robot = DeviceCapabilities(status_reports=True, supervised=True, battery=True)
    return DeviceProfile({"cuff": cuff, "dispenser": disp, "robot": robot})

def load():
    from ralmon.spec import load_registry, load_templates
    from ralmon.monitor import MonitorConfig
    reg = load_registry(REG, step_ms=60000, allow_fixture_only=True)
    tpl = load_templates(registry=reg)
    cfg = MonitorConfig(60000, 0, False, None, "likely", reg.version())
    return reg, tpl, cfg
