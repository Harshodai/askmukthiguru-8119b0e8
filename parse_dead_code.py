import json
with open('/Users/harshodaikolluru/.gemini/antigravity/brain/8bb8831f-e23b-4832-b5d9-5608c600ba1b/.system_generated/steps/1881/output.txt', 'r') as f:
    data = json.load(f)

dead_code = data.get('dead_code', [])
backend_dead = [d for d in dead_code if '/backend/' in d['file'] and not d['file'].endswith('test') and not 'master_schema' in d['file']]
for d in backend_dead:
    print(f"{d['kind']} {d['name']} at {d['file']}:{d['line']}")
