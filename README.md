# kite-cfd

一个用于风筝几何批量生成、Fluent 网格生成，以及稳态/瞬态批量求解的自动化项目。

项目分成两部分：

- `spaceclaim+pyfluent`：本地前处理，负责 `SpaceClaim -> .scdoc 几何 -> PyFluent Meshing -> mesh.cas.h5`
- `clurm`：超算批处理，负责 `mesh -> 稳态+瞬态` 和 `已有稳态结果 -> 继续瞬态`

## 项目概览

这个仓库把一个典型 CFD 工作流拆成了三个阶段：

1. 基于基础几何 `KITE.scdoc`，按攻角/侧滑角批量生成旋转后的 `.scdoc` 几何文件。
2. 基于 `.scdoc` 几何，使用 `ansys.fluent.core` 自动完成 Fluent Meshing，并输出网格质量汇总。
3. 在超算上通过 Slurm array 批量提交 Fluent 求解任务：
   - `clurm/1`：从网格开始，先稳态再瞬态连续求解
   - `clurm/2`：读取已有稳态 `case+data`，继续进行瞬态计算

## 目录结构

```text
kite-cfd/
├─ spaceclaim+pyfluent/
│  ├─ KITE.scdoc                  # 基础几何
│  ├─ rotate_kite.py              # SpaceClaim 旋转脚本
│  ├─ main_spaceclaim.py          # 批量生成 .scdoc 几何
│  ├─ mesh_generator.py           # PyFluent Meshing 工作流
│  ├─ main_mesh.py                # 批量生成网格并汇总质量
│  ├─ config.py                   # 本地前处理配置
│  ├─ geometry/                   # 旋转后几何输出目录
│  └─ mesh/                       # 网格、日志、汇总表
│
└─ clurm/
   ├─ 1/
   │  ├─ main_solve.py            # 从网格开始：稳态 + 瞬态
   │  ├─ solver.py                # 生成 journal 并调用 Fluent
   │  ├─ config.py                # 求解配置
   │  ├─ job_solve_array.sh       # Slurm array 提交脚本
   │  └─ solve/solve_parameters.xlsx
   │
   └─ 2/
      ├─ main_unsteady.py         # 从已有稳态结果继续瞬态
      ├─ unsteady_solver.py       # 生成 journal 并调用 Fluent
      ├─ config.py                # 求解配置
      ├─ job_unsteady_array.sh    # Slurm array 提交脚本
      └─ unsteady.xlsx
```

## 工作流

### 1. SpaceClaim 批量生成几何

入口脚本：`spaceclaim+pyfluent/main_spaceclaim.py`

流程：

1. 读取 `geometry/geometry.xlsx`
2. 获取每一行的 `alpha` 和 `beta`
3. 调用 `rotate_kite.py`
4. 以 `KITE_{alpha}_{beta}.scdoc` 命名保存到 `geometry/`

`rotate_kite.py` 的核心逻辑：

- 打开基础几何 `KITE.scdoc`
- 获取命名选择 `inlet`、`outlet`、`symmetric`
- 分别按 `alpha`、`beta` 旋转
- 保存为新的 `.scdoc`

说明：

- 代码会按四位小数匹配几何文件名，避免 Excel 数值和文件名的小数位差异导致找不到文件。
- 当前仓库快照中没有包含 `geometry/geometry.xlsx`，如果要运行这一步，需要自行补充该表。

### 2. PyFluent 自动生成网格

入口脚本：`spaceclaim+pyfluent/main_mesh.py`

输入表：`spaceclaim+pyfluent/mesh/mesh_parameters.xlsx`

表格主要列包括：

- `number`
- `alpha`
- `beta`
- `rib_size`
- `boi_size`
- `edge_size`
- `face_size`
- `surface_max_size`
- `surface_min_size`
- `volume_max_cell_length`
- `n_boundary_layers`
- `boi_growth_rate`

流程：

1. 根据 `alpha`、`beta` 找到匹配的 `.scdoc`
2. 启动 Fluent Meshing
3. 使用 Watertight Geometry 工作流导入几何
4. 对 `boi`、`kite_edges`、`kite_ribs`、`kite_face` 设置局部网格尺寸
5. 生成表面网格、边界层和 polyhedra 体网格
6. 输出 `mesh{number}.cas.h5`
7. 解析网格质量日志，生成汇总：
   - `mesh/mesh_summary.xlsx`
   - `mesh/mesh_summary.csv`

网格质量汇总会记录的信息包括：

- 单元数
- 正交质量
- 长宽比
- Cell Squish
- 负体积计数
- transcript 时间
- 质量等级和备注

## 超算求解

### 3. `clurm/1`：从网格开始做稳态 + 瞬态

入口脚本：`clurm/1/main_solve.py`

输入表：`clurm/1/solve/solve_parameters.xlsx`

默认流程由 `solver.py` 自动生成 Fluent journal：

1. 读取网格文件
2. 打开 `transition-sst`
3. 设置空气材料参数、入口速度、湍流参数、压力速度耦合
4. 创建力/力矩 report definitions：
   - `fx`
   - `fy`
   - `fz`
   - `momx`
   - `momy`
   - `momz`
5. 初始化
6. 执行稳态迭代
7. 切换为 `unsteady-1st-order`
8. 执行 `dual-time-iterate`
9. 保存最终 `solveN.cas.h5` 和 `solveN.dat.h5`

输出目录通常包括：

- `solve/`：最终 case/data
- `result/`：监控输出、控制台日志
- `journal/`：自动生成的 `.jou`
- `transcript/`：Fluent transcript

`solve_parameters.xlsx` 里常见可配置列包括：

- `mesh` 或 `mesh_file`
- `steady_iterations`
- `time_step`
- `number_of_time_steps`
- `max_iter_per_time_step`
- `viscosity`
- `inlet_velocity`
- `processor_count`
- `precision`
- `dimension`

### 4. `clurm/2`：基于已有稳态结果继续做瞬态

入口脚本：`clurm/2/main_unsteady.py`

输入表：`clurm/2/unsteady.xlsx`

这一步不再重新读 mesh，而是直接读取已有稳态结果：

- `solveN.cas.h5`
- `solveN.dat.h5`

流程：

1. 根据 `unsteady.xlsx` 中的 `case` 找到对应稳态结果
2. 读入已有 `case+data`
3. 切换到非稳态
4. 删除旧的 report-file / report-plot
5. 识别已有 report definitions，重新建立新的 monitor 文件
6. 执行 `dual-time-iterate`
7. 保存续算后的 `case+data`

说明：

- 如果 `unsteady.xlsx` 提供了 `steady_solve_dir`，脚本会从指定目录读取原始稳态结果。
- 如果没有，则默认从当前 `solve/` 目录读取。
- 当前仓库里的 `unsteady.xlsx` 更像模板或占位内容，正式运行前建议先检查并填写有效工况。

## 依赖环境

### 本地前处理

- ANSYS SpaceClaim
- PyFluent，对应 Python 包：
  - `ansys.fluent.core`
- `pandas`
- `openpyxl`

`spaceclaim+pyfluent/config.py` 中默认配置了本机 SpaceClaim 路径：

```python
self.spaceclaim_exe = r"C:\Program Files\ANSYS Inc242\v242\scdm\SpaceClaim.exe"
```

如果你的安装路径不同，需要先修改这里。

### 超算求解

- Linux + Slurm
- Fluent 可执行文件
- Python
- `openpyxl`

`clurm/1/config.py` 和 `clurm/2/config.py` 中默认 Fluent 路径为：

```bash
/apps/soft/ansys/2022R1/ansys_inc/v221/fluent/bin/fluent
```

提交脚本中默认使用：

- 4 个节点
- 每节点 56 tasks
- 总并行核数 224

实际使用前请按所在超算环境修改：

- 分区
- 节点数
- `ntasks-per-node`
- 工作目录
- 模块加载命令

## 运行方法

### 本地：批量生成几何

在 `spaceclaim+pyfluent/` 目录下运行：

```bash
python main_spaceclaim.py
```

### 本地：批量生成网格

在 `spaceclaim+pyfluent/` 目录下运行：

```bash
python main_mesh.py
```

### 超算：从网格开始做稳态 + 瞬态

在 `clurm/1/` 目录下运行：

```bash
python main_solve.py --dry-run
python main_solve.py
```

Slurm array 提交：

```bash
sbatch job_solve_array.sh
```

### 超算：基于已有稳态结果继续做瞬态

在 `clurm/2/` 目录下运行：

```bash
python main_unsteady.py --dry-run
python main_unsteady.py
```

Slurm array 提交：

```bash
sbatch job_unsteady_array.sh
```

## 命令行说明

两个求解入口都支持类似参数：

- `--dry-run`
  只生成 journal，不真正启动 Fluent
- `--processors`
  覆盖默认并行核数
- `--case-index`
  只运行第几个有效工况，适合 array task
- `--print-case-count`
  只打印有效工况总数

其中 `main_solve.py` 还支持：

- `--excel`
- `--sheet`
- `--fluent-path`
- `--dimension`
- `--precision`

`main_unsteady.py` 同样支持相应覆盖参数。

## 文件命名约定

- 几何文件：`KITE_{alpha}_{beta}.scdoc`
- 网格文件：`mesh{number}.cas.h5`
- 连续求解结果：`solve{number}.cas.h5`、`solve{number}.dat.h5`
- 续算结果：通常为 `solve{number}_unsteady.cas.h5`

## 已有样例文件

仓库当前已经包含一些结果文件，方便查看格式：

- `spaceclaim+pyfluent/geometry/KITE_20_0.scdoc`
- `spaceclaim+pyfluent/mesh/mesh173.cas.h5`
- `spaceclaim+pyfluent/mesh/mesh173_meshinfo.log`
- `spaceclaim+pyfluent/mesh/mesh_summary.xlsx`
- `spaceclaim+pyfluent/mesh/mesh_summary.csv`

如果要公开上传到 GitHub，建议先确认这些大文件是否需要保留，必要时可以配合 `.gitignore` 或 Git LFS 管理。

## 注意事项

- `spaceclaim+pyfluent` 是 Windows 本地前处理工作流。
- `clurm` 是 Linux 超算工作流，默认依赖 Slurm。
- 代码中对几何文件名和角度匹配做了四位小数容差处理。
- 网格阶段依赖命名选择和标签名称，例如：
  - `inlet`
  - `outlet`
  - `symmetric`
  - `kite_edges`
  - `kite_ribs`
  - `kite_face`
- 如果几何命名选择或标签和脚本不一致，需要同步修改脚本。

## 后续可改进项

- 补充 `.gitignore`
- 提供 `geometry.xlsx` 模板
- 提供 `solve_parameters.xlsx` 和 `unsteady.xlsx` 的最小示例
- 增加流程图和结果示意图
- 增加环境安装说明和版本锁定

## License

当前仓库未包含许可证文件。若准备公开发布，建议补充 `LICENSE`。
