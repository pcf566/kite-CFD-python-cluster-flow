from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from config import Config
from solver import Solver


try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="读取 fluent3/solve/solve_parameters.xlsx，先稳态再非稳态连续求解。支持 Slurm array 单工况模式。"
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="项目根目录。默认是当前 main_solve.py 所在目录。",
    )
    parser.add_argument(
        "--excel",
        type=str,
        default="solve_parameters.xlsx",
        help="solve 目录下的参数表文件名。默认 solve_parameters.xlsx。",
    )
    parser.add_argument(
        "--sheet",
        type=str,
        default=None,
        help="Excel 工作表名称。默认读取第一个工作表。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只生成 .jou，不真正启动 Fluent。",
    )
    parser.add_argument(
        "--processors",
        type=int,
        default=None,
        help="设置 Fluent 并行核数；若不传，则优先读取 SLURM_NTASKS，最后由 Fluent 自行决定。",
    )
    parser.add_argument(
        "--fluent-path",
        type=str,
        default=None,
        help="覆盖 config.py 中的 fluent 可执行文件路径。",
    )
    parser.add_argument(
        "--dimension",
        type=str,
        default=None,
        choices=["2d", "3d"],
        help="覆盖默认维度。",
    )
    parser.add_argument(
        "--precision",
        type=str,
        default=None,
        choices=["sp", "dp", "single"],
        help="覆盖默认精度。",
    )
    parser.add_argument(
        "--case-index",
        type=int,
        default=None,
        help="只运行第几个有效工况（1-based）。适合 Slurm array。",
    )
    parser.add_argument(
        "--case-index-env",
        type=str,
        default="SLURM_ARRAY_TASK_ID",
        help="如果未显式传 --case-index，则尝试从该环境变量读取工况号。",
    )
    parser.add_argument(
        "--print-case-count",
        action="store_true",
        help="只打印有效工况总数，然后退出。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = Config(base_dir=args.base_dir)
    config.solve_table_name = args.excel
    config.solve_sheet_name = args.sheet

    if args.processors is not None:
        config.processor_count = args.processors
        config.default_case_settings["processor_count"] = args.processors

    if args.fluent_path is not None:
        config.fluent_path = args.fluent_path

    if args.dimension is not None:
        config.dimension = args.dimension
        config.default_case_settings["dimension"] = args.dimension

    if args.precision is not None:
        config.precision = args.precision
        config.default_case_settings["precision"] = args.precision

    solver = Solver(config)

    if args.print_case_count:
        print(solver.get_case_count())
        return

    case_index = args.case_index
    if case_index is None:
        env_value = os.environ.get(args.case_index_env)
        if env_value:
            try:
                case_index = int(env_value)
            except Exception as exc:
                raise ValueError(
                    f"环境变量 {args.case_index_env}={env_value} 不能转换为整数。"
                ) from exc

    print("=" * 72)
    print("Fluent 2022 R1 连续求解（稳态 -> 非稳态）")
    print(f"项目目录        : {config.base_dir}")
    print(f"参数表          : {config.solve_table_path}")
    print(f"网格目录        : {config.mesh_dir}")
    print(f"solve目录       : {config.solve_dir}")
    print(f"result目录      : {config.result_dir}")
    print(f"journal目录     : {config.journal_dir}")
    print(f"transcript目录  : {config.transcript_dir}")
    print(f"Fluent路径      : {config.fluent_path}")
    print(f"默认维度/精度    : {config.dimension}/{config.precision}")
    parallel_text = str(config.processor_count) if config.processor_count is not None else "自动"
    print(f"并行核数        : {parallel_text}")
    print(f"dry_run         : {args.dry_run}")
    print(f"指定工况号       : {case_index}")
    print("=" * 72)

    if case_index is None:
        print("未指定 --case-index，也未检测到数组环境变量，进入顺序批量模式。")
        solver.run_all(dry_run=args.dry_run)
    else:
        print(f"进入单工况模式：仅运行第 {case_index} 个有效工况。")
        solver.run_one_by_index(case_index, dry_run=args.dry_run)


if __name__ == "__main__":
    main()