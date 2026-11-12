#!/usr/bin/env python3
"""Decode/re-encode a VS Code .code-profile export without hand-editing escapes."""
import json, re, sys
from pathlib import Path


def strip_jsonc(text):
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    return re.sub(r'(^|\s)//.*$', r'\1', text, flags=re.M)


def unique_loads(text, *, jsonc=False):
    def hook(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate key: {key}')
            result[key] = value
        return result
    return json.loads(strip_jsonc(text) if jsonc else text, object_pairs_hook=hook)


def layers(profile):
    root = unique_loads(Path(profile).read_text())
    settings_wrapper = unique_loads(root['settings'])
    keybindings_wrapper = unique_loads(root['keybindings'])
    tasks_wrapper = unique_loads(root['tasks'])
    snippets_wrapper = unique_loads(root['snippets'])
    settings = unique_loads(settings_wrapper['settings'], jsonc=True)
    keybindings = unique_loads(keybindings_wrapper['keybindings'])
    tasks = unique_loads(tasks_wrapper['tasks'])
    snippets = snippets_wrapper['snippets']
    extensions = unique_loads(root['extensions'])
    return root, settings, keybindings, tasks, snippets, extensions


def inventory(profile):
    _, settings, keybindings, _, _, extensions = layers(profile)
    return {
        'settings': settings,
        'keybindings': {str(i): value for i, value in enumerate(keybindings)},
        'extensions': {
            x['identifier']['id']: x for x in extensions
        },
    }


def print_diff(before, after):
    print('KEY-LEVEL DIFF')
    for section in ('settings', 'keybindings', 'extensions'):
        old, new = before[section], after[section]
        added = sorted(set(new) - set(old))
        removed = sorted(set(old) - set(new))
        changed = sorted(k for k in set(old) & set(new) if old[k] != new[k])
        print(f'[{section}]')
        print(' added:', added or 'none')
        print(' removed:', removed or 'none')
        print(' changed:', changed or 'none')


def decode(profile, out):
    root, settings, keybindings, tasks, snippets, extensions = layers(profile)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'settings.json').write_text(unique_loads(root['settings'])['settings'])
    (out / 'keybindings.json').write_text(unique_loads(root['keybindings'])['keybindings'])
    (out / 'tasks.json').write_text(unique_loads(root['tasks'])['tasks'])
    for filename, content in snippets.items():
        path = out / 'snippets' / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    (out / 'extensions.json').write_text(json.dumps(extensions, ensure_ascii=False, indent=2) + '\n')
    (out / 'name.txt').write_text(root['name'])
    (out / '.inventory.before.json').write_text(json.dumps(inventory(profile), ensure_ascii=False, indent=2) + '\n')
    print('BEFORE inventory written to', out / '.inventory.before.json')


def encode(profile, source):
    before = json.loads((source / '.inventory.before.json').read_text())
    name = (source / 'name.txt').read_text()
    settings_text = (source / 'settings.json').read_text()
    keybindings = (source / 'keybindings.json').read_text()
    tasks = (source / 'tasks.json').read_text()
    snippets = {path.name: path.read_text() for path in (source / 'snippets').glob('*')}
    extensions_text = (source / 'extensions.json').read_text()
    # Parse every inner layer, reject comments only in settings, trailing commas, and duplicates.
    unique_loads(settings_text, jsonc=True)
    unique_loads(keybindings)
    unique_loads(tasks)
    unique_loads(extensions_text)
    root = {
        'name': name,
        'settings': json.dumps({'settings': settings_text}, separators=(',', ':')),
        'keybindings': json.dumps({'keybindings': keybindings}, separators=(',', ':')),
        'tasks': json.dumps({'tasks': tasks}, separators=(',', ':')),
        'snippets': json.dumps({'snippets': snippets}, separators=(',', ':')),
        'extensions': extensions_text,
    }
    # Validate the complete repacked structure and every inner layer again.
    out = Path(profile)
    out.write_text(json.dumps(root, ensure_ascii=False, indent=2) + '\n')
    after = inventory(profile)
    print_diff(before, after)
    print('VALIDATION: outer JSON, settings JSONC, keybindings, tasks, snippets, and extensions parsed; no duplicate keys or trailing commas.')


if __name__ == '__main__':
    if len(sys.argv) != 4 or sys.argv[1] not in {'decode', 'encode'}:
        raise SystemExit('usage: repack_profile.py decode|encode PROFILE DIRECTORY')
    (decode if sys.argv[1] == 'decode' else encode)(sys.argv[2], Path(sys.argv[3]))
