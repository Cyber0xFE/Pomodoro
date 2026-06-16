"""单实例检测，防止重复启动."""

from PySide6.QtCore import QSharedMemory


def acquire_app_lock(app_key: str = "PomodoroBall_Instance") -> QSharedMemory | None:
    """尝试获取应用单实例锁。

    返回 QSharedMemory 对象表示成功（调用方须保活引用），
    返回 None 表示已有实例在运行。
    """
    shared_mem = QSharedMemory(app_key)
    if shared_mem.attach():
        return None
    if not shared_mem.create(1):
        return None
    return shared_mem
