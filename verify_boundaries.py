"""Run before extraction: python verify_boundaries.py (no token required)."""
from pathlib import Path
from boundary53 import load_city_polygons, read_registry

def main():
    root = Path(__file__).resolve().parent
    registry_path = root / 'data' / 'city_registry_53.csv'
    boundaries = load_city_polygons(root / 'data' / 'cities boundary', registry_path)
    registry = read_registry(registry_path)
    print('\nVerified study cities:')
    for i, key in enumerate(sorted(boundaries), 1):
        print(f'{i:2}. {registry[key][0]}, {registry[key][1]}')

if __name__ == '__main__':
    main()
