import sys

filepath = r"c:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\auth-web\components\DashboardContent.tsx"
with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Delete lines 2530 to 2581 (0-indexed 2529 to 2580)
# Delete lines 1358 to 1364 (0-indexed 1357 to 1363)
del lines[2529:2581]
del lines[1357:1364]

with open(filepath, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Deleted duplicate lines by index.")
