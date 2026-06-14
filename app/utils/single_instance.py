"""单实例检测，防止重复启动."""

from PySide6.QtCore import QSharedMemory


def is_already_running(app_key: str = "PomodoroBall_Instance") -> bool:
    """检查是否已有实例在运行."""
    shared_mem = QSharedMemory(app_key)
    if shared_mem.attach():
        return True
    shared_mem.create(1)
    return False
