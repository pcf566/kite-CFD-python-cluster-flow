from pathlib import Path


def round_angle(x, ndigits=4):
    """角度比较统一按四位小数处理"""
    return round(float(x), ndigits)


def format_num(x, ndigits=4):
    """
    数值转字符串：
    1. 先四舍五入到 ndigits 位小数
    2. 再去掉末尾多余的 0 和 .
    """
    x = round(float(x), ndigits)
    s = f"{x:.{ndigits}f}".rstrip("0").rstrip(".")
    if s == "-0":
        s = "0"
    return s


class Config:
    def __init__(self):
        # 基础路径（局限于 pyfluent 代码文件夹内）
        self.base_dir = Path(__file__).parent

        # 创建文件夹结构
        self.geometry_dir = self.base_dir / "geometry"
        self.mesh_dir = self.base_dir / "mesh"
        self.solve_dir = self.base_dir / "solve"
        self.result_dir = self.base_dir / "result"

        # 创建文件夹
        for dir_path in [self.geometry_dir, self.mesh_dir, self.solve_dir, self.result_dir]:
            dir_path.mkdir(exist_ok=True)
            print(f"创建文件夹: {dir_path}")
            print(f"文件夹是否存在: {dir_path.exists()}")

        # 保持 output_dir 兼容旧代码
        self.output_dir = self.solve_dir

        # SpaceClaim 配置（如果需要）
        self.spaceclaim_exe = r"C:\Program Files\ANSYS Inc242\v242\scdm\SpaceClaim.exe"
        self.rotate_script = self.base_dir / "rotate_kite.py"

        # 网格生成配置
        self.mesh_settings = {
            "boi_size": 175,                 # 影响体尺寸
            "edge_size": 3,                  # 边缘尺寸
            "rib_size": 18,                  # 肋条尺寸
            "face_size": 56,                 # 表面尺寸
            "surface_max_size": 1750,        # 表面最大尺寸
            "surface_min_size": 3,           # 表面最小尺寸
            "volume_max_cell_length": 1750,  # 体网格最大单元长度
            "boi_growth_rate": 1.15,         # 影响体生长率
            "n_boundary_layers": 20,         # 边界层数量
            "processor_count": 14,           # 处理器数量
            "precision": "double" ,           # 精度
            "ui_mode": "gui",
        }

        # 求解器配置
        self.solver_settings = {
            "model": "transition-sst",      # 湍流模型
            "time_type": "steady",          # 时间类型
            "flow_scheme": "SIMPLE",        # 流场求解方案
            "inlet_velocity": 1.0,          # 入口速度
            "viscosity": 1.7894e-5,         # 空气粘性系数
            "processor_count": 14,          # 处理器数量
            "precision": "double",          # 精度
            "ui_mode": "gui",               # UI模式
            "time_step": 0.01,              # 时间步长
            "number_of_time_steps": 250,    # 时间步数
            "number_of_iterations": 500,    # 迭代步数（稳态）
            "max_iter_per_time_step": 50    # 每个时间步最多内迭代次数
        }

        # 后处理配置
        self.post_processing_settings = {
            "results_file": self.base_dir / "results.xlsx",
            "force_moment_history_file": "{name}_force_moment_history.out",
            "pressure_eps": "xz_pressure.eps",
            "pathline_png": "xz_pathline_pressure.png",
            "resolution": (1800, 1200)
        }

    def _extract_angles_from_filename(self, file_path):
        """
        从文件名中提取 alpha、beta
        例如：
        KITE_3.081078467_0.scdoc
        -> alpha=3.081078467, beta=0
        """
        stem = file_path.stem  # 去掉后缀
        parts = stem.split("_")

        if len(parts) < 3:
            raise ValueError(f"文件名格式不正确，无法提取角度: {file_path.name}")

        alpha_str = parts[-2]
        beta_str = parts[-1]

        return float(alpha_str), float(beta_str)

    def get_geometry_file(self, alpha, beta):
        """
        获取几何文件路径：
        不要求文件名和 Excel 数值完全一致，
        只要求 alpha、beta 在四舍五入到小数点后四位后相等。
        """
        alpha_target = round_angle(alpha, 4)
        beta_target = round_angle(beta, 4)

        scdoc_files = list(self.geometry_dir.glob("*.scdoc"))

        if not scdoc_files:
            raise FileNotFoundError(f"geometry 文件夹下未找到任何 .scdoc 文件: {self.geometry_dir}")

        matched_files = []

        for file_path in scdoc_files:
            try:
                file_alpha, file_beta = self._extract_angles_from_filename(file_path)
            except Exception:
                continue

            if round_angle(file_alpha, 4) == alpha_target and round_angle(file_beta, 4) == beta_target:
                matched_files.append(file_path)

        if len(matched_files) == 1:
            return matched_files[0]

        if len(matched_files) > 1:
            print("警告: 找到多个匹配的几何文件，将默认使用第一个：")
            for f in matched_files:
                print(f"  - {f.name}")
            return matched_files[0]

        raise FileNotFoundError(
            f"未找到匹配的几何文件: alpha={alpha}, beta={beta}\n"
            f"按四位小数比较后为: alpha={alpha_target}, beta={beta_target}\n"
            f"请检查 geometry 文件夹中的 .scdoc 文件名。"
        )

    def get_mesh_file(self, alpha, beta):
        """获取网格文件路径（用于命名，不用于反查文件）"""
        name = f"KITE_{format_num(alpha)}_{format_num(beta)}"
        return self.mesh_dir / f"{name}mesh.cas.h5"

    def get_case_file(self, alpha, beta):
        """获取求解文件路径"""
        name = f"KITE_{format_num(alpha)}_{format_num(beta)}"
        return self.solve_dir / f"{name}solve.cas.h5"

    def get_data_file(self, alpha, beta):
        """获取数据文件路径"""
        name = f"KITE_{format_num(alpha)}_{format_num(beta)}"
        return self.solve_dir / f"{name}solve.dat.h5"

    def get_force_moment_history_file(self, alpha, beta):
        """获取力和力矩历史文件路径"""
        name = f"KITE_{format_num(alpha)}_{format_num(beta)}"
        filename = self.post_processing_settings["force_moment_history_file"].format(name=name)
        return self.result_dir / filename