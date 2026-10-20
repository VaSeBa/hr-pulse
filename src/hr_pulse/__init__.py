from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("hr-pulse")
except PackageNotFoundError:
    # Нет метаданных: код запущен без установки или из exe
    __version__ = "0.0.0+unknown"


def main() -> None:
    """Точка входа приложения: команда hr-pulse вызывает эту функцию."""
    print(f"HR Pulse v{__version__}")
