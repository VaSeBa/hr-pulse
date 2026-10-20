from importlib.metadata import PackageNotFoundError, version

v = version("hr_pulse")

def main() -> None:
    print(f"HR Pulse {v}")
