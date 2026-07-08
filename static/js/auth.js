/**
 * 用户认证前端模块 — auth.js
 *
 * 功能:
 *   - 登录/注册模态框管理
 *   - localStorage 登录状态持久化
 *   - 导航栏状态自动更新
 *   - 管理员权限检查
 */

// ─── 认证状态管理 ────────────────────────────────────────────────
var AuthState = {
    _key: 'sc_search_user',

    /** 获取当前登录用户信息 */
    getUser: function () {
        try {
            var raw = localStorage.getItem(this._key);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    },

    /** 保存用户信息到 localStorage */
    setUser: function (user) {
        localStorage.setItem(this._key, JSON.stringify(user));
    },

    /** 清除登录状态 */
    clearUser: function () {
        localStorage.removeItem(this._key);
    },

    /** 是否已登录 */
    isLoggedIn: function () {
        return this.getUser() !== null;
    },

    /** 是否为管理员 */
    isAdmin: function () {
        var user = this.getUser();
        return user && user.role === 'admin';
    },

    /** 获取当前用户名 */
    getUsername: function () {
        var user = this.getUser();
        return user ? user.username : '';
    },

    /** 获取用于 API 请求的认证头 */
    getAuthHeaders: function () {
        var user = this.getUser();
        if (!user) return {};
        return { 'Authorization': 'Bearer ' + user.username };
    },
};


// ─── 认证 UI 模块 ────────────────────────────────────────────────
var AuthUI = {
    /** 页面初始化：根据登录状态更新导航栏 */
    init: function () {
        this.updateNavBar();
        this.bindEvents();
    },

    /** 绑定模态框事件 */
    bindEvents: function () {
        var self = this;

        // 登录表单提交
        var loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', function () {
                self.handleLogin();
            });
        }

        // 注册表单提交
        var registerForm = document.getElementById('register-form');
        if (registerForm) {
            registerForm.addEventListener('submit', function () {
                self.handleRegister();
            });
        }

        // 点击模态框背景关闭
        document.querySelectorAll('.modal-overlay').forEach(function (overlay) {
            overlay.addEventListener('click', function (e) {
                if (e.target === overlay) {
                    self.closeModals();
                }
            });
        });

        // ESC 关闭模态框
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                self.closeModals();
            }
        });
    },

    /** 更新导航栏显示 */
    updateNavBar: function () {
        var guestEl = document.getElementById('auth-guest');
        var userEl = document.getElementById('auth-user');
        var usernameEl = document.getElementById('auth-username');
        var roleBadge = document.getElementById('auth-role-badge');

        if (!guestEl || !userEl) return;

        if (AuthState.isLoggedIn()) {
            guestEl.classList.add('hidden');
            userEl.classList.remove('hidden');
            if (usernameEl) usernameEl.textContent = AuthState.getUsername();
            if (roleBadge) {
                roleBadge.textContent = AuthState.isAdmin() ? '管理员' : '用户';
                roleBadge.className = 'user-role-badge ' + (AuthState.isAdmin() ? 'role-admin' : 'role-user');
            }
        } else {
            guestEl.classList.remove('hidden');
            userEl.classList.add('hidden');
        }
    },

    /** 显示登录模态框 */
    showLoginModal: function () {
        this.closeModals();
        var modal = document.getElementById('login-modal');
        if (modal) {
            modal.classList.remove('hidden');
            document.getElementById('login-username').focus();
        }
        this.clearFormErrors();
    },

    /** 显示注册模态框 */
    showRegisterModal: function () {
        this.closeModals();
        var modal = document.getElementById('register-modal');
        if (modal) {
            modal.classList.remove('hidden');
            document.getElementById('register-username').focus();
        }
        this.clearFormErrors();
    },

    /** 关闭所有模态框 */
    closeModals: function () {
        document.querySelectorAll('.modal-overlay').forEach(function (m) {
            m.classList.add('hidden');
        });
        this.clearFormErrors();
    },

    /** 清除表单错误提示 */
    clearFormErrors: function () {
        var errors = document.querySelectorAll('.form-error');
        errors.forEach(function (e) { e.classList.add('hidden'); e.textContent = ''; });
        // 清空表单
        var loginForm = document.getElementById('login-form');
        var registerForm = document.getElementById('register-form');
        if (loginForm) loginForm.reset();
        if (registerForm) registerForm.reset();
        // 重置按钮状态
        this.setButtonLoading('login-submit-btn', false);
        this.setButtonLoading('register-submit-btn', false);
    },

    /** 处理登录 */
    handleLogin: function () {
        var username = document.getElementById('login-username').value.trim();
        var password = document.getElementById('login-password').value.trim();
        var errorEl = document.getElementById('login-error');

        if (!username || !password) {
            this.showError(errorEl, '用户名和密码不能为空');
            return;
        }

        this.setButtonLoading('login-submit-btn', true);

        fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: username, password: password }),
        })
        .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
        .then(function (result) {
            if (!result.ok || result.data.status === 'error') {
                AuthUI.showError(errorEl, result.data.message || '登录失败');
                AuthUI.setButtonLoading('login-submit-btn', false);
                return;
            }
            // 登录成功，保存状态
            AuthState.setUser(result.data.user);
            AuthUI.updateNavBar();
            AuthUI.closeModals();
            AuthUI.showToast('登录成功！欢迎 ' + result.data.user.username, 'success');

            // 通知其他模块登录状态已变化
            if (typeof onAuthStateChanged === 'function') {
                onAuthStateChanged(result.data.user);
            }
        })
        .catch(function (err) {
            AuthUI.showError(errorEl, '网络请求失败: ' + err.message);
            AuthUI.setButtonLoading('login-submit-btn', false);
        });
    },

    /** 处理注册 */
    handleRegister: function () {
        var username = document.getElementById('register-username').value.trim();
        var password = document.getElementById('register-password').value.trim();
        var passwordConfirm = document.getElementById('register-password-confirm').value.trim();
        var errorEl = document.getElementById('register-error');

        if (!username || !password) {
            this.showError(errorEl, '用户名和密码不能为空');
            return;
        }
        if (username.length < 3) {
            this.showError(errorEl, '用户名至少需要 3 个字符');
            return;
        }
        if (password.length < 6) {
            this.showError(errorEl, '密码至少需要 6 个字符');
            return;
        }
        if (password !== passwordConfirm) {
            this.showError(errorEl, '两次输入的密码不一致');
            return;
        }

        this.setButtonLoading('register-submit-btn', true);

        fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: username, password: password }),
        })
        .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
        .then(function (result) {
            if (!result.ok || result.data.status === 'error') {
                AuthUI.showError(errorEl, result.data.message || '注册失败');
                AuthUI.setButtonLoading('register-submit-btn', false);
                return;
            }
            // 注册成功，切换到登录
            AuthUI.showToast('注册成功！请登录', 'success');
            AuthUI.setButtonLoading('register-submit-btn', false);
            AuthUI.showLoginModal();
        })
        .catch(function (err) {
            AuthUI.showError(errorEl, '网络请求失败: ' + err.message);
            AuthUI.setButtonLoading('register-submit-btn', false);
        });
    },

    /** 退出登录 */
    logout: function () {
        AuthState.clearUser();
        this.updateNavBar();
        this.showToast('已退出登录', 'info');

        // 通知其他模块
        if (typeof onAuthStateChanged === 'function') {
            onAuthStateChanged(null);
        }
    },

    /** 显示表单内联错误 */
    showError: function (el, message) {
        if (!el) return;
        el.textContent = message;
        el.classList.remove('hidden');
    },

    /** 设置按钮加载状态 */
    setButtonLoading: function (btnId, isLoading) {
        var btn = document.getElementById(btnId);
        if (!btn) return;
        var btnText = btn.querySelector('.btn-text');
        var btnLoading = btn.querySelector('.btn-loading');
        if (isLoading) {
            btn.disabled = true;
            if (btnText) btnText.classList.add('hidden');
            if (btnLoading) btnLoading.classList.remove('hidden');
        } else {
            btn.disabled = false;
            if (btnText) btnText.classList.remove('hidden');
            if (btnLoading) btnLoading.classList.add('hidden');
        }
    },

    /** 显示 Toast 消息 */
    showToast: function (message, type) {
        type = type || 'info';
        var container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        var toast = document.createElement('div');
        var iconMap = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
        toast.className = 'toast toast-' + type;
        toast.innerHTML = '<span class="toast-icon">' + (iconMap[type] || '') + '</span>' +
            '<span class="toast-msg">' + escapeHtml(message) + '</span>' +
            '<button class="toast-close" onclick="this.parentElement.remove()">✕</button>';
        container.appendChild(toast);

        setTimeout(function () {
            if (toast.parentElement) toast.remove();
        }, 4000);
    },
};


// ─── 认证状态变化回调（由 app.js 实现） ──────────────────────────
function onAuthStateChanged(user) {
    // 页面级模块可覆盖此函数以响应登录/退出事件
}


// ─── 页面加载时初始化 ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    AuthUI.init();
});


// ─── 工具函数 ────────────────────────────────────────────────────
function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}
