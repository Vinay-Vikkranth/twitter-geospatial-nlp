"""Strict boundary loading for the fixed Project 53 city/state registry.

The bundled Census WKT files are NAD83 (EPSG:4269). Tweet coordinates are
longitude/latitude in EPSG:4326. Never infer identity or CRS from a filename.
"""
import csv
import re
import sys
from pathlib import Path

SOURCE_CRS = 'EPSG:4269'
TARGET_CRS = 'EPSG:4326'
EXPECTED_CITY_COUNT = 53


def normalize_city_key(value):
    text = re.sub(r'\s+', ' ', str(value).strip().lower().replace('-', ' ').replace('_', ' '))
    return {'saint louis': 'st louis', 'st. louis': 'st louis',
            'city of phoenix': 'phoenix', 'indianapolis city': 'indianapolis',
            'nashville davidson metropolitan government (balance)': 'nashville',
            'nashville davidson': 'nashville', 'orleans': 'new orleans'}.get(text, text)


def city_state_key(city, state):
    return normalize_city_key(city), re.sub(r'\s+', ' ', str(state).strip().lower())


def read_registry(registry_path):
    with Path(registry_path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not {'City', 'State'} <= set(reader.fieldnames or []):
            raise ValueError('City registry must contain City and State columns.')
        rows = list(reader)
    registry = {}
    for row in rows:
        if not row['City'].strip() or not row['State'].strip():
            raise ValueError('Blank City/State in registry.')
        key = city_state_key(row['City'], row['State'])
        if key in registry:
            raise ValueError(f'Duplicate registry city/state: {key}')
        registry[key] = (row['City'], row['State'])
    if len(registry) != EXPECTED_CITY_COUNT:
        raise ValueError(f'Registry must contain exactly 53 unique city/state pairs; found {len(registry)}.')
    return registry


def read_incident_city_aliases(path, registry):
    """Explicit historical City_std assignments; never strip arbitrary parentheses."""
    aliases = {}
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not {'City Or County', 'State', 'City_std'} <= set(reader.fieldnames or []):
            raise ValueError('Incident aliases require City Or County, State, City_std.')
        for row in reader:
            if any(not row[c].strip() for c in ('City Or County', 'State', 'City_std')):
                raise ValueError('Blank incident alias field.')
            source = city_state_key(row['City Or County'], row['State'])
            target = city_state_key(row['City_std'], row['State'])
            if target not in registry or (source in registry and source != target):
                raise ValueError(f'Invalid incident city assignment: {source} -> {target}')
            if source in aliases and aliases[source] != target:
                raise ValueError(f'Conflicting incident alias: {source}')
            aliases[source] = target
    return aliases


def load_city_polygons(boundary_dir, registry_path):
    from shapely import wkt
    from shapely.ops import transform
    from pyproj import Transformer
    csv.field_size_limit(min(sys.maxsize, 10**9))
    registry = read_registry(registry_path)
    files = sorted(Path(boundary_dir).glob('*.csv'))
    polygons = {}
    transformer = Transformer.from_crs(SOURCE_CRS, TARGET_CRS, always_xy=True)
    for path in files:
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if not {'WKT', 'City', 'State'} <= set(reader.fieldnames or []):
                raise ValueError(f'{path.name}: required columns are WKT, City and State.')
            rows = list(reader)
        if len(rows) != 1:
            raise ValueError(f'{path.name}: expected exactly one boundary row, found {len(rows)}.')
        row = rows[0]
        key = city_state_key(row['City'], row['State'])
        if key not in registry:
            raise ValueError(f'Unexpected city/state boundary: {key} in {path.name}')
        if key in polygons:
            raise ValueError(f'Duplicate city/state boundary: {key}')
        geom = wkt.loads(row['WKT'])
        if geom.is_empty or not geom.is_valid or geom.geom_type not in ('Polygon', 'MultiPolygon'):
            raise ValueError(f'{path.name}: boundary must be a valid nonempty Polygon/MultiPolygon.')
        xmin, ymin, xmax, ymax = geom.bounds
        if not (-180 <= xmin <= xmax <= 180 and -90 <= ymin <= ymax <= 90):
            raise ValueError(f'{path.name}: coordinates do not match declared {SOURCE_CRS}.')
        geom = transform(transformer.transform, geom)
        if geom.is_empty or not geom.is_valid:
            raise ValueError(f'{path.name}: geometry invalid after coordinate transformation.')
        polygons[key] = geom
    missing = set(registry) - set(polygons)
    if missing:
        labels = [', '.join(registry[k]) for k in sorted(missing)]
        raise ValueError('Missing required city boundaries: ' + '; '.join(labels))
    if len(files) != EXPECTED_CITY_COUNT or len(polygons) != EXPECTED_CITY_COUNT:
        raise ValueError(f'Expected 53 files and 53 city/state boundaries, got {len(files)} and {len(polygons)}.')
    print('BOUNDARY CHECK: PASS')
    print('Required study cities: 53')
    print(f'Boundary CSV files: {len(files)}')
    print(f'Loaded study city/state boundaries: {len(polygons)}')
    print('Missing study cities: 0')
    print('Unexpected cities: 0')
    print('Duplicate city/state boundaries: 0')
    print(f'Boundary coordinates: {SOURCE_CRS} -> {TARGET_CRS}')
    return polygons
