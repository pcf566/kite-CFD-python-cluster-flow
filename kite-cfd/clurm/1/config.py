from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List


@dataclass
class Config:
    """fluent3：先稳态再非稳态的连续求解配置"""

    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent)

    # Fluent 启动
    fluent_path: str = "/apps/soft/ansys/2022R1/ansys_inc/v221/fluent/bin/fluent"
    dimension: str = "3d"
    precision: str = "dp"
    processor_count: int | None = None
    headless: bool = True

    # 在 slurm 环境中优先使用 -slurm
    use_slurm_launcher: bool = True

    # 目录
    # fluent3 自己的工作目录
    solve_dir_name: str = "solve"
    result_dir_name: str = "result"
    journal_dir_name: str = "journal"
    transcript_dir_name: str = "transcript"

    # 网格目录：从 ../fluent/mesh 读取
    upstream_fluent_dir_name: str = "fluent"
    mesh_dir_name: str = "mesh"

    # 输入表格
    solve_table_name: str = "solve_parameters.xlsx"
    solve_sheet_name: str | None = None

    # 默认设置：先稳态后非稳态
    default_case_settings: Dict[str, Any] = field(
        default_factory=lambda: {
            "model": "transition-sst",

            # 基本物性和边界
            "inlet_velocity": 10.0,
            "viscosity": 1.813e-5,
            "pv_coupling": 24,

            # 稳态默认
            "steady_iterations": 200,

            # 非稳态默认
            "time_step": 0.005,
            "number_of_time_steps": 5000,
            "max_iter_per_time_step": 10,

            # 输出
            "write_instantaneous_values": True,
            "output_case_data": True,

            # 初始化
            "initialize_method": "hyb-initialization",

            # 维度精度
            "dimension": "3d",
            "precision": "dp",
        }
    )

    # 力和力矩监控面
    wall_zones: List[str] = field(
        default_factory=lambda: ["kite_edges", "kite_face", "kite_ribs"]
    )
    moment_center: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    # 入口条件
    inlet_name: str = "inlet"
    inlet_turbulence_intensity: float = 5.0
    inlet_turbulence_viscosity_ratio: float = 10.0

    # 支持识别的列
    recognized_columns: Iterable[str] = field(
        default_factory=lambda: {
            "mesh",
            "mesh_file",
            "case_name",
            "model",
            "inlet_velocity",
            "viscosity",
            "pv_coupling",

            # 新列名
            "steady_iterations",
            "time_step",
            "number_of_time_steps",
            "max_iter_per_time_step",

            # 兼容旧列名
            "number_of_iterations",

            "processor_count",
            "precision",
            "dimension",
            "inlet_name",
            "inlet_turbulence_intensity",
            "inlet_turbulence_viscosity_ratio",
            "write_instantaneous_values",
            "output_case_data",
            "initialize_method",
        }
    )

    def __post_init__(self) -> None:
        self.base_dir = Path(self.base_dir)

        self.solve_dir.mkdir(parents=True, exist_ok=True)
        self.result_dir.mkdir(parents=True, exist_ok=True)
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_dir.mkdir(parents=True, exist_ok=True)

        self.default_case_settings["dimension"] = self.dimension
        self.default_case_settings["precision"] = self.precision

    @property
    def solve_dir(self) -> Path:
        return self.base_dir / self.solve_dir_name

    @property
    def result_dir(self) -> Path:
        return self.base_dir / self.result_dir_name

    @property
    def journal_dir(self) -> Path:
        return self.base_dir / self.journal_dir_name

    @property
    def transcript_dir(self) -> Path:
        return self.base_dir / self.transcript_dir_name

    @property
    def upstream_fluent_dir(self) -> Path:
        return self.base_dir.parent / self.upstream_fluent_dir_name

    @property
    def mesh_dir(self) -> Path:
        return self.upstream_fluent_dir / self.mesh_dir_name

    @property
    def solve_table_path(self) -> Path:
        return self.solve_dir / self.solve_table_name

    def resolve_mesh_file(self, mesh_value: Any) -> Path:
        """根据表格中的 mesh / mesh_file 列解析网格文件"""
        if mesh_value is None or str(mesh_value).strip() == "":
            raise ValueError("mesh 列为空，无法确定网格文件。")

        raw = str(mesh_value).strip()

        # 先尝试直接路径
        p = Path(raw)
        if p.exists():
            return p.resolve()

        # 相对 fluent3 根目录
        p2 = self.base_dir / raw
        if p2.exists():
            return p2.resolve()

        # 相对 ../fluent/mesh
        p3 = self.mesh_dir / raw
        if p3.exists():
            return p3.resolve()

        # 数字 -> mesh1 / mesh2
        candidate_stems: List[str] = []
        if raw.replace(".", "", 1).isdigit():
            num = int(float(raw))
            candidate_stems.extend([f"mesh{num}", str(num)])
        else:
            candidate_stems.append(Path(raw).stem)

        suffixes = [
            ".cas.h5",
            ".cas.gz",
            ".cas",
            ".msh.h5",
            ".msh.gz",
            ".msh",
        ]
        for stem in candidate_stems:
            for suffix in suffixes:
                c = self.mesh_dir / f"{stem}{suffix}"
                if c.exists():
                    return c.resolve()

        raise FileNotFoundError(
            f"未找到网格文件，输入值为: {mesh_value}\n"
            f"当前默认网格目录: {self.mesh_dir}"
        )

    def get_case_basename(self, case_index: int, row: Dict[str, Any]) -> str:
        case_name = row.get("case_name")
        if case_name is not None and str(case_name).strip():
            return str(case_name).strip()
        return f"solve{case_index}"

    def bool_to_yes_no(self, value: bool) -> str:
        return "yes" if bool(value) else "no"