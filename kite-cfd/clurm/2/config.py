from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List


@dataclass
class Config:
    """Fluent 2022 R1 批处理默认配置（支持 Slurm array 单工况模式）。"""

    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent)

    # Fluent 启动相关
    fluent_path: str = "/apps/soft/ansys/2022R1/ansys_inc/v221/fluent/bin/fluent"
    dimension: str = "3d"
    precision: str = "dp"  # 3ddp
    processor_count: int = 112
    headless: bool = True

    # 启动方式：在探索1000上，array 模式通常每个 task 占 1 个节点，建议直接用 -slurm
    use_slurm_launcher: bool = True

    # 目录
    mesh_dir_name: str = "mesh"
    solve_dir_name: str = "solve"
    result_dir_name: str = "result"
    journal_dir_name: str = "journal"
    transcript_dir_name: str = "transcript"

    # 输入表格
    solve_table_name: str = "solve_parameters.xlsx"
    solve_sheet_name: str | None = None

    # 默认求解设置
    default_case_settings: Dict[str, Any] = field(
        default_factory=lambda: {
            "model": "transition-sst",
            "time_type": "unsteady-1st-order",  # steady / unsteady-1st-order
            "inlet_velocity": 10.0,
            "viscosity": 1.813e-5,
            "pv_coupling": 24,
            "number_of_iterations": 300,
            "time_step": 0.005,
            "number_of_time_steps": 500,
            "max_iter_per_time_step": 10,
            "write_instantaneous_values": True,
            "output_case_data": True,
            "initialize_method": "hyb-initialization",
            "processor_count": 112,
            "dimension": "3d",
            "precision": "dp",
        }
    )

    # 力、力矩相关
    wall_zones: List[str] = field(
        default_factory=lambda: ["kite_edges", "kite_face", "kite_ribs"]
    )
    moment_center: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    # 默认入口条件
    inlet_name: str = "inlet"
    inlet_turbulence_intensity: float = 5.0
    inlet_turbulence_viscosity_ratio: float = 10.0

    # 支持识别的可选列
    recognized_columns: Iterable[str] = field(
        default_factory=lambda: {
            "mesh",
            "mesh_file",
            "case_name",
            "model",
            "time_type",
            "inlet_velocity",
            "viscosity",
            "pv_coupling",
            "number_of_iterations",
            "time_step",
            "number_of_time_steps",
            "max_iter_per_time_step",
            "processor_count",
            "precision",
            "dimension",
            "inlet_name",
            "inlet_turbulence_intensity",
            "inlet_turbulence_viscosity_ratio",
            "write_instantaneous_values",
            "output_case_data",
            "initialize_method",
            "steady_solve_dir",
        }
    )

    def __post_init__(self) -> None:
        self.base_dir = Path(self.base_dir)
        self.mesh_dir.mkdir(parents=True, exist_ok=True)
        self.solve_dir.mkdir(parents=True, exist_ok=True)
        self.result_dir.mkdir(parents=True, exist_ok=True)
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_dir.mkdir(parents=True, exist_ok=True)

        # 同步默认设置与顶层默认值，防止只改一处失效
        self.default_case_settings["processor_count"] = self.processor_count
        self.default_case_settings["dimension"] = self.dimension
        self.default_case_settings["precision"] = self.precision

    @property
    def mesh_dir(self) -> Path:
        return self.base_dir / self.mesh_dir_name

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
    def solve_table_path(self) -> Path:
        return self.solve_dir / self.solve_table_name

    def resolve_mesh_file(self, mesh_value: Any) -> Path:
        """根据表格中的 mesh / mesh_file 列解析网格文件。"""
        if mesh_value is None or str(mesh_value).strip() == "":
            raise ValueError("mesh 列为空，无法确定网格文件。")

        raw = str(mesh_value).strip()

        # 先尝试直接当路径
        p = Path(raw)
        if p.exists():
            return p.resolve()

        p2 = self.base_dir / raw
        if p2.exists():
            return p2.resolve()

        p3 = self.mesh_dir / raw
        if p3.exists():
            return p3.resolve()

        # 再尝试把 1 / 2 / 3 之类解释为 mesh1.*
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

        raise FileNotFoundError(f"未找到网格文件，输入值为: {mesh_value}")

    def get_case_basename(self, case_index: int, row: Dict[str, Any]) -> str:
        case_name = row.get("case_name")
        if case_name is not None and str(case_name).strip():
            return str(case_name).strip()
        return f"solve{case_index}"

    def get_case_prefix(self, case_index: int, row: Dict[str, Any]) -> str:
        """
        给每个工况一个稳定且唯一的前缀。
        例如：0001_alpha10
        这样 array 并发时不会互相覆盖。
        """
        base = self.get_case_basename(case_index, row)
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in base)
        return f"{case_index:04d}_{safe}"

    def bool_to_yes_no(self, value: bool) -> str:
        return "yes" if bool(value) else "no"