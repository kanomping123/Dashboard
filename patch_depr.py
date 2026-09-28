from pathlib import Path

OLD_LIST = '"รวมต้นทุนค่าซ่อม", "Total Cash",\n    "Total Freight", "Fuel (Cash)"'
NEW_LIST = '"รวมต้นทุนค่าซ่อม", "รวมค่าเสื่อม", "Total Cash",\n    "Total Freight", "Fuel (Cash)"'

EDITS = {
    "transport_cost_route.py": [
        (OLD_LIST, NEW_LIST),
        ('"รวมต้นทุนค่าซ่อม", "Total Cash", "Total Freight",\n}',
         '"รวมต้นทุนค่าซ่อม", "รวมค่าเสื่อม", "Total Cash", "Total Freight",\n}'),
    ],
    "database.py": [
        (OLD_LIST, NEW_LIST),
    ],
    "empty_trip.py": [
        ('PIE_DEFAULT = ["รวมต้นทุนค่าเดินทาง", "รวมต้นทุนค่าซ่อม"]',
         'PIE_DEFAULT = ["รวมต้นทุนค่าเดินทาง", "รวมต้นทุนค่าซ่อม", "รวมค่าเสื่อม"]'),
    ],
}

for name, pairs in EDITS.items():
    path = Path(name)
    if not path.exists():
        print(f"✗ ไม่พบไฟล์ {name}")
        continue
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if new in text:
            print(f"- {name}: แก้ไว้แล้ว ข้าม")
        elif text.count(old) == 1:
            text = text.replace(old, new)
            print(f"✓ {name}: แก้แล้ว")
        else:
            print(f"✗ {name}: หาข้อความเดิมไม่เจอ (ต้องแก้มือ)")
    path.write_text(text, encoding="utf-8")