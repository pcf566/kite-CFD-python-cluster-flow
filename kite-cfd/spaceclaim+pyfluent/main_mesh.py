
from pathlib import Path
import re
import pandas as pd
from mesh_generator import MeshGenerator

from config import Config


def _clean_numeric_token(token):
    if token is None:
        return None
    token = str(token).strip()
    token = token.rstrip(".,;:")
    return token


def extract_first_float(text, pattern, flags=re.IGNORECASE):
    m = re.search(pattern, text, flags)
    if not m:
        return None
    token = _clean_numeric_token(m.group(1))
    try:
        return float(token)
    except Exception:
        return None


def extract_first_int(text, pattern, flags=re.IGNORECASE):
    m = re.search(pattern, text, flags)
    if not m:
        return None
    token = _clean_numeric_token(m.group(1))
    try:
        return int(token)
    except Exception:
        return None


def extract_first_str(text, pattern, flags=re.IGNORECASE):
    m = re.search(pattern, text, flags)
    if not m:
        return None
    return m.group(1).strip()

def find_latest_transcript_file(search_dirs=None):
    """查找最近生成的 Fluent transcript(.trn) 文件"""
    if search_dirs is None:
        search_dirs = [Path('.'), Path('mesh'), Path.cwd(), Path('/mnt/data')]

    candidates = []
    seen = set()
    for base in search_dirs:
        try:
            base = Path(base)
            if not base.exists():
                continue
            for p in base.rglob('*.trn'):
                rp = p.resolve()
                if rp in seen:
                    continue
                seen.add(rp)
                candidates.append(p)
        except Exception:
            continue

    if not candidates:
        return None

    return max(candidates, key=lambda p: p.stat().st_mtime)


def extract_cells_from_trn(trn_path: Path):
    """从 Fluent transcript 中提取总网格数。优先匹配 volume mesh 完成后的总单元数。"""
    try:
        text = trn_path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return None

    patterns = [
        r'-+\s*([0-9][0-9,]*)\s+cells\s+were\s+created\s+in\s*:',
        r'Total Number of Cells\s*[:=]\s*([0-9][0-9,]*)',
        r'cells\s*created\s*[:=]\s*([0-9][0-9,]*)',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            token = matches[-1].replace(',', '').strip()
            try:
                return int(token)
            except Exception:
                pass
    return None


def ensure_log_contains_cells(log_path: Path, trn_path: Path = None):
    """若 .log 中没有 cells，则从 .trn 读取并追加到 .log 末尾，供后续汇总解析。"""
    if not log_path or not Path(log_path).exists():
        return None

    log_path = Path(log_path)
    try:
        log_text = log_path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return None

    existing_cells = extract_first_int(log_text, r'Total\s+Cells\s*[:=]\s*([0-9][0-9,]*)')
    if existing_cells is not None:
        return existing_cells

    if trn_path is None:
        trn_path = find_latest_transcript_file()
    else:
        trn_path = Path(trn_path)

    if not trn_path or not trn_path.exists():
        return None

    cells = extract_cells_from_trn(trn_path)
    if cells is None:
        return None

    try:
        with log_path.open('a', encoding='utf-8', errors='ignore') as f:
            f.write(f"\nTotal Cells = {cells}\n")
            f.write(f"Cells Source Transcript = {trn_path.name}\n")
    except Exception:
        return cells

    return cells


def judge_orthogonal_quality(v):
    if v is None:
        return "缺失"
    if v >= 0.20:
        return "好"
    if v >= 0.10:
        return "可接受"
    if v >= 0.05:
        return "较差"
    return "很差"


def judge_cell_squish(v):
    if v is None:
        return "缺失"
    if v < 0.80:
        return "好"
    if v < 0.90:
        return "可接受"
    if v < 0.95:
        return "较差"
    return "很差"


def judge_aspect_ratio(v):
    if v is None:
        return "缺失"
    if v < 100:
        return "好"
    if v < 200:
        return "可接受"
    if v < 500:
        return "较差"
    return "很差"


def combine_grade(oq_grade, squish_grade, ar_grade, has_error=False):
    if has_error:
        return "失败/需检查"

    grades = [oq_grade, squish_grade, ar_grade]
    known = [g for g in grades if g != "缺失"]

    if not known:
        return "信息不足"
    if any(g == "很差" for g in known):
        return "差"
    if any(g == "较差" for g in known):
        return "一般"
    if all(g == "好" for g in known):
        return "较好"
    return "可用"


def parse_mesh_log(log_path: Path):
    text = log_path.read_text(encoding="utf-8", errors="ignore")

    result = {
        "log_file": log_path.name,
        "mesh_id": None,
        "log_status": "unknown",
        "has_error": False,
        "log_error_message": None,
        "transcript_start_time": None,
        "transcript_stop_time": None,
        "total_transcript_time": None,
        "cells": None,
        "core_count": None,
        "x_min": None,
        "x_max": None,
        "y_min": None,
        "y_max": None,
        "z_min": None,
        "z_max": None,
        "minimum_volume": None,
        "maximum_volume": None,
        "total_volume": None,
        "minimum_face_area": None,
        "maximum_face_area": None,
        "average_face_area": None,
        "minimum_orthogonal_quality": None,
        "maximum_cell_squish": None,
        "maximum_aspect_ratio": None,
        "minimum_expansion_ratio": None,
        "orthogonal_quality_grade": None,
        "cell_squish_grade": None,
        "aspect_ratio_grade": None,
        "overall_grade": None,
        "comment": None,
    }

    m = re.search(r"(mesh\d+)", log_path.stem, re.IGNORECASE)
    result["mesh_id"] = m.group(1).lower() if m else log_path.stem.lower()

    error_lines = re.findall(r"^.*Error:.*$", text, re.IGNORECASE | re.MULTILINE)
    if error_lines:
        result["has_error"] = True
        result["log_error_message"] = " | ".join(s.strip() for s in error_lines[:5])

    result["transcript_start_time"] = extract_first_str(text, r"Transcript Start Time:\s*(.+)")
    result["transcript_stop_time"] = extract_first_str(text, r"Transcript Stop Time:\s*(.+)")
    result["total_transcript_time"] = extract_first_str(text, r"Total Transcript Time:\s*(.+)")
    result["cells"] = extract_first_int(text, r"Total\s+Cells\s*[:=]\s*([0-9][0-9,]*)")

    all_core_matches = re.findall(r"^\s*n\d+\*?\s+\S+\s+(\d+)/\d+", text, re.MULTILINE)
    if all_core_matches:
        try:
            result["core_count"] = max(int(x) for x in all_core_matches)
        except Exception:
            pass

    result["x_min"] = extract_first_float(text, r"x-coordinate:\s*min\s*=\s*([0-9Ee+\-\.]+)")
    result["x_max"] = extract_first_float(text, r"x-coordinate:\s*min\s*=\s*[0-9Ee+\-\.]+\s*,\s*max\s*=\s*([0-9Ee+\-\.]+)")
    result["y_min"] = extract_first_float(text, r"y-coordinate:\s*min\s*=\s*([0-9Ee+\-\.]+)")
    result["y_max"] = extract_first_float(text, r"y-coordinate:\s*min\s*=\s*[0-9Ee+\-\.]+\s*,\s*max\s*=\s*([0-9Ee+\-\.]+)")
    result["z_min"] = extract_first_float(text, r"z-coordinate:\s*min\s*=\s*([0-9Ee+\-\.]+)")
    result["z_max"] = extract_first_float(text, r"z-coordinate:\s*min\s*=\s*[0-9Ee+\-\.]+\s*,\s*max\s*=\s*([0-9Ee+\-\.]+)")

    result["minimum_volume"] = extract_first_float(text, r"minimum volume:\s*([0-9Ee+\-\.]+)")
    result["maximum_volume"] = extract_first_float(text, r"maximum volume:\s*([0-9Ee+\-\.]+)")
    result["total_volume"] = extract_first_float(text, r"total volume:\s*([0-9Ee+\-\.]+)")

    result["minimum_face_area"] = extract_first_float(text, r"minimum face area:\s*([0-9Ee+\-\.]+)")
    result["maximum_face_area"] = extract_first_float(text, r"maximum face area:\s*([0-9Ee+\-\.]+)")
    result["average_face_area"] = extract_first_float(text, r"average face area:\s*([0-9Ee+\-\.]+)")

    result["minimum_orthogonal_quality"] = extract_first_float(
        text, r"Minimum Orthogonal Quality\s*=\s*([0-9Ee+\-\.]+)"
    )
    result["maximum_cell_squish"] = extract_first_float(
        text, r"Maximum Cell Squish\s*=\s*([0-9Ee+\-\.]+)"
    )
    result["maximum_aspect_ratio"] = extract_first_float(
        text, r"Maximum Aspect Ratio\s*=\s*([0-9Ee+\-\.]+)"
    )
    result["minimum_expansion_ratio"] = extract_first_float(
        text, r"Minimum Expansion Ratio\s*=\s*([0-9Ee+\-\.]+)"
    )

    has_done = bool(re.search(r"\bDone\.", text))
    has_quality = result["minimum_orthogonal_quality"] is not None
    if result["has_error"]:
        result["log_status"] = "error"
    elif has_done and has_quality:
        result["log_status"] = "ok"
    elif has_done:
        result["log_status"] = "done_but_incomplete"
    else:
        result["log_status"] = "incomplete"

    oq_grade = judge_orthogonal_quality(result["minimum_orthogonal_quality"])
    squish_grade = judge_cell_squish(result["maximum_cell_squish"])
    ar_grade = judge_aspect_ratio(result["maximum_aspect_ratio"])

    result["orthogonal_quality_grade"] = oq_grade
    result["cell_squish_grade"] = squish_grade
    result["aspect_ratio_grade"] = ar_grade
    result["overall_grade"] = combine_grade(
        oq_grade, squish_grade, ar_grade, has_error=result["has_error"]
    )

    comments = []
    oq = result["minimum_orthogonal_quality"]
    if oq is not None:
        if oq < 0.05:
            comments.append("最小正交质量很低，存在明显劣质单元风险")
        elif oq < 0.10:
            comments.append("最小正交质量偏低，建议重点检查局部区域")
        elif oq < 0.20:
            comments.append("最小正交质量尚可，但不算优秀")
        else:
            comments.append("最小正交质量较好")

    squish = result["maximum_cell_squish"]
    if squish is not None:
        if squish >= 0.95:
            comments.append("Cell Squish 很高，劣质单元风险大")
        elif squish >= 0.90:
            comments.append("Cell Squish 偏高，建议检查局部变形单元")
        else:
            comments.append("Cell Squish 可接受")

    ar = result["maximum_aspect_ratio"]
    if ar is not None:
        if ar >= 500:
            comments.append("最大长宽比非常大，可能影响局部精度或收敛")
        elif ar >= 200:
            comments.append("最大长宽比偏大")
        elif ar >= 100:
            comments.append("最大长宽比尚可")
        else:
            comments.append("最大长宽比较好")

    if result["has_error"] and result["log_error_message"]:
        comments.append(f"日志包含报错：{result['log_error_message']}")

    result["comment"] = "；".join(comments) if comments else None
    return result


def first_non_none(*values):
    for value in values:
        if value is not None and value != "":
            return value
    return None


def merge_mesh_record(group_no, alpha, beta, param_dict, mesh_info, log_info, mesh_file=None):
    row = {
        "group_no": group_no,
        "mesh_id": first_non_none(
            mesh_info.get("mesh_id") if mesh_info else None,
            log_info.get("mesh_id") if log_info else None,
            f"mesh{group_no}",
        ),
        "alpha": alpha,
        "beta": beta,
        "mesh_file": str(mesh_file) if mesh_file else None,
        "generation_status": mesh_info.get("status") if mesh_info else None,
        "log_status": log_info.get("log_status") if log_info else None,
        "status": first_non_none(
            mesh_info.get("status") if mesh_info else None,
            log_info.get("log_status") if log_info else None,
        ),
        "cells": first_non_none(
            mesh_info.get("cells") if mesh_info else None,
            log_info.get("cells") if log_info else None,
        ),
        "min_orthogonal_quality": first_non_none(
            mesh_info.get("min_orthogonal_quality") if mesh_info else None,
            log_info.get("minimum_orthogonal_quality") if log_info else None,
        ),
        "max_aspect_ratio": first_non_none(
            mesh_info.get("max_aspect_ratio") if mesh_info else None,
            log_info.get("maximum_aspect_ratio") if log_info else None,
        ),
        "negative_volume_count": mesh_info.get("negative_volume_count") if mesh_info else None,
        "error_message": first_non_none(
            mesh_info.get("error_message") if mesh_info else None,
            log_info.get("log_error_message") if log_info else None,
        ),
        "log_file": log_info.get("log_file") if log_info else None,
        "minimum_volume": log_info.get("minimum_volume") if log_info else None,
        "maximum_volume": log_info.get("maximum_volume") if log_info else None,
        "total_volume": log_info.get("total_volume") if log_info else None,
        "minimum_face_area": log_info.get("minimum_face_area") if log_info else None,
        "maximum_face_area": log_info.get("maximum_face_area") if log_info else None,
        "average_face_area": log_info.get("average_face_area") if log_info else None,
        "minimum_orthogonal_quality": log_info.get("minimum_orthogonal_quality") if log_info else None,
        "maximum_cell_squish": log_info.get("maximum_cell_squish") if log_info else None,
        "maximum_aspect_ratio": log_info.get("maximum_aspect_ratio") if log_info else None,
        "minimum_expansion_ratio": log_info.get("minimum_expansion_ratio") if log_info else None,
        "orthogonal_quality_grade": log_info.get("orthogonal_quality_grade") if log_info else None,
        "cell_squish_grade": log_info.get("cell_squish_grade") if log_info else None,
        "aspect_ratio_grade": log_info.get("aspect_ratio_grade") if log_info else None,
        "overall_grade": log_info.get("overall_grade") if log_info else None,
        "comment": log_info.get("comment") if log_info else None,
        "core_count": log_info.get("core_count") if log_info else None,
        "transcript_start_time": log_info.get("transcript_start_time") if log_info else None,
        "transcript_stop_time": log_info.get("transcript_stop_time") if log_info else None,
        "total_transcript_time": log_info.get("total_transcript_time") if log_info else None,
        "x_min": log_info.get("x_min") if log_info else None,
        "x_max": log_info.get("x_max") if log_info else None,
        "y_min": log_info.get("y_min") if log_info else None,
        "y_max": log_info.get("y_max") if log_info else None,
        "z_min": log_info.get("z_min") if log_info else None,
        "z_max": log_info.get("z_max") if log_info else None,
    }

    for k, v in param_dict.items():
        if k != "group_no":
            row[k] = v

    if row["status"] == "failed" and not row["overall_grade"]:
        row["overall_grade"] = "失败/需检查"

    return row


def build_summary_dataframe(rows):
    df = pd.DataFrame(rows)

    preferred_cols = [
        "group_no",
        "mesh_id",
        "alpha",
        "beta",
        "mesh_file",
        "status",
        "generation_status",
        "log_status",
        "overall_grade",
        "orthogonal_quality_grade",
        "cell_squish_grade",
        "aspect_ratio_grade",
        "cells",
        "min_orthogonal_quality",
        "max_aspect_ratio",
        "negative_volume_count",
        "minimum_orthogonal_quality",
        "maximum_cell_squish",
        "maximum_aspect_ratio",
        "minimum_expansion_ratio",
        "minimum_volume",
        "maximum_volume",
        "total_volume",
        "minimum_face_area",
        "maximum_face_area",
        "average_face_area",
        "core_count",
        "transcript_start_time",
        "transcript_stop_time",
        "total_transcript_time",
        "error_message",
        "comment",
        "log_file",
        "rib_size",
        "boi_size",
        "edge_size",
        "face_size",
        "surface_max_size",
        "surface_min_size",
        "volume_max_cell_length",
        "n_boundary_layers",
        "boi_growth_rate",
        "x_min",
        "x_max",
        "y_min",
        "y_max",
        "z_min",
        "z_max",
    ]

    existing_cols = [c for c in preferred_cols if c in df.columns]
    other_cols = [c for c in df.columns if c not in existing_cols]
    if existing_cols:
        df = df[existing_cols + other_cols]

    if "group_no" in df.columns:
        df = df.sort_values(by="group_no")
    return df


def main():
    """主函数 - 网格生成 + 网格日志后处理汇总"""

    mesh_excel_path = Path("mesh") / "mesh_parameters.xlsx"
    mesh_summary_xlsx = Path("mesh") / "mesh_summary.xlsx"
    mesh_summary_csv = Path("mesh") / "mesh_summary.csv"

    if not mesh_excel_path.exists():
        print(f"错误: 网格参数文件不存在: {mesh_excel_path}")
        print("请先在 mesh 文件夹中准备 mesh_parameters.xlsx")
        return

    try:
        mesh_df = pd.read_excel(mesh_excel_path)
    except Exception as e:
        print(f"错误: 读取 Excel 失败: {e}")
        return

    required_columns = [
        "alpha",
        "beta",
        "rib_size",
        "boi_size",
        "edge_size",
        "face_size",
        "surface_max_size",
        "surface_min_size",
        "volume_max_cell_length",
        "n_boundary_layers",
        "boi_growth_rate",
    ]

    missing_columns = [col for col in required_columns if col not in mesh_df.columns]
    if missing_columns:
        print("错误: Excel 缺少以下必要列：")
        for col in missing_columns:
            print(f"  - {col}")
        return

    mesh_df = mesh_df.dropna(how="all")
    if mesh_df.empty:
        print("错误: Excel 中没有有效数据行")
        return

    mesh_combinations = []
    for row_idx, row in mesh_df.iterrows():
        param_dict = {}

        for col in required_columns:
            value = row[col]
            if pd.isna(value):
                print(f"错误: 第 {row_idx + 2} 行参数 {col} 为空，请检查 Excel")
                return

            if col == "n_boundary_layers":
                value = int(value)
            else:
                value = float(value)
            param_dict[col] = value

        if "number" in mesh_df.columns and not pd.isna(row["number"]):
            group_no = int(row["number"])
        else:
            group_no = len(mesh_combinations) + 1

        param_dict["group_no"] = group_no
        mesh_combinations.append(param_dict)

    print("=== 网格参数确认 ===")
    print(f"参数文件: {mesh_excel_path}")
    print(f"总网格组数: {len(mesh_combinations)}")

    print("\n具体网格参数组合:")
    for param_dict in mesh_combinations:
        group_no = param_dict["group_no"]
        display_items = [f"{k}={v}" for k, v in param_dict.items() if k != "group_no"]
        print(f"网格组 {group_no}: " + ", ".join(display_items))

    confirm = input("\n确认运行以上网格参数组合？ (y/n): ")
    if confirm.lower() != "y":
        print("取消运行")
        return

    print("\n=== 开始生成网格 ===")
    mesh_rows = []

    for idx, param_dict in enumerate(mesh_combinations, 1):
        group_no = param_dict["group_no"]
        alpha = param_dict["alpha"]
        beta = param_dict["beta"]

        print(f"\n运行网格组 {group_no}/{len(mesh_combinations)}")
        display_items = [f"{k}={v}" for k, v in param_dict.items() if k != "group_no"]
        print("参数: " + ", ".join(display_items))

        config = Config()
        for key in [
            "boi_size",
            "edge_size",
            "rib_size",
            "face_size",
            "surface_max_size",
            "surface_min_size",
            "volume_max_cell_length",
            "boi_growth_rate",
            "n_boundary_layers",
            "processor_count",
            "precision",
        ]:
            if key in param_dict:
                config.mesh_settings[key] = param_dict[key]

        print("最终传入的 mesh_settings =", config.mesh_settings)
        mesh_generator = MeshGenerator(config)

        mesh_file = None
        mesh_info = {
            "mesh_id": f"mesh{group_no}",
            "status": None,
            "cells": None,
            "min_orthogonal_quality": None,
            "max_aspect_ratio": None,
            "negative_volume_count": None,
            "error_message": "",
        }

        try:
            mesh_file, generated_info = mesh_generator.generate_mesh(alpha, beta, group_no)
            mesh_info.update(generated_info or {})
            print(f"网格文件已生成: {mesh_file}")
        except Exception as e:
            mesh_info["status"] = "failed"
            mesh_info["error_message"] = str(e)
            print(f"网格组 {group_no} 失败: {e}")

        log_path = Path("mesh") / f"mesh{group_no}_meshinfo.log"
        log_info = {}
        if log_path.exists():
            try:
                appended_cells = ensure_log_contains_cells(log_path)
                if appended_cells is not None:
                    print(f"已向日志补充总网格数 cells={appended_cells}")
                log_info = parse_mesh_log(log_path)
                print(f"已读取日志: {log_path}")
            except Exception as e:
                log_info = {
                    "mesh_id": f"mesh{group_no}",
                    "log_file": log_path.name,
                    "log_status": "parse_failed",
                    "log_error_message": str(e),
                    "overall_grade": "失败/需检查",
                }
                print(f"日志解析失败: {log_path} -> {e}")
        else:
            print(f"未找到日志文件: {log_path}")

        row = merge_mesh_record(group_no, alpha, beta, param_dict, mesh_info, log_info, mesh_file)
        mesh_rows.append(row)

        summary_df = build_summary_dataframe(mesh_rows)
        mesh_summary_xlsx.parent.mkdir(parents=True, exist_ok=True)
        summary_df.to_excel(mesh_summary_xlsx, index=False)
        summary_df.to_csv(mesh_summary_csv, index=False, encoding="utf-8-sig")
        print(f"已更新汇总表: {mesh_summary_xlsx}")
        print(f"已更新汇总表: {mesh_summary_csv}")

    print("\n=== 网格生成完成 ===")
    print(f"共处理 {len(mesh_rows)} 个网格组合")
    print(f"汇总表已保存到: {mesh_summary_xlsx}")
    print(f"汇总表已保存到: {mesh_summary_csv}")


if __name__ == "__main__":
    main()
