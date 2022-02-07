import os
from typing import Any, Dict, List, Optional, Sequence, Union

import dateutil.parser
import pystac
import rasterio as rio
from .constants import (
    DLR_PROVIDER,
    WSF2019_BANDS,
    WSF2019_DESCRIPTION,
    WSF2019_ID,
    WSF2019_LICENSE,
    WSF2019_TITLE,
)
from pystac.extensions.eo import EOExtension
from pystac.extensions.item_assets import ItemAssetsExtension
from pystac.extensions.projection import ProjectionExtension
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import unary_union
from copy import deepcopy

import pyproj
from datetime import datetime


def get_spatial_extent(polygons: List[Polygon]) -> pystac.SpatialExtent:
    unioned_geom = unary_union(polygons)
    return pystac.SpatialExtent(bboxes=[unioned_geom.bounds])


def get_temporal_extent(
    starttime: datetime, endtime: datetime
) -> pystac.TemporalExtent:
    time_interval = [starttime, endtime]
    return pystac.TemporalExtent(intervals=[time_interval])  # type: ignore


def create_full_extent(stac_item_list: List[pystac.Item]) -> pystac.Extent:
    polygons = []
    time_ranges = []

    for stac_item in stac_item_list:
        geom = stac_item.geometry
        time_range = stac_item.datetime

        polygons.append(shape(geom))
        time_ranges.append(time_range)

    spatial_extent = get_spatial_extent(polygons)
    temporal_extent = get_temporal_extent(
        min(time_ranges), max(time_ranges)
    )  # type: ignore

    collection_extent = pystac.Extent(
        spatial=spatial_extent,
        temporal=temporal_extent,
    )

    return collection_extent


def reproject_geom(
    src_crs: Union[pyproj.CRS, rio.crs.CRS, str],
    dest_crs: Union[pyproj.CRS, rio.crs.CRS, str],
    geom: Dict[str, Any],
    precision: Optional[int] = None,
) -> Dict[str, Any]:
    """Reprojects a geometry represented as GeoJSON
    from the src_crs to the dest crs.
    Args:
        src_crs: pyproj.crs.CRS, rasterio.crs.CRS or str used to create one
            Projection of input data.
        dest_crs: pyproj.crs.CRS, rasterio.crs.CRS or str used to create one
            Projection of output data.
        geom (dict): The GeoJSON geometry
        precision
    Returns:
        dict: The reprojected geometry
    """
    transformer = pyproj.Transformer.from_crs(src_crs, dest_crs, always_xy=True)
    result = deepcopy(geom)

    def fn(coords: Sequence[Any]) -> Sequence[Any]:
        coords = list(coords)
        for i in range(0, len(coords)):
            coord = coords[i]
            if isinstance(coord[0], Sequence):
                coords[i] = fn(coord)
            else:
                x, y = coord
                reprojected_coords = list(transformer.transform(x, y))
                if precision is not None:
                    reprojected_coords = [
                        round(n, precision) for n in reprojected_coords
                    ]
                coords[i] = reprojected_coords
        return coords

    result["coordinates"] = fn(result["coordinates"])

    return result


def create_collection(extent: pystac.Extent) -> pystac.Collection:
    """Creates a STAC COllection for wsf2019 data.
    Args:
        seasons (List[int]): List of years that represent the wsf2019 seasons
            this collection represents.
    """

    collection = pystac.Collection(
        id=WSF2019_ID,
        description=WSF2019_DESCRIPTION,
        title=WSF2019_TITLE,
        href="data/",
        license=WSF2019_LICENSE,
        providers=[DLR_PROVIDER],
        extent=extent,
        extra_fields={
            "item_assets": {
                "image": {
                    "eo:bands": [b.properties for b in WSF2019_BANDS],
                    "roles": ["data"],
                    "title": "Binary Mask COG tile",
                    "type": pystac.MediaType.COG,
                },
            }
        },
    )
    ItemAssetsExtension.add_to(collection)

    return collection


def create_item(cog_href: str, collection: pystac.Collection) -> pystac.Item:

    with rio.open(cog_href) as ds:
        gsd = ds.res[0]
        epsg = int(ds.crs.to_authority()[1])
        image_shape = list(ds.shape)
        original_bbox = list(ds.bounds)
        transform = list(ds.transform)
        geom = reproject_geom(
            ds.crs, "epsg:4326", mapping(box(*ds.bounds)), precision=6
        )

    # data/WSF2019_v1_-100_16.tif -> WSF2019_v1_100_16
    fname = os.path.splitext(os.path.basename(cog_href))[0]
    item_id = fname.replace("-", "")

    bounds = list(shape(geom).bounds)

    dt = dateutil.parser.isoparse("2019-01-01")

    properties: Dict[str, str] = {}

    item = pystac.Item(
        id=item_id,
        geometry=geom,
        bbox=bounds,
        datetime=dt,
        properties=properties,
    )

    # Common metadata
    item.common_metadata.providers = [DLR_PROVIDER]
    item.common_metadata.gsd = gsd

    item.collection = collection  # type: ignore

    # eo, for asset bands
    EOExtension.add_to(item)

    # proj
    projection = ProjectionExtension.ext(item, add_if_missing=True)
    projection.epsg = epsg
    projection.shape = image_shape
    projection.bbox = original_bbox
    projection.transform = transform

    # COG
    item.add_asset(
        "image",
        pystac.Asset(
            href=cog_href,
            media_type=pystac.MediaType.COG,
            roles=["data"],
            title="Binary mask COG tile",
        ),
    )

    asset_eo = EOExtension.ext(item.assets["image"])
    asset_eo.bands = WSF2019_BANDS

    return item
