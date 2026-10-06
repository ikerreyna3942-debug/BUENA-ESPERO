import difflib

with open("modules/prompt_studio_v3.py", "r", encoding="utf-8", errors="ignore") as f1:
    lines1 = f1.readlines()

with open("modules/prompt_studio_v4.py", "r", encoding="utf-8", errors="ignore") as f2:
    lines2 = f2.readlines()

diff = list(difflib.unified_diff(lines1, lines2, fromfile="modules/prompt_studio_v3.py", tofile="modules/prompt_studio_v4.py"))
with open(".agents/teamwork/explorer_r1_1/diff_v3_v4.txt", "w", encoding="utf-8") as out:
    out.writelines(diff)

print(f"Diff written, {len(diff)} lines")
