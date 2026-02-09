import json
from pathlib import Path

cards_en = json.load(Path("en.json").open())
cards_any = json.load(Path("any.json").open())


total_diff = 0
diffs = {}
for card in sorted(set(list(cards_en.keys()) + list(cards_any.keys()))):
    if card not in cards_en or card not in cards_any:
        continue
    diff = cards_en[card] - cards_any[card]
    diffs[card] = diff


min_diff = 50
max_diff = 1000
for card, diff in diffs.items():
    if min_diff <= diff <= max_diff:
        total_diff += diff
        diff_dollars = round(diff / 100, 2)
        print(f"{card=} {diff_dollars=}")
total_diff_dollars = round(total_diff / 100, 2)
print(f"Total diff: {total_diff_dollars=}")
