# You can save this as list_files.py and run it
import os

def print_tree(startpath, indent=''):
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, '').count(os.sep)
        prefix = ' ' * 4 * level
        print(f"{prefix}{os.path.basename(root)}/")
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            print(f"{subindent}{f}")

print_tree('.')