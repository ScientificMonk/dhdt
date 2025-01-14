# functions of use for the CopernicusDEM data

# generic libraries
import os
import tarfile
import pathlib
import tempfile
import pandas

# import geospatial libraries
import numpy as np
import geopandas
import rioxarray
from rioxarray.merge import merge_arrays # had some troubles since I got:
    # AttributeError: module 'rioxarray' has no attribute 'merge'
from rioxarray.merge import merge_datasets
from rasterio.enums import Resampling
from shapely.geometry import Polygon
from affine import Affine

# import local functions
from .handler_www import get_file_from_ftps
from .mapping_io import read_geo_info
from .mapping_tools import get_bbox, get_shape_extent
from .handler_sentinel2 import get_crs_from_mgrs_tile

def get_itersecting_DEM_tile_names(index, geometry):
    """
    Find the DEM tiles that intersect the geometry and extract the
    filenames from the index. NOTE: the geometries need to be in the 
    same CRS!
    
    Parameters
    ----------
    index : dtype=GeoDataFrame
        DEM tile index.
    geometry : shapely geometry object
        polygon of interest.

    Returns
    -------
    fname
        file name of tiles of interest.
    """    
    # sometimes points are projected to infinity
    # this is troublesome for intersections
    # hence remove these instances
    out_of_bounds = index['geometry'].area.isna()
    index = index[~out_of_bounds]
    
    mask = index.intersects(geometry)
    index = index[mask]
    return index['CPP filename']

def copDEM_files(members):
    for tarinfo in members:
        if tarinfo.name.endswith('DEM.tif'):
            yield tarinfo

def get_cds_url(): return 'cdsdata.copernicus.eu:990'

def get_cds_path_copDEM(type='DGED',resolution=30, year=2021, version=1):
    cds_path = os.path.join('DEM-datasets',
                            'COP-DEM_GLO-' + str(resolution) + '-' + type,
                            str(year) + '_' + str(version))
    return cds_path

def get_copDEM_filestructure(tmp_path, cds_sso, cds_pw,
                             cds_url='cdsdata.copernicus.eu:990',
                             type='DGED',resolution=30, year=2021, version=1):
    """ the CopernicusDEM is situated in different folders, this function
    downloads the 'mapping.csv'-file that has the ftp-whereabouts of all the
    elevation rasters.

    Parameters
    ----------
    tmp_path : string
        path where the CopDEM meta-data can be dumped
    cds_sso : string
        single sign-in
    cds_pw : string
        pass word
    cds_url : string
        Copernicus Data Service url
    type : {'DGED', 'DTED'}
        * DGED : Defence Gridded Elevation Data, 32 Bit, floating [1]
        * DTED : Digital Terrain Elevation Data, 16 Bit, signed
    resolution : {30, 90}
        post or pixel resolution in meters, the original is in 10 meters, but this
        is not available for download. When DGED option is taken the format is:
            * DT2-format for GLO30
            * DT1-format for GLO90
    year : {2019, 2020, 2021}
        year of revised product
    version : {1, 2}
        sometimes multiple revisions are implemented

    Returns
    -------
    cds_path : string
        directory where CopDEM metadata is situated, this is typically
        'DEM-datasets/COP-DEM_GLO-30-DGED', while the data is situated in
        'datasets/COP-DEM_GLO-30-DGED'.

    References
    ----------
    .. [1] https://www.dgiwg.org/dgiwg-standards/250
    .. [2] https://spacedata.copernicus.eu/cop-dem-faq
    """
    cds_path = get_cds_path_copDEM(type=type, resolution=resolution,
                                   year=year, version=version)
    file_name = 'mapping.csv'
    get_file_from_ftps(cds_url, cds_sso, cds_pw,
                       cds_path, file_name, tmp_path)
    return cds_path

def make_copDEM_geojson(cop_path, cop_file='mapping.csv',
                        out_file='DGED-30.geojson'):
    """ construct a geographic file of the CopDEM meta-data

    Parameters
    ----------
    cop_path : string
        location where CopDEM meta-data is situated
    cop_file : string, default='mapping.csv'
        file name of the CopDEM meta-data
    out_file : out_file, default='DGED-30.geojson'
        file name of the CopDEM geographic file

    Notes
    -----
    The projection systems of the data are the follwing:
        * horizontal : World Geodetic System 1984, WGS84-G1150 (EPSG 4326)
        * vertical : Earth Gravitational Model 2008, EGM2008 (EPSG 3855)
    """
    file_path = os.path.join(cop_path, cop_file)

    # load file with ftp-addresses
    df = pandas.read_csv(file_path, delimiter=";", header=0)
    df_org = df.copy()

    # creating dictionary for trans table
    trans_dict = {"N": "+", "S": "-", "E": "+", "W": "-"}
    # creating translate table from dictionary
    trans_table = "NSEW".maketrans(trans_dict)
    # translating through passed transtable
    df["Lat"] = df["Lat"].str.translate(trans_table)
    df["Long"] = df["Long"].str.translate(trans_table)

    # naming is the lower left corner
    ll = df[["Long", "Lat"]].astype(float)

    def f(x):
        return Polygon.from_bounds(x[0], x[1], x[0] + 1, x[1] + 1)
    geom = ll.apply(f, axis=1)

    # include geometry and make a geopandas dataframe
    gdf = geopandas.GeoDataFrame(df_org, geometry=geom)
    gdf.set_crs(epsg=4326)
    gdf.to_file(os.path.join(cop_path, out_file), driver='GeoJSON')
    return

def make_copDEM_mgrs_tile(mgrs_tile, im_path, im_name, tile_path, cop_path,
                          tile_name='sentinel2_tiles_world.shp',
                          cop_name='mapping.csv', map_name='DGED-30.geojson',
                          sso='', pw=''):
    if (len(sso) == 0) or (len(pw) == 0):
        raise Exception('No username or password were given')
    assert not os.path.exists(os.path.join(im_path, im_name)), \
        ('file does not seem to exist')
    assert not os.path.exists(os.path.join(tile_path, tile_name)), \
        ('file does not seem to exist')

    urls, tars = get_copDEM_s2_tile_intersect_list(tile_path, cop_path,
       mgrs_tile, s2_file=tile_name, cop_file=cop_name,
       map_file=map_name)

    crs = get_crs_from_mgrs_tile(mgrs_tile)
    _, geoTransform, _, rows, cols, _ = read_geo_info(os.path.join(im_path,
                                                                   im_name))
    bbox = get_bbox(geoTransform, rows, cols)

    cds_path, cds_url = get_cds_path_copDEM(), get_cds_url()
    cop_dem = download_and_mosaic_through_ftps(tars, cop_path,
                                               cds_url, cds_path[4:],
                                               sso, pw, bbox, crs, geoTransform)

    cop_dem.to_raster(os.path.join(cop_path, 'COP-DEM-' + mgrs_tile + '.tif'))
    return

def get_copDEM_s2_tile_intersect_list(s2_path, cop_path, s2_toi,
                                      s2_file='sentinel2_tiles_world.shp',
                                      cop_file='mapping.csv',
                                      map_file='DGED-30.geojson',
                                      sso='', pw=''):
    """ get a list of filenames and urls of CopDEM tiles that are touching or
    in a Sentinel-2 tile

    Parameters
    ----------
    s2_path : string
        location where the Sentinel-2 tile data is situated
    cop_path : string
        location where the CopDEM tile data is situated
    s2_toi : string
        MGRS Sentinel-2 tile code of interest
    s2_file : string, default='sentinel2_tiles_world.shp'
        filename of the MGRS Sentinel-2 tiles
    cop_file : string, default='mapping.csv'
        filename of the table with CopDEM meta-data
    map_file : string, default='DGED-30.geojson'
        filename of the geographic CopDEM meta-data
    sso : string
        single sign-in user name
    pw : string
        pass word

    Returns
    -------
    urls : list of strings
        locations of the .tar files
    tars : list of strings
        filenames of the .tar files

    See Also
    --------
    .handler_sentinel2.get_tiles_from_S2_list

    """
    # get dataframe of Sentinel-2 tiles
    file_path = os.path.join(s2_path, s2_file)
    s2_df = geopandas.read_file(file_path)
    s2_df = s2_df[s2_df['Name'].isin([s2_toi])]

    # get meta-data of CopDEM if it is not present
    if not os.path.exists(os.path.join(cop_path,cop_file)):
        if (len(sso)==0) or (len(pw)==0):
            raise Exception('No username or password were given')
        _ = get_copDEM_filestructure(cop_path, sso, pw)
        make_copDEM_geojson(cop_path, cop_file=cop_file,
                            out_file=map_file)
    # read CopDEM meta-data
    cop_df = geopandas.read_file(os.path.join(cop_path, map_file))

    cop_oi = cop_df[cop_df.intersects(s2_df['geometry'].item())]

    urls = list(cop_oi['downloadURL'])
    tars = list(cop_oi['CPP filename'])
    return urls, tars

def download_and_mosaic_through_ftps(file_list, tmp_path, cds_url, cds_path,
                                     cds_sso, cds_pw, bbox, crs, geoTransform):
    """ Download Copernicus DEM tiles and create mosaic according to satellite
    imagery tiling scheme
    
    file_list : list with strings
        list of DEM tile filenames
    tmp_path : string
        work path where to download and untar DEM tiles
    cds_url : string
        Copernicus Data Service url
    cds_path : string
        data directory of interest
    cds_sso : string
        single sign-in
    cds_pw : string
        pass word
    bbox : list
        bound box formated as (x_min, y_min, x_max, y_max)
    crs : string
        coordinate reference string
    geoTransform : tuple, size=(6,1)
        affine transformation coefficients of the DEM tile

    Returns
    -------
    dem_clip : DataArray object
        retiled DEM
    """
    with tempfile.TemporaryDirectory(dir=tmp_path) as tmpdir:
    
        for file_name in file_list:
            get_file_from_ftps(cds_url, cds_sso, cds_pw,
                               cds_path, file_name, tmpdir)

        tar_tiles_filenames = [f for f in os.listdir(tmpdir) if f.endswith('.tar')]
        for tar_fname in tar_tiles_filenames:
            tar_file = tarfile.open(os.path.join(tmpdir, tar_fname), mode="r|")
            tar_file.extractall(members=copDEM_files(tar_file), 
                                path=tmpdir)
            tar_file.close()
            
            
        dem_tiles_filename = pathlib.Path(tmpdir).glob("**/*_DEM.tif")
        dem_clip = mosaic_tiles(dem_tiles_filename, bbox, crs, geoTransform)
          
        # sometimes out of bound tiles are still present,
        # hence rerun a clip to be sure
        # dem_clip = dem_clip.rio.clip_box(*bbox)
    return dem_clip

def mosaic_tiles(dem_tiles_filenames, bbox, crs, geoTransform):
    """ given a selection of elevation models, mosaic them together

    Parameters
    ----------
    dem_tiles_filenames : list with strings
        list of DEM tile filenames
    bbox : list
        bound box formated as (x_min, y_min, x_max, y_max)
    crs : string
        coordinate reference string
    geoTransform : tuple, size=(6,1)
        affine transformation coefficients of the DEM tile

    Returns
    -------
    merged : DataArray object
        mosaiced DEM
    """
    if not isinstance(crs, str): crs = crs.ExportToWkt()

    shape_im = get_shape_extent(bbox.reshape((2,2)).T.ravel(),
                             geoTransform)
    # geoTransform needs to be converted to Affine model
    afn = Affine.from_gdal(*geoTransform)

    merged = None
    for f in dem_tiles_filenames:
        dem_tile = rioxarray.open_rasterio(f, masked=True)
        # reproject to image CRS
        dem_tile_xy = dem_tile.rio.reproject(crs, transform=afn,
                                             resampling=Resampling.lanczos,
                                             shape=shape_im)

        if merged is None:
            merged = dem_tile_xy
        else:
            dem_clip = merge_arrays([merged, dem_tile_xy])
    return merged
