#!/usr/bin/env python3
import json, sys
from pathlib import Path
p=Path(sys.argv[1])
data=json.loads((p/"jurisdiction.json").read_text(encoding="utf-8"))
print(data["jurisdiction"]["name"])
for rt in data["records"]["role_terms"]:
    print(rt.get("person_id"), "->", rt.get("office_id"))
