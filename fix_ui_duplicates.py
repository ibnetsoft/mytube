# -*- coding: utf-8 -*-
import sys
import re

filepath = r"c:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\auth-web\components\DashboardContent.tsx"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Remove the duplicate useEffect
effect_target = """
    useEffect(() => {
        if (activeTab === 'withdrawals') {
            fetchWithdrawals();
        }
    }, [activeTab, fetchWithdrawals]);
"""
# If there are two of these, replace the first one with nothing.
if content.count(effect_target) > 1:
    content = content.replace(effect_target, "", 1)

# Remove the smaller-font withdrawal block.
# We will find the block that starts with "{activeTab === 'withdrawals' && (" 
# and contains "text-[10px]" (the smaller button).
blocks = re.findall(r"(\{activeTab === 'withdrawals' && \([\s\S]+?</div>\s*\)\})", content)
for block in blocks:
    if "text-[10px]" in block:
        content = content.replace(block, "")

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Duplicates successfully removed from DashboardContent.tsx")
