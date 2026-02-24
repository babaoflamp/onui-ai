import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SENTENCES_FILE = os.path.join(BASE_DIR, "data", "sentences.json")
NEW_FILE = os.path.join(BASE_DIR, "data", "new_sentences_temp.json")

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def main():
    if not os.path.exists(SENTENCES_FILE):
        print(f"Error: {SENTENCES_FILE} not found.")
        return

    if not os.path.exists(NEW_FILE):
        print(f"Error: {NEW_FILE} not found.")
        return

    try:
        existing = load_json(SENTENCES_FILE)
        print(f"Existing count: {len(existing)}")
    except Exception as e:
        print(f"Error reading existing file: {e}")
        return

    try:
        new_data = load_json(NEW_FILE)
        print(f"New count: {len(new_data)}")
    except Exception as e:
        print(f"Error reading new data file: {e}")
        return

    existing_ids = {item['id'] for item in existing}
    
    added_count = 0
    for item in new_data:
        if item['id'] in existing_ids:
            print(f"Skipping duplicate ID: {item['id']}")
            continue
        existing.append(item)
        added_count += 1
    
    existing.sort(key=lambda x: x['id'])

    save_json(SENTENCES_FILE, existing)
    print(f"Merged successfully. Total count: {len(existing)}")
    print(f"Added {added_count} items.")

if __name__ == "__main__":
    main()
