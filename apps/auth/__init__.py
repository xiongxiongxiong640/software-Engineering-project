"""
apps.auth — 用户认证模块

功能:
    - 用户注册（bcrypt 密码哈希）
    - 用户登录（session 管理）
    - 角色管理（admin / user）
    - JSON 文件持久化存储

数据持久化: data/users.json

默认管理员: admin / admin123
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import bcrypt

# 数据文件路径
_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_USERS_FILE = _DATA_DIR / "users.json"


def _ensure_data_dir():
    """确保数据目录存在"""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_users() -> dict:
    """加载用户数据库"""
    _ensure_data_dir()
    if _USERS_FILE.exists():
        with open(_USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_users(users: dict):
    """保存用户数据库"""
    _ensure_data_dir()
    with open(_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


# ======================================================================
#  用户注册 / 登录 / 管理
# ======================================================================

def register_user(
    username: str,
    password: str,
    role: str = "user",
) -> Tuple[bool, str]:
    """注册新用户

    Args:
        username: 用户名，长度 >= 3
        password: 密码，长度 >= 6
        role: 角色，"admin" 或 "user"

    Returns:
        (success, message)
    """
    if len(username) < 3:
        return False, "用户名至少需要 3 个字符"
    if len(password) < 6:
        return False, "密码至少需要 6 个字符"

    users = _load_users()
    if username in users:
        return False, f"用户名 '{username}' 已存在"

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    users[username] = {
        "username": username,
        "password": hashed.decode("utf-8"),
        "role": role,
        "created_at": datetime.now().isoformat(),
    }
    _save_users(users)
    return True, f"用户 '{username}' 注册成功"


def login_user(username: str, password: str) -> Tuple[bool, str, Optional[dict]]:
    """用户登录验证

    Returns:
        (success, message, user_info | None)
    """
    users = _load_users()
    if username not in users:
        return False, "用户名或密码错误", None

    user = users[username]
    stored_hash = user["password"].encode("utf-8")

    if not bcrypt.checkpw(password.encode("utf-8"), stored_hash):
        return False, "用户名或密码错误", None

    return True, "登录成功", {
        "username": user["username"],
        "role": user["role"],
        "created_at": user.get("created_at", ""),
    }


def get_all_users() -> List[dict]:
    """获取所有用户列表（管理员使用）"""
    users = _load_users()
    return [
        {
            "username": u["username"],
            "role": u["role"],
            "created_at": u.get("created_at", ""),
        }
        for u in users.values()
    ]


def update_user_role(username: str, new_role: str) -> Tuple[bool, str]:
    """更新用户角色"""
    users = _load_users()
    if username not in users:
        return False, f"用户 '{username}' 不存在"
    users[username]["role"] = new_role
    _save_users(users)
    return True, f"用户 '{username}' 角色已更新为 {new_role}"


def delete_user(username: str) -> Tuple[bool, str]:
    """删除用户（不能删除 admin）"""
    if username == "admin":
        return False, "不能删除 admin 账号"
    users = _load_users()
    if username not in users:
        return False, f"用户 '{username}' 不存在"
    del users[username]
    _save_users(users)
    return True, f"用户 '{username}' 已删除"


def get_user_stats(username: str) -> dict:
    """获取用户统计信息"""
    users = _load_users()
    user = users.get(username, {})

    # 统计数据集
    from apps.data_processor import _load_ds_db as _load_ds
    ds_db = _load_ds()
    ds_count = sum(1 for m in ds_db.values() if m.get("username") == username)

    # 统计索引
    from apps.search_engine.index_builder import _load_index_db
    idx_db = _load_index_db()
    idx_count = sum(1 for m in idx_db.values() if m.get("username") == username)

    return {
        "username": username,
        "role": user.get("role", "user"),
        "created_at": user.get("created_at", ""),
        "dataset_count": ds_count,
        "index_count": idx_count,
    }


# ======================================================================
#  初始化
# ======================================================================

def init_admin():
    """初始化默认管理员账号"""
    users = _load_users()
    if "admin" not in users:
        register_user("admin", "admin123", role="admin")
