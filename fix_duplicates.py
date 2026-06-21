# -*- coding: utf-8 -*-
import sys
import re

filepath = r"c:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\auth-web\components\DashboardContent.tsx"
with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
skip = False
state_count = 0
fetch_count = 0
update_count = 0

i = 0
while i < len(lines):
    line = lines[i]
    if "const [withdrawals, setWithdrawals]" in line:
        state_count += 1
        if state_count > 1:
            i += 1
            continue
    
    if "const fetchWithdrawals = useCallback" in line:
        fetch_count += 1
        if fetch_count > 1:
            # skip the whole block
            while i < len(lines) and "}, [])" not in lines[i]:
                i += 1
            i += 1 # skip the `}, [])` line
            continue
    
    if "const updateWithdrawalStatus = async" in line:
        update_count += 1
        if update_count > 1:
            # skip the whole block
            while i < len(lines) and "    }" not in lines[i]:
                i += 1
            i += 1 # skip the `    }` line
            continue
            
    # Remove duplicate withdrawal tab JSX
    if "{activeTab === 'withdrawals' && (" in line:
        # Check if we already have a withdrawals tab
        if any("수당 출금 요청 리스트" in l for l in new_lines):
            # Wait, if the file already has one, we only want the NEW ONE.
            # Actually, my script injected the new one. The old one might be there too.
            pass

    new_lines.append(line)
    i += 1

with open(filepath, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Duplicates removed from DashboardContent.tsx")
