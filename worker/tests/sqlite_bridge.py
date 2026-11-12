import json
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
connection.row_factory = sqlite3.Row
request = json.load(sys.stdin)
if 'script' in request:
    connection.executescript(request['script'])
    rows = []
else:
    rows = [dict(row) for row in connection.execute(request['sql'], request.get('params', []))]
connection.commit()
print(json.dumps(rows))
