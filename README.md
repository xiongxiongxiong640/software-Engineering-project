# 单细胞 ANN 检索系统

南开大学 2025-2026 学年《软件工程》第 19 小组课程作业

本仓库对应一个基于 Flask 的 Web 应用，用于在单细胞数据上完成近似最近邻（ANN）检索、条件筛选、结果可视化与基础性能评估。

## 1. 运行环境

- Python 3.10 及以上
- Windows / macOS / Linux
- 建议使用虚拟环境

项目主要依赖：

- Flask
- scanpy / anndata
- numpy / pandas / h5py
- faiss-cpu
- bcrypt

## 2. 项目结构

```text
software-Engineering-project/
├─ apps/
│  ├─ api/               # 后端 REST API
│  ├─ auth/              # 注册、登录、权限管理
│  ├─ data_processor/    # .h5ad 数据读取与查询
│  ├─ home/              # 前端页面与前端接口
│  ├─ search_engine/     # ANN 索引构建与检索
│  └─ services/          # 全局状态管理
├─ data/
│  ├─ liver.h5ad         # 示例单细胞数据集
│  └─ users.json         # 用户信息存储
├─ static/               # 前端静态资源
├─ templates/            # 前端页面模板
├─ tests/                # 测试脚本
├─ requirements.txt
└─ run.py
```

## 3. 安装步骤

### 3.1 克隆项目

```bash
git clone <你的仓库地址>
cd software-Engineering-project
```

### 3.2 创建并激活虚拟环境

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3.3 安装依赖

```bash
pip install -r requirements.txt
```

如果 `faiss-cpu` 安装较慢，可先升级 `pip`：

```bash
python -m pip install --upgrade pip
```

## 4. 数据准备

项目默认读取 `data/liver.h5ad`。

当前仓库已经包含该示例数据，因此一般情况下无需额外下载。若替换为自己的数据，请确保：

- 文件格式为 `.h5ad`
- 文件中包含 `obs.cell_type`
- 文件中包含 `obs.disease`
- 文件中包含 `obs.AgeGroup`
- 文件中包含 `obsm["X_pca"]`

如果缺少上述字段，系统启动后将无法正常完成检索。

## 5. 启动方式

在项目根目录执行：

```bash
python run.py
```

默认启动参数：

- Host：`0.0.0.0`
- Port：`5000`
- 默认 `DEBUG=True`

浏览器访问：

```text
http://127.0.0.1:5000
```

## 6. 使用说明

系统启动后会自动完成以下初始化流程：

1. 读取 `data/liver.h5ad`
2. 校验数据字段
3. 提取 PCA 向量
4. 构建 ANN 检索索引
5. 加载前端页面

前端可完成的主要操作：

- 输入细胞 ID 进行 Top-K 相似细胞检索
- 按细胞类型进行条件筛选
- 在 PCA 散点图中点击细胞直接发起查询
- 查看查询耗时与相似细胞结果
- 进行向量检索
- 查看索引状态与性能评估结果

默认管理员账号：

- 用户名：`admin`
- 密码：`admin123`

## 7. 常用接口

部分常用接口如下：

- `GET /api/status`：查看系统状态
- `POST /api/search`：按细胞 ID 检索相似细胞
- `POST /api/search/by-vector`：按向量检索
- `GET /api/index/status`：查看索引状态
- `POST /api/index/rebuild`：重建索引
- `GET /api/benchmark`：性能评估
- `GET /api/datasets`：查看已注册数据集

检索请求示例：

```json
{
  "query_cell_id": "AAACCTGAGCAGGTCA-1_2",
  "top_k": 10,
  "filter_cell_type": "Hepatocyte"
}
```

## 8. 测试方法

可直接运行仓库自带冒烟测试：

```bash
python tests/test_data_processor.py
```

该测试会检查：

- 数据读取是否成功
- 字段是否完整
- PCA 向量提取是否正常
- 按细胞 ID / 行号查询是否正常
- 数据集管理接口是否可用

## 9. 常见问题

### 9.1 启动时报“未找到核心单细胞文件”

请确认 `data/liver.h5ad` 存在，且启动命令是在项目根目录执行。

### 9.2 `faiss-cpu` 安装失败

建议先确认 Python 版本兼容，再升级 `pip` 后重试；若仍失败，可在相同环境下重新创建虚拟环境后安装。

### 9.3 页面打开但没有检索结果

请先确认：

- 后端已成功启动
- 终端中没有数据加载报错
- 输入的细胞 ID 确实存在于当前数据集中

## 10. 提交说明

本 README 作为仓库内的安装运行说明文件，供课程结项提交时配套使用。完整的软件开发文档、演示视频、贡献度说明等内容应按课程要求另外整理并提交。










