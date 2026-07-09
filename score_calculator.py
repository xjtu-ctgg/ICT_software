#!/usr/bin/env python3
"""
评分计算脚本 — 竞赛用例评分工具

使用方法（两种模式）:

模式1 - 从MD日志解析（推荐）:
    python score_calculator.py <md文件路径>
    解析MD格式评分日志中的 "评分汇总" 部分，逐用例计算交集，结果准确。
    同时也会解析 "助理裁判" 部分作为交叉验证。

模式2 - 交互式逐用例输入:
    python score_calculator.py
    逐行输入每个用例的5票结果（格式: True,True,True,False,False），空行结束。

    如果只有各裁判通过总数且不需要精确交集:
    python score_calculator.py --simple
    输入总用例数和5个裁判的通过数（注意：此模式下稳定性用最小值近似，不精确）。

评分规则:
    - 用例通过率 = 5个裁判通过的用例数之和 / 5
    - 稳定性     = 5个裁判都判通过的用例数（逐用例取交集，即5/5全票通过的用例数）
    - 准确性     = 5个裁判中通过用例数的最大值
    - 最终得分   = 100 × (稳定性通过数 + 准确通过数) / (总用例数 × 2)

MD日志格式示例（评分汇总部分）:
    ### 评分汇总
    - group-1-1: votes=[True, True, True, True, True], pass_count=5, accuracy_passed=True, stability_passed=True
    - group-1-2: votes=[False, False, False, False, False], pass_count=0, accuracy_passed=False, stability_passed=False
    ...

    ### 助理裁判
    - assistant_judge_1: executor_status=success, scoring_completed=True, note=8/24题通过
    ...
"""

import re
import sys


def parse_md(filepath):
    """从MD日志解析评分汇总和助理裁判数据"""
    votes_per_case = {}   # case_idx -> [bool, bool, bool, bool, bool]
    judge_totals = {}     # judge_name -> pass_count

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 解析评分汇总: - group-1-N: votes=[True, True, ...], pass_count=N, ...
    vote_pattern = r'group-\d+-(\d+):\s*votes=\[([^\]]+)\]'
    for m in re.finditer(vote_pattern, content):
        case_idx = int(m.group(1))
        votes_str = m.group(2)
        votes = [v.strip() == 'True' for v in votes_str.split(',')]
        votes_per_case[case_idx] = votes

    # 解析助理裁判: - assistant_judge_N: ... note=N/M题通过
    judge_pattern = r'assistant_judge_(\d+):.*?note=(\d+)/\d+题通过'
    for m in re.finditer(judge_pattern, content):
        judge_idx = int(m.group(1))
        pass_count = int(m.group(2))
        judge_totals[judge_idx] = pass_count

    return votes_per_case, judge_totals


def compute_scores(votes_per_case, total_cases):
    """根据逐用例投票数据计算所有评分指标"""
    per_judge_pass = [0] * 5
    stability_count = 0

    for case_idx in sorted(votes_per_case.keys()):
        votes = votes_per_case[case_idx]
        if all(votes):
            stability_count += 1
        for j in range(5):
            if votes[j]:
                per_judge_pass[j] += 1

    pass_rate = sum(per_judge_pass) / 5
    accuracy = max(per_judge_pass)
    final_score = 100 * (stability_count + accuracy) / (total_cases * 2)

    return per_judge_pass, stability_count, accuracy, pass_rate, final_score


def print_detail(votes_per_case, per_judge_pass, stability_count, accuracy, pass_rate, final_score, total_cases, judge_totals=None):
    """输出详细评分结果"""
    print()
    print("=" * 40)
    print("          评 分 结 果")
    print("=" * 40)
    print(f"  总用例数:         {total_cases}")

    # 裁判通过数
    print(f"  各裁判通过数:     {per_judge_pass}")
    if judge_totals:
        # 用日志中的助理裁判数据做交叉验证
        judge_list = [judge_totals.get(i+1, '?') for i in range(5)]
        match = all(judge_totals.get(i+1) == per_judge_pass[i] for i in range(5))
        status = "✓ 一致" if match else "✗ 不一致!"
        print(f"  日志助理裁判数据: {judge_list}  {status}")

    print(f"  用例通过率:       {pass_rate:.2f}")
    print(f"  稳定性(全票通过): {stability_count}/{total_cases}")
    print(f"  准确性(最佳裁判): {accuracy}/{total_cases}")
    print(f"  最终得分:         {final_score:.2f}")
    print("=" * 40)

    # 稳定/不稳定用例详情
    stable_cases = sorted([idx for idx in votes_per_case if all(votes_per_case[idx])])
    unstable_cases = sorted([idx for idx in votes_per_case if not all(votes_per_case[idx])])

    print(f"\n  稳定通过的用例 ({len(stable_cases)}): {stable_cases}")
    print(f"  未稳定通过的用例 ({len(unstable_cases)}): {unstable_cases}")

    if unstable_cases:
        print("\n  --- 不稳定用例投票详情 ---")
        for idx in unstable_cases:
            v = votes_per_case[idx]
            judges_pass = [j+1 for j in range(5) if v[j]]
            judges_fail = [j+1 for j in range(5) if not v[j]]
            print(f"    group-1-{idx:2d}: 通过裁判{judges_pass}, 未通过裁判{judges_fail}  ({sum(v)}/5)")

    # 逐裁判视角
    print("\n  --- 逐裁判视角 ---")
    for j in range(5):
        passed = [idx for idx in sorted(votes_per_case) if votes_per_case[idx][j]]
        print(f"    裁判{j+1}: 通过{len(passed)}题 {passed}")


def main():
    args = sys.argv[1:]

    # 模式1: 从MD日志文件解析（默认模式）
    if args and args[0] not in ('--simple',):
        filepath = args[0]
        votes_per_case, judge_totals = parse_md(filepath)

        if not votes_per_case:
            print(f"未在 {filepath} 中找到评分汇总数据。")
            sys.exit(1)

        total_cases = max(votes_per_case.keys())
        per_judge_pass, stability_count, accuracy, pass_rate, final_score = \
            compute_scores(votes_per_case, total_cases)

        print_detail(votes_per_case, per_judge_pass, stability_count,
                     accuracy, pass_rate, final_score, total_cases, judge_totals)
        return

    # 模式2: 简单模式（仅输入各裁判通过数）
    if args and args[0] == '--simple':
        total = int(input("请输入总用例数: "))
        passed_counts = []
        for i in range(5):
            count = int(input(f"请输入第{i+1}个裁判通过用例数: "))
            passed_counts.append(count)

        pass_rate = sum(passed_counts) / 5
        stability = min(passed_counts)  # 近似值
        accuracy = max(passed_counts)
        final_score = 100 * (stability + accuracy) / (total * 2)

        print()
        print("=" * 40)
        print("      评分结果（近似 - 无逐用例数据）")
        print("=" * 40)
        print(f"  各裁判通过数:       {passed_counts}")
        print(f"  用例通过率:         {pass_rate:.2f}")
        print(f"  稳定性(最小值近似): {stability}/{total}  ⚠ 非精确交集")
        print(f"  准确性(最大值):     {accuracy}/{total}")
        print(f"  最终得分(近似):     {final_score:.2f}")
        print("=" * 40)
        return

    # 模式3: 逐用例交互输入
    print("请逐行输入每个用例的5票结果（格式: True,True,True,False,False）")
    print("输入空行结束输入\n")

    votes_per_case = {}
    case_idx = 1
    while True:
        line = input(f"用例 {case_idx} votes: ").strip()
        if not line:
            break
        votes = [v.strip() == 'True' for v in line.split(',')]
        if len(votes) != 5:
            print(f"  ⚠ 需要5个值，当前{len(votes)}个，请重新输入")
            continue
        votes_per_case[case_idx] = votes
        case_idx += 1

    if not votes_per_case:
        print("未输入任何用例数据。")
        return

    total_cases = max(votes_per_case.keys())
    per_judge_pass, stability_count, accuracy, pass_rate, final_score = \
        compute_scores(votes_per_case, total_cases)

    print_detail(votes_per_case, per_judge_pass, stability_count,
                 accuracy, pass_rate, final_score, total_cases)


if __name__ == "__main__":
    main()