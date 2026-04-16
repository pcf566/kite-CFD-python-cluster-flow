from pathlib import Path
import subprocess
import pandas as pd


def round_angle(x, ndigits=4):
    """角度比较统一按四位小数处理"""
    return round(float(x), ndigits)


def format_num(x, ndigits=4):
    """
    数值转字符串：
    1. 先四舍五入到 ndigits 位小数
    2. 去掉末尾多余的 0 和 .
    """
    x = round(float(x), ndigits)
    s = f"{x:.{ndigits}f}".rstrip("0").rstrip(".")
    if s == "-0":
        s = "0"
    return s


def extract_angles_from_filename(file_path: Path):
    """
    从文件名中提取 alpha、beta
    例如：
    KITE_3.081078467_0.scdoc
    -> alpha=3.081078467, beta=0
    """
    stem = file_path.stem
    parts = stem.split("_")

    if len(parts) < 3:
        raise ValueError(f"文件名格式不正确，无法提取角度: {file_path.name}")

    alpha_str = parts[-2]
    beta_str = parts[-1]
    return float(alpha_str), float(beta_str)


def find_matching_geometry_file(output_dir: Path, alpha, beta):
    """
    在 output_dir 中查找与 alpha、beta 匹配的 .scdoc 文件。
    匹配规则：只比较到小数点后 4 位。
    """
    alpha_target = round_angle(alpha, 4)
    beta_target = round_angle(beta, 4)

    scdoc_files = list(output_dir.glob("KITE_*.scdoc"))

    matched_files = []
    for file_path in scdoc_files:
        try:
            file_alpha, file_beta = extract_angles_from_filename(file_path)
        except Exception:
            continue

        if round_angle(file_alpha, 4) == alpha_target and round_angle(file_beta, 4) == beta_target:
            matched_files.append(file_path)

    if len(matched_files) >= 1:
        return matched_files[0]

    return None


def main():
    base_dir = Path(__file__).parent

    spaceclaim_exe = Path(r"C:\Program Files\ANSYS Inc242\v242\scdm\SpaceClaim.exe")
    script_path = base_dir / "rotate_kite.py"
    input_file = base_dir / "KITE.scdoc"
    output_dir = base_dir / "geometry"
    excel_path = output_dir / "geometry.xlsx"

    output_dir.mkdir(exist_ok=True)

    # 检查必要文件
    if not spaceclaim_exe.exists():
        print(f"错误: SpaceClaim 可执行文件不存在: {spaceclaim_exe}")
        return

    if not script_path.exists():
        print(f"错误: rotate_kite.py 不存在: {script_path}")
        return

    if not input_file.exists():
        print(f"错误: 基础几何文件不存在: {input_file}")
        return

    if not excel_path.exists():
        print(f"错误: geometry 参数表不存在: {excel_path}")
        return

    # 读取 Excel
    try:
        df = pd.read_excel(excel_path)
    except Exception as e:
        print(f"错误: 读取 Excel 失败: {e}")
        return

    # 检查必要列
    required_columns = ["alpha", "beta"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        print("错误: Excel 缺少以下必要列：")
        for col in missing_columns:
            print(f"  - {col}")
        return

    # 删除全空行
    df = df.dropna(how="all")

    if df.empty:
        print("错误: geometry.xlsx 中没有有效数据行")
        return

    # 提取参数
    geometry_tasks = []
    for row_idx, row in df.iterrows():
        alpha = row["alpha"]
        beta = row["beta"]

        if pd.isna(alpha) or pd.isna(beta):
            print(f"错误: 第 {row_idx + 2} 行的 alpha 或 beta 为空，请检查 Excel")
            return

        alpha = float(alpha)
        beta = float(beta)

        geometry_tasks.append({
            "row_no": row_idx + 2,   # Excel 实际行号（含表头偏移）
            "alpha": alpha,
            "beta": beta
        })

    print("=== 几何参数确认 ===")
    print(f"参数文件: {excel_path}")
    print(f"总组合数: {len(geometry_tasks)}")
    for task in geometry_tasks:
        print(f"第 {task['row_no']} 行: alpha={task['alpha']}, beta={task['beta']}")

    # 开始处理
    print("\n=== 开始检查并生成几何文件 ===")

    generated_count = 0
    skipped_count = 0

    for task in geometry_tasks:
        alpha = task["alpha"]
        beta = task["beta"]

        # 先按“四位小数匹配”检查是否已存在
        matched_file = find_matching_geometry_file(output_dir, alpha, beta)

        if matched_file is not None:
            print(
                f"跳过 alpha={alpha}, beta={beta}："
                f"已存在匹配文件 {matched_file.name} "
                f"(按四位小数比较)"
            )
            skipped_count += 1
            continue

        # 不存在时，生成新的输出文件名
        output_file = output_dir / f"KITE_{format_num(alpha)}_{format_num(beta)}.scdoc"
        script_args = f"{input_file},{output_file},{alpha},{beta}"

        cmd = [
            str(spaceclaim_exe),
            "/Headless=True",
            "/Splash=False",
            "/Welcome=False",
            f"/RunScript={script_path}",
            f"/ScriptArgs={script_args}",
            "/ExitAfterScript=True"
        ]

        print(f"开始生成: alpha={alpha}, beta={beta}")
        print(f"输出文件: {output_file}")

        try:
            subprocess.run(cmd, check=True)
            print(f"生成完成: {output_file.name}")
            generated_count += 1
        except subprocess.CalledProcessError as e:
            print(f"错误: 生成失败 alpha={alpha}, beta={beta}")
            print(f"命令返回码: {e.returncode}")

    print("\n=== 全部完成 ===")
    print(f"新生成文件数: {generated_count}")
    print(f"跳过文件数: {skipped_count}")


if __name__ == "__main__":
    main()