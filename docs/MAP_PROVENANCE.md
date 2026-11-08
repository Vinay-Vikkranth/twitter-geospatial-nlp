# Native ArcGIS map provenance

## Sources and export method

The configured city_registry_53.csv and all 53 Census WKT boundary files come from Twitter_Pipeline/Current/data. This is the same expanded study configuration used by the pipeline, distinct from the 35-city gun violence model. Boundary coordinates are explicitly declared NAD83 (EPSG:4269); ArcGIS transforms them to WGS84 for the exported map.

The images were newly exported using licensed ArcGIS Pro 3.6 `arcpy.mp` on November 7, 2026, with the project's Light Gray basemap style. New editable layouts and a temporary geodatabase are local portfolio artifacts; original source files and APRX projects are unchanged.

## Nationwide footprint

A fresh check confirmed 53 boundary polygons, a 53-city registry and 3,578 configured incidents. The map shows boundary-centroid city markers sized by registry incident counts. It does not display individual incident addresses, raw tweets or tweet locations. Markers may overlap for nearby municipalities or boroughs. These are configured population counts, not a completed full archive analysis or model output.

## Chicago boundary

Exactly one Chicago boundary is selected from that configured polygon set. This image illustrates the spatial geofence used alongside the pipeline's temporal windows. It does not display tweet matches or demonstrate label accuracy. All basemap source attribution is retained. Legend overflow is checked before export and the resulting image is visually inspected.

The ESRI concept diagrams found under Project53 docs were not used as Vinay's research maps: they illustrate general GIS concepts rather than this project's own measured geography.
